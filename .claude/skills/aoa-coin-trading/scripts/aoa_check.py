#!/usr/bin/env python3
"""aoa_check — 워뇨띠(aoa)식 매매 원칙 점검기.

1시간봉으로 7일 박스 위치 · 24시간 쏠림 · 변동성 비율을 계산하고, 분할 지정가
계획의 실질 레버리지 · 청산가를 따져 매매원칙.md 규칙대로 판정한 체크카드를
출력한다. 공개 시세 API만 읽는다 — API 키도, 주문 기능도 없다.

사용 예:
  python3 aoa_check.py                                    # 바이낸스 BTCUSDT
  python3 aoa_check.py --exchange upbit --symbol KRW-BTC  # 업비트 원화 현물
  python3 aoa_check.py --exchange bybit --side long --equity 10000 \\
      --plan "67000:0.05,66600:0.05,66200:0.1"
  python3 aoa_check.py --price 66800 --high7 72400 --low7 66100 --price24h 69000
  python3 aoa_check.py --csv btc_1h.csv --json

--plan 은 "지정가:수량" 을 쉼표로 잇는다 (천 단위 쉼표 없이).
--csv 는 1시간봉, 열 순서 time,open,high,low,close[,volume].
청산가는 USDT 선형 계약 · 격리 마진 · 수수료 제외 근사치다. 투자 권유가 아니다.
"""
import argparse
import csv
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BOX_HOURS = 168            # 7일 박스
DAY_HOURS = 24
VOL_LONG_HOURS = 720       # 30일 변동성
ZONE_PCT = 25.0            # 유리한 끝
MIDDLE_PCT = 50.0          # 25~50% = 데이터상 유일한 손실 구간
VOL_MODE_RATIO = 1.5       # 원칙 3: 평소의 1.5배
NORMAL_LEVERAGE = 2.0      # 2019~2021 중앙값 2.0 → 1.6 → 1.1배
MAX_LEVERAGE = 3.0
SURVIVE_MOVE = 0.30        # 원칙 2: 20~30% 역행에도 청산 X
MIN_SURVIVE_MOVE = 0.20
MAX_HOLD_DAYS = 14
DEFAULT_MMR = 0.005        # 유지증거금률 (거래소·구간별로 다름)

FIAT = ("USDT", "USDC", "FDUSD", "BUSD", "USD", "KRW")
HEADERS = {"User-Agent": "aoa-check/1.0", "Accept": "application/json"}
KST = timezone(timedelta(hours=9))


# ── 시세 ────────────────────────────────────────────────────────────────
# 캔들 = (time_ms, open, high, low, close, volume), 오래된 → 최신

def _get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_binance(symbol, futures=False):
    base = ("https://fapi.binance.com/fapi/v1/klines" if futures
            else "https://api.binance.com/api/v3/klines")
    rows = _get_json(f"{base}?symbol={symbol}&interval=1h&limit=1000")
    return [(int(r[0]), *map(float, r[1:6])) for r in rows]


def fetch_bybit(symbol):
    data = _get_json("https://api.bybit.com/v5/market/kline"
                     f"?category=linear&symbol={symbol}&interval=60&limit=1000")
    if data.get("retCode") != 0:
        raise RuntimeError(f"bybit: {data.get('retMsg')}")
    return sorted((int(r[0]), *map(float, r[1:6])) for r in data["result"]["list"])


def fetch_upbit(market):
    candles, to = {}, None
    for _ in range(4):  # 200개씩 4번 = 800시간 (30일 변동성용)
        url = f"https://api.upbit.com/v1/candles/minutes/60?market={market}&count=200"
        if to:
            url += "&to=" + urllib.parse.quote(to)
        rows = _get_json(url)
        if not rows:
            break
        for r in rows:
            t = datetime.strptime(r["candle_date_time_utc"], "%Y-%m-%dT%H:%M:%S")
            ms = int(t.replace(tzinfo=timezone.utc).timestamp() * 1000)
            candles[ms] = (ms, float(r["opening_price"]), float(r["high_price"]),
                           float(r["low_price"]), float(r["trade_price"]),
                           float(r["candle_acc_trade_volume"]))
        to = min(r["candle_date_time_utc"] for r in rows) + "Z"
        time.sleep(0.2)  # 업비트 캔들 API 초당 요청 제한
    return sorted(candles.values())


