#!/usr/bin/env node
/**
 * Gemini API 연결 확인 스크립트 (standalone).
 *
 * VS Code 익스텐션 밖에서 Gemini 연동이 정상인지 진단한다. 키를 찾는 순서는
 * 익스텐션과 동일한 우선순위를 따른다:
 *   1) GEMINI_API_KEY 환경변수
 *   2) <company>/_agents/business/tools/gemini_account.json  (단일 진실의 출처, v2.89.153)
 *   3) <company>/_agents/business/config.md 의 `GEMINI_API_KEY: ...` 라인
 *
 * 확인 항목:
 *   [1/3] 키 유효성  — models 목록 조회 (HTTP 200 이면 키 자체는 유효)
 *   [2/3] 텍스트 생성 — 설정된 TEXT_MODEL (기본 gemini-3.1-flash-lite-preview) 로 실제 generateContent
 *   [3/3] 이미지 모델 — 설정된 IMAGE_MODEL 로 generateContent (무료 tier 는 quota 0 → 경고만)
 *
 * Requirements:
 *   - Node 18+ (내장 fetch 사용, 외부 의존성 없음)
 *
 * Usage:
 *   node scripts/check_gemini.js                                  # 회사 폴더 설정에서 키 탐색
 *   GEMINI_API_KEY=AIza... node scripts/check_gemini.js           # 키 직접 지정
 *   BRAIN_DIR=~/my-brain node scripts/check_gemini.js             # 커스텀 두뇌 폴더
 *   COMPANY_DIR=/abs/path node scripts/check_gemini.js            # detached 회사 폴더
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// ───────────────────────── Config (env-overridable) ─────────────────────────
const BRAIN_DIR = (process.env.BRAIN_DIR || path.join(os.homedir(), '.connect-ai-brain')).replace(/^~/, os.homedir());
const COMPANY_DIR = (process.env.COMPANY_DIR || path.join(BRAIN_DIR, '_company')).replace(/^~/, os.homedir());
const BASE_URL = process.env.GEMINI_BASE_URL || 'https://generativelanguage.googleapis.com/v1beta';
const DEFAULT_TEXT_MODEL = 'gemini-3.1-flash-lite-preview';
const DEFAULT_IMAGE_MODEL = 'gemini-3.1-flash-image-preview';
const TIMEOUT_MS = parseInt(process.env.TIMEOUT_MS || '30000', 10);

// ───────────────────────── Helpers ─────────────────────────
const safeRead = (p) => { try { return fs.readFileSync(p, 'utf-8'); } catch { return ''; } };
const mask = (k) => (k && k.length > 8 ? `${k.slice(0, 6)}…${k.slice(-4)}` : '(없음)');

/** 익스텐션과 같은 우선순위로 키/모델 설정을 찾는다. */
function loadGeminiConfig() {
    const out = { apiKey: '', textModel: '', imageModel: '', source: '' };

    if ((process.env.GEMINI_API_KEY || '').trim()) {
        out.apiKey = process.env.GEMINI_API_KEY.trim();
        out.textModel = (process.env.GEMINI_TEXT_MODEL || '').trim();
        out.imageModel = (process.env.GEMINI_IMAGE_MODEL || '').trim();
        out.source = '환경변수 GEMINI_API_KEY';
        return out;
    }

    /* gemini_account.json — 단일 진실의 출처 (extension.ts v2.89.153 과 동일 경로) */
    const jsonPath = path.join(COMPANY_DIR, '_agents', 'business', 'tools', 'gemini_account.json');
    try {
        if (fs.existsSync(jsonPath)) {
            const cfg = JSON.parse(safeRead(jsonPath) || '{}');
            out.apiKey = String(cfg.API_KEY || '').trim();
            out.textModel = String(cfg.TEXT_MODEL || '').trim();
            out.imageModel = String(cfg.IMAGE_MODEL || '').trim();
            if (out.apiKey) { out.source = jsonPath; return out; }
        }
    } catch { /* fall through to config.md */ }

    /* config.md — line-anchored (extension.ts v2.89.5 와 동일하게 라인 시작 강제) */
    const cfgPath = path.join(COMPANY_DIR, '_agents', 'business', 'config.md');
    const txt = safeRead(cfgPath);
    const pick = (key) => {
        const m = txt.match(new RegExp('^' + key + '[ \\t]*[:：=][ \\t]*([^\\r\\n]+?)[ \\t]*$', 'm'));
        return m ? m[1].trim() : '';
    };
    out.apiKey = pick('GEMINI_API_KEY');
    out.textModel = pick('GEMINI_TEXT_MODEL');
    out.imageModel = pick('GEMINI_IMAGE_MODEL');
    if (out.apiKey) out.source = cfgPath;
    return out;
}

async function callGemini(pathname, body) {
    const url = `${BASE_URL}/${pathname}`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
        const res = await fetch(url, {
            method: body ? 'POST' : 'GET',
            headers: body ? { 'Content-Type': 'application/json' } : undefined,
            body: body ? JSON.stringify(body) : undefined,
            signal: ctrl.signal,
        });
        const json = await res.json().catch(() => ({}));
        return { status: res.status, json };
    } finally {
        clearTimeout(timer);
    }
}