def _parse_time(text):
    text = text.strip()
    try:
        v = float(text)
        return int(v if v > 1e12 else v * 1000)
    except ValueError:
        pass
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            try:
                o, h, l, c = (float(x) for x in row[1:5])
            except ValueError:
                continue  # 헤더 행
            try:
                v = float(row[5]) if len(row) > 5 else 0.0
            except ValueError:
                v = 0.0
            rows.append((_parse_time(row[0]), o, h, l, c, v))
    if rows and all(r[0] is not None for r in rows):
        rows.sort()  # 시간을 읽을 수 있으면 오래된 순으로, 아니면 파일 순서 그대로
    return rows


# ── 지표 (보조지표 아님: 박스 · 쏠림 · 변동성 · 거래량만) ─────────────────

def _stdev_returns(closes):
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    return statistics.pstdev(rets) if len(rets) > 1 else 0.0


def market_from_candles(candles):
    if len(candles) < BOX_HOURS + 1:
        raise SystemExit(f"1시간봉이 {BOX_HOURS + 1}개 이상 필요합니다 (받은 개수 {len(candles)}).")
    box = candles[-(BOX_HOURS + 1):-1]  # 진행 중인 봉을 뺀 직전 7일
    closes = [c[4] for c in candles]
    vol_ratio = None
    if len(closes) > VOL_LONG_HOURS:
        long_sd = _stdev_returns(closes[-(VOL_LONG_HOURS + 1):])
        if long_sd > 0:
            vol_ratio = _stdev_returns(closes[-(BOX_HOURS + 1):]) / long_sd
    volume_ratio = None
    if len(candles) >= BOX_HOURS + DAY_HOURS + 1:
        last_day = sum(c[5] for c in candles[-(DAY_HOURS + 1):-1])
        prior = candles[-(BOX_HOURS + DAY_HOURS + 1):-(DAY_HOURS + 1)]
        per_day = sum(c[5] for c in prior) / (BOX_HOURS / DAY_HOURS)
        if per_day > 0:
            volume_ratio = last_day / per_day
    return {
        "price": closes[-1],
        "high7": max(c[2] for c in box),
        "low7": min(c[3] for c in box),
        "price24h": closes[-(DAY_HOURS + 1)],
        "vol_ratio": vol_ratio,
        "volume_ratio": volume_ratio,
        "candles": len(candles),
    }


def base_asset(symbol):
    s = symbol.upper().split(".")[0].replace("_", "-").replace("/", "-")
    parts = [p for p in s.split("-") if p]
    if len(parts) > 1:  # KRW-BTC, BTC-USDT, BTC-USDT-SWAP
        base = next((p for p in parts if p not in FIAT), parts[0])
    else:               # BTCUSDT, XBTUSD
        base = s
        for q in FIAT:
            if s.endswith(q) and len(s) > len(q):
                base = s[:-len(q)]
                break
    return "BTC" if base == "XBT" else base


# ── 판정 ────────────────────────────────────────────────────────────────

def box_position(side, price, high7, low7):
    """유리한 끝 = 0%. 롱은 7일 저가, 숏은 7일 고가 쪽이 0%. 0% 미만이면 박스 이탈."""
    edge = price - low7 if side == "long" else high7 - price
    return edge / (high7 - low7) * 100


def judge_side(side, m, asset):
    pos = box_position(side, m["price"], m["high7"], m["low7"])
    change = None if m["price24h"] is None else (m["price"] / m["price24h"] - 1) * 100
    counter = None if change is None else (change < 0 if side == "long" else change > 0)
    if asset not in ("BTC", "ETH"):
        status, reason = "⛔", "알트코인 — 박스 끝 역추세·물타기 금지 (규칙 2 · 리플 강제청산 -15.3 BTC)"
    elif pos < 0:
        broke = "7일 저점 이탈" if side == "long" else "7일 고점 돌파"
        status, reason = "⚠️", f"{broke} — 박스가 깨지는 중. 신규 역추세 보류, 보유 중이면 물타기 중단·당일 축소 (규칙 7)"
    elif pos <= ZONE_PCT:
        if counter:
            status, reason = "✅", "유리한 끝 + 쏠림의 반대편 — 진입 구간"
        elif counter is None:
            status, reason = "🟡", "박스 끝 — 24시간 추세 미확인 (--price24h 로 다시 점검)"
        else:
            status, reason = "🟡", "박스 끝이지만 24시간 순추세 — 소량만 (큰 매매 순추세 -120 BTC)"
    elif pos <= MIDDLE_PCT:
        status, reason = "⏸", "애매한 중간(25~50%) — 대기. 데이터상 유일한 손실 구간 (승률 76%에도 -193 BTC)"
    else:
        status, reason = "⏸", "박스 반대편 — 대기"
    rng = m["high7"] - m["low7"]
    zone = m["low7"] + rng * ZONE_PCT / 100 if side == "long" else m["high7"] - rng * ZONE_PCT / 100
    return {"side": side, "position_pct": pos, "change24h_pct": change, "countertrend": counter,
            "zone_price": zone, "status": status, "reason": reason}


def parse_plan(text):
    legs = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        try:
            price, qty = (float(x) for x in part.split(":"))
        except ValueError:
            raise SystemExit(f"--plan 형식 오류: '{part}' (예: 67000:0.05,66000:0.1 — 천 단위 쉼표 없이)")
        if price <= 0 or qty <= 0:
            raise SystemExit(f"--plan 가격·수량은 0보다 커야 합니다: '{part}'")
        legs.append((price, qty))
    if not legs:
        raise SystemExit("--plan 이 비었습니다.")
    return legs


def liquidation_price(side, avg, leverage, mmr):
    """USDT 선형 · 격리 · 수수료 제외 근사. 1배 이하 롱은 청산 없음(None)."""
    if side == "long":
        liq = avg * (1 - 1 / leverage) / (1 - mmr)
        return liq if liq > 0 else None
    return avg * (1 + 1 / leverage) / (1 + mmr)


def evaluate_plan(legs, side, equity, mmr, spot, m, entry=True):
    """entry=False 는 보유 점검 ("평단:수량") — 지정가 위치 규칙은 따지지 않는다."""
    qty = sum(q for _, q in legs)
    notional = sum(p * q for p, q in legs)
    avg = notional / qty
    leverage = notional / equity
    checks = []
    liq = dist = None
    if spot:
        ok = leverage <= 1
        checks.append(("✅" if ok else "⛔",
                       f"현물 — 자산의 {leverage * 100:.0f}% 사용" if ok else "현물 계획이 자산보다 큼"))
    else:
        if leverage <= NORMAL_LEVERAGE:
            checks.append(("✅", f"실질 레버리지 {leverage:.2f}배 — 평소 범위(1~2배)"))
        elif leverage <= MAX_LEVERAGE:
            checks.append(("✅", f"실질 레버리지 {leverage:.2f}배 — 상한(3배) 이내, 평소보다 큼"))
        else:
            checks.append(("⛔", f"실질 레버리지 {leverage:.2f}배 — 3배 초과. 첫 진입 수량부터 줄일 것 (규칙 6)"))
        liq = liquidation_price(side, avg, leverage, mmr)
        if liq is None:
            checks.append(("✅", "청산 없음 (1배 이하 롱)"))
        else:
            dist = abs(liq / avg - 1)
            sign = "-" if side == "long" else "+"
            if dist >= SURVIVE_MOVE:
                mark, note = "✅", "30% 역행 생존"
            elif dist >= MIN_SURVIVE_MOVE:
                mark, note = "🟡", "20~30% — 30% 기준 미달, 줄이기 권장"
            else:
                mark, note = "⛔", "20%도 못 버팀 — 규칙 6 위반"
            checks.append((mark, f"예상 청산가 ≈ {fmt(liq)} (평단 대비 {sign}{dist * 100:.1f}%) — {note}"))
    rows = []
    for price, q in legs:
        pos = box_position(side, price, m["high7"], m["low7"])
        mark = "⛔ 박스 밖 — 깔지 않는다 (규칙 7)" if pos < 0 else ("✅" if pos <= ZONE_PCT else "⏸ 유리한 끝 밖")
        rows.append({"price": price, "qty": q, "position_pct": pos, "mark": mark})
    if entry:
        outside = sum(1 for r in rows if r["position_pct"] < 0)
        off_zone = sum(1 for r in rows if r["position_pct"] > ZONE_PCT)
        if outside:
            checks.append(("⛔", f"박스 밖 지정가 {outside}개 — 빼고 다시 계획 (규칙 5·7)"))
        if off_zone:
            checks.append(("🟡", f"유리한 끝 밖 지정가 {off_zone}개 — 0~25% 안으로 옮기기 (규칙 3)"))
        prices = [p for p, _ in legs]
        if prices != sorted(prices, reverse=(side == "long")):
            checks.append(("🟡", "분할은 불리해질수록 (롱은 더 낮게, 숏은 더 높게) 이어지게 깐다"))
    return {"legs": rows,
            "avg": avg, "qty": qty, "notional": notional, "leverage": None if spot else leverage,
            "liquidation": liq, "liq_distance_pct": None if dist is None else dist * 100,
            "first_leg_share_pct": legs[0][1] / qty * 100,
            "max_notional": equity * (1 if spot else MAX_LEVERAGE), "equity": equity,
            "checks": [{"status": s, "text": t} for s, t in checks]}