// ───────────────────────── Checks ─────────────────────────
async function main() {
    console.log('🔎 Gemini API 연결 확인\n');

    const cfg = loadGeminiConfig();
    if (!cfg.apiKey) {
        console.error('❌ GEMINI_API_KEY 를 찾지 못했습니다.');
        console.error('   설정 위치 (우선순위 순):');
        console.error('   1) 환경변수 GEMINI_API_KEY');
        console.error(`   2) ${path.join(COMPANY_DIR, '_agents', 'business', 'tools', 'gemini_account.json')}`);
        console.error(`   3) ${path.join(COMPANY_DIR, '_agents', 'business', 'config.md')} 의 GEMINI_API_KEY: 라인`);
        console.error('   키 발급: https://aistudio.google.com/apikey');
        process.exit(1);
    }
    const textModel = cfg.textModel || DEFAULT_TEXT_MODEL;
    const imageModel = cfg.imageModel || DEFAULT_IMAGE_MODEL;
    console.log(`   키: ${mask(cfg.apiKey)}  (출처: ${cfg.source})`);
    console.log(`   텍스트 모델: ${textModel}${cfg.textModel ? '' : ' (기본값)'}`);
    console.log(`   이미지 모델: ${imageModel}${cfg.imageModel ? '' : ' (기본값)'}\n`);

    let ok = true;

    /* [1/3] 키 유효성 — 모델 목록 */
    {
        const { status, json } = await callGemini(`models?key=${cfg.apiKey}&pageSize=50`);
        if (status === 200) {
            const n = (json.models || []).length;
            console.log(`✅ [1/3] 키 유효 — 모델 목록 조회 성공 (${n}개 반환)`);
        } else {
            ok = false;
            console.error(`❌ [1/3] 키 검증 실패 — HTTP ${status}: ${json.error?.message || '(응답 파싱 실패)'}`);
            if (status === 400 || status === 403) console.error('   → 키가 잘못되었거나 폐기되었습니다. https://aistudio.google.com/apikey 에서 재발급하세요.');
            console.error('\n결론: ❌ Gemini 미연결');
            process.exit(1);
        }
    }

    /* [2/3] 텍스트 생성 — 실제 generateContent 왕복 */
    {
        const { status, json } = await callGemini(
            `models/${textModel}:generateContent?key=${cfg.apiKey}`,
            { contents: [{ parts: [{ text: '연결 테스트. 한국어로 딱 한 문장만 답해줘.' }] }] },
        );
        if (status === 200) {
            const parts = json.candidates?.[0]?.content?.parts || [];
            const text = parts.map((p) => p.text || '').join('').trim();
            const usage = json.usageMetadata?.totalTokenCount;
            console.log(`✅ [2/3] 텍스트 생성 성공 — "${text}"${usage ? ` (${usage} tokens)` : ''}`);
        } else {
            ok = false;
            const msg = json.error?.message || '';
            console.error(`❌ [2/3] 텍스트 생성 실패 — HTTP ${status}: ${msg.slice(0, 200)}`);
            if (status === 404) console.error(`   → 모델 '${textModel}' 접근 불가. 신규 키는 구형 모델이 막혀 있으니 gemini-3.x 계열로 설정하세요.`);
            if (status === 429) console.error('   → quota 초과. 무료 tier 한도이거나 요청이 몰린 상태 — 잠시 후 재시도.');
        }
    }

    /* [3/3] 이미지 모델 — 무료 tier 는 quota 0 이라 429 가 정상. 경고로만 처리. */
    {
        const { status, json } = await callGemini(
            `models/${imageModel}:generateContent?key=${cfg.apiKey}`,
            { contents: [{ parts: [{ text: '작은 파란 원 하나만 있는 단순한 이미지' }] }] },
        );
        if (status === 200) {
            const parts = json.candidates?.[0]?.content?.parts || [];
            const img = parts.find((p) => p.inlineData);
            console.log(`✅ [3/3] 이미지 생성 성공${img ? ` — ${img.inlineData.mimeType}` : ''}`);
        } else if (status === 429 && /free_tier/.test(json.error?.message || '')) {
            console.log(`⚠️  [3/3] 이미지 모델 '${imageModel}' — 무료 tier quota 없음 (텍스트 연동에는 영향 없음. 이미지 생성이 필요하면 결제 설정).`);
        } else {
            /* 이미지 실패는 연결 자체의 실패로 보지 않음 — 경고만 */
            console.log(`⚠️  [3/3] 이미지 모델 확인 실패 — HTTP ${status}: ${(json.error?.message || '').slice(0, 150)}`);
        }
    }

    console.log(`\n결론: ${ok ? '✅ Gemini 정상 연결' : '❌ 연결 문제 있음 (위 항목 참고)'}`);
    process.exit(ok ? 0 : 1);
}

main().catch((e) => {
    console.error(`❌ 네트워크/실행 오류: ${e.message}`);
    console.error('   인터넷 연결 또는 프록시 설정을 확인하세요.');
    process.exit(1);
});