# ── 출력 ────────────────────────────────────────────────────────────────

def fmt(v):
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:,.2f}"
    return f"{v:.6g}"


def render(report):
    m, lines = report["market"], []
    width = (m["high7"] / m["low7"] - 1) * 100
    lines.append(f"## 🧭 aoa 매매 체크카드 — {report['symbol']} ({report['source']}) · {report['time']}")
    lines.append(f"- 현재가 **{fmt(m['price'])}** · 직전 7일 박스 **{fmt(m['low7'])} ~ {fmt(m['high7'])}** (폭 {width:.1f}%)")
    lines.append(f"- 롱 자리 ≤ **{fmt(report['long_zone'])}** · 숏 자리 ≥ **{fmt(report['short_zone'])}** (유리한 끝 25%)")
    if m["price24h"] is not None:
        lines.append(f"- 24시간 변화 **{(m['price'] / m['price24h'] - 1) * 100:+.1f}%** (24시간 전 {fmt(m['price24h'])})")
    if m["vol_ratio"] is None:
        lines.append("- 변동성 7일/30일 — 미계산 (30일 데이터 부족 또는 미입력)")
    else:
        mode = ("🌪 변동성 모드 — 방향 말고 과한 쏠림 되돌림만, 한 방향으로 쌓지 않기 (규칙 8)"
                if m["vol_ratio"] >= VOL_MODE_RATIO else "평시")
        lines.append(f"- 변동성 7일/30일 **{m['vol_ratio']:.2f}배** → {mode}")
    if m.get("volume_ratio") is not None:
        lines.append(f"- 거래량 최근 24시간 / 직전 7일 일평균 **{m['volume_ratio']:.2f}배** (쏠림 확인용)")
    if report["asset"] == "ETH":
        lines.append("- ETH — 유동성은 깊지만 알트. BTC보다 작게 (규칙 2)")

    for s in report["sides"]:
        name = "롱" if s["side"] == "long" else "숏"
        lines += ["", f"### {name} {s['status']} {s['reason']}"]
        lines.append(f"- 박스 위치 **{s['position_pct']:.0f}%** (0~25%가 유리한 끝)")
        if s["countertrend"] is not None:
            lines.append(f"- 24시간 쏠림의 반대편(역추세): {'예' if s['countertrend'] else '아니오'}")
        if s["status"] == "⏸":
            mark = "이하" if s["side"] == "long" else "이상"
            lines.append(f"- 기다릴 가격: **{fmt(s['zone_price'])}** {mark}")
        exit_line = (f"7일 저점 {fmt(m['low7'])} 이탈" if s["side"] == "long"
                     else f"7일 고점 {fmt(m['high7'])} 돌파")
        lines.append(f"- 도망갈 기준: {exit_line} → 물타기 중단·당일 축소")

    p = report.get("plan")
    if p:
        name = "롱" if report["plan_side"] == "long" else "숏"
        kind = "현물 · 자산" if p["leverage"] is None else "USDT 선형 · 격리 근사 · 증거금"
        lines += ["", f"### 분할 계획 ({name} · {kind} {fmt(p['equity'])})"]
        lines += ["| 지정가 | 수량 | 박스 위치 |", "|---|---|---|"]
        lines += [f"| {fmt(l['price'])} | {l['qty']:g} | {l['position_pct']:.0f}% {l['mark']} |" for l in p["legs"]]
        lines.append(f"- 평단 **{fmt(p['avg'])}** · 전부 체결 명목 **{fmt(p['notional'])}** · 첫 물량 비중 {p['first_leg_share_pct']:.0f}%")
        lines += [f"- {c['status']} {c['text']}" for c in p["checks"]]
        if p["leverage"] is not None:
            lines.append(f"- 이 증거금의 명목 상한 **{fmt(p['max_notional'])}** (3배) · 평소 {fmt(p['equity'])} ~ {fmt(p['equity'] * NORMAL_LEVERAGE)}")

    if report.get("held"):
        lines += ["", f"### 보유 {report['held']['days']:g}일 {report['held']['status']} {report['held']['text']}"]

    lines += ["", f"### 판정: {report['verdict']}", "",
              "잊지 말 것: 시장가 금지·지정가 분할 (규칙 5) · 자리를 비우면 먼저 정리, 최대 14일 (규칙 9) · "
              "보조지표·추세선 없이, 3분·30분·3시간·3일봉 제외 (규칙 10)", "",
              "> 계산 도구일 뿐 투자 권유가 아닙니다. 레버리지 선물은 원금 전액을 잃을 수 있습니다."]
    return "\n".join(lines)


def verdict(report):
    statuses = [s["status"] for s in report["sides"]]
    size_blocked = any(c["status"] == "⛔" for c in (report.get("plan") or {}).get("checks", []))
    vol = report["market"]["vol_ratio"]
    vol_mode = vol is not None and vol >= VOL_MODE_RATIO
    held = report.get("held")
    if held:  # 보유 포지션 점검 (--side 필수): 정리 / 축소 / 익절 / 유지
        side = report["sides"][0]
        if held["status"] == "⛔" or side["status"] == "⛔":
            return "⛔ 정리 — 손익과 무관하게 닫고 처음부터 재평가"
        if side["status"] == "⚠️":
            return "⚠️ 축소 — 박스가 포지션 반대로 깨짐. 물타기 중단, 되돌림에 줄여 그날 안에 정리 (규칙 7)"
        if size_blocked:
            return "⚠️ 축소 — 실질 레버리지·청산 거리부터 기준 안으로 (규칙 6)"
        if side["position_pct"] >= 100 - ZONE_PCT:
            return "💰 익절 구간 — 박스 반대편 끝 도착. 남은 물량 지정가로 정리, 반대 방향은 새로 점검 (2021-06 핑퐁)"
        return "✅ 유지 가능 — 도망갈 기준·14일·자리 비우면 정리, 셋을 지키는 동안만"
    if "⛔" in statuses or size_blocked:
        return "⛔ 진입 금지 — ⛔ 항목부터 해결"
    best = [s for s in report["sides"] if s["status"] == "✅"]
    if best:
        names = "/".join("롱" if s["side"] == "long" else "숏" for s in best)
        return f"✅ {names} 진입 구간 — 지정가 분할, 체크카드 나머지(현물 단계·시드·지켜볼 수 있나) 확인 후"
    if "🟡" in statuses:
        return "🟡 소량만 또는 추가 확인"
    if "⚠️" in statuses:
        if vol_mode:
            return "⚠️ 박스 이탈 + 변동성 모드 — 큰 역추세 금지, 과한 쏠림 되돌림만 소량·짧게 (규칙 7·8)"
        return "⚠️ 박스 이탈 — 새 박스가 생길 때까지 신규 역추세 보류"
    return "⏸ 대기 — 애매하면 안 한다"


def main():
    ap = argparse.ArgumentParser(description="워뇨띠(aoa)식 매매 원칙 점검기 — 주문 기능 없음")
    ap.add_argument("--exchange", choices=["binance", "binance-futures", "bybit", "upbit"], default="binance")
    ap.add_argument("--symbol", help="기본 BTCUSDT (업비트는 KRW-BTC)")
    ap.add_argument("--csv", help="1시간봉 CSV: time,open,high,low,close[,volume]")
    ap.add_argument("--price", type=float, help="직접 입력: 현재가")
    ap.add_argument("--high7", type=float, help="직접 입력: 직전 7일 최고가")
    ap.add_argument("--low7", type=float, help="직접 입력: 직전 7일 최저가")
    ap.add_argument("--price24h", type=float, help="직접 입력: 24시간 전 가격")
    ap.add_argument("--vol-ratio", type=float, help="직접 입력: 7일 변동성 ÷ 30일 변동성")
    ap.add_argument("--side", choices=["long", "short"], help="생략하면 롱·숏 모두 판정")
    ap.add_argument("--plan", help='분할 지정가 "가격:수량,가격:수량" (보유 점검은 "평단:수량")')
    ap.add_argument("--equity", type=float, help="이 포지션 증거금(격리) 또는 선물 계좌 자산(교차)")
    ap.add_argument("--mmr", type=float, default=DEFAULT_MMR, help="유지증거금률 (기본 0.005)")
    ap.add_argument("--spot", action="store_true", help="현물 계획 (레버리지 없음)")
    ap.add_argument("--held-days", type=float, help="보유 포지션 점검: 지금까지 보유한 일수")
    ap.add_argument("--json", action="store_true", help="JSON 으로 출력")
    a = ap.parse_args()

    if a.plan and (not a.side or not a.equity):
        ap.error("--plan 에는 --side 와 --equity 가 필요합니다.")
    if a.held_days is not None and not a.side:
        ap.error("--held-days 에는 보유 방향 --side 가 필요합니다.")
    if a.equity is not None and a.equity <= 0:
        ap.error("--equity 는 0보다 커야 합니다.")
    if a.spot and a.side == "short":
        ap.error("현물(--spot)은 숏 계획을 점검할 수 없습니다.")

    manual = a.price is not None or a.high7 is not None or a.low7 is not None
    symbol = a.symbol or ("KRW-BTC" if a.exchange == "upbit" else "BTCUSDT")
    if manual:
        if None in (a.price, a.high7, a.low7):
            ap.error("직접 입력은 --price, --high7, --low7 가 모두 필요합니다.")
        m = {"price": a.price, "high7": a.high7, "low7": a.low7, "price24h": a.price24h,
             "vol_ratio": a.vol_ratio, "volume_ratio": None, "candles": None}
        source = "직접 입력"
    else:
        try:
            if a.csv:
                candles, source = load_csv(a.csv), f"CSV {os.path.basename(a.csv)}"
            elif a.exchange == "upbit":
                candles, source = fetch_upbit(symbol), "업비트 1시간봉"
            elif a.exchange == "bybit":
                candles, source = fetch_bybit(symbol), "바이비트 1시간봉"
            else:
                futures = a.exchange == "binance-futures"
                candles = fetch_binance(symbol, futures)
                source = "바이낸스 선물 1시간봉" if futures else "바이낸스 1시간봉"
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            print(f"시세 조회 실패: {e}\n→ 차트에서 읽은 값으로 직접 입력: "
                  "--price 현재가 --high7 7일고가 --low7 7일저가 --price24h 24시간전가격", file=sys.stderr)
            sys.exit(2)
        m = market_from_candles(candles)
        if a.vol_ratio is not None:
            m["vol_ratio"] = a.vol_ratio
    if m["high7"] <= m["low7"]:
        sys.exit("7일 고가가 저가보다 커야 합니다.")

    asset = base_asset(symbol)
    sides = [a.side] if a.side else ["long", "short"]
    report = {
        "symbol": symbol, "asset": asset, "source": source,
        "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "market": m,
        "long_zone": m["low7"] + (m["high7"] - m["low7"]) * ZONE_PCT / 100,
        "short_zone": m["high7"] - (m["high7"] - m["low7"]) * ZONE_PCT / 100,
        "sides": [judge_side(s, m, asset) for s in sides],
    }
    if a.plan:
        report["plan_side"] = a.side
        report["plan"] = evaluate_plan(parse_plan(a.plan), a.side, a.equity, a.mmr, a.spot, m,
                                       entry=a.held_days is None)
    if a.held_days is not None:
        over = a.held_days >= MAX_HOLD_DAYS
        report["held"] = {"days": a.held_days, "status": "⛔" if over else "✅",
                          "text": "2주 초과 — 손익 무관 정리 후 재평가 (규칙 9 · 25일·44일 보유가 4분기 -570 BTC)"
                          if over else f"{MAX_HOLD_DAYS}일 이내 — 방치만 하지 않으면 OK"}
    report["verdict"] = verdict(report)

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔 이모지·한글
    except (AttributeError, ValueError):
        pass
    main()
