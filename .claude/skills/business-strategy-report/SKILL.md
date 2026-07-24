---
name: business-strategy-report
description: >-
  Consolidate business-planning / idea / strategy source material (screenshots,
  notes, transcripts, URLs, YouTube summaries) into ONE verified, authority-backed
  report scored for reliability. Use this WHENEVER the user wants to organize,
  summarize, fact-check, or upgrade content about 사업 기획, 사업 전략, 아이디어 구상,
  1인 기업/창업, 마인드셋, or business strategy/planning — including requests like
  "이 내용 정리해서 보고서 만들어줘", "검수하고 신뢰도 매겨줘", "권위 있는 사업가 생각 알려줘",
  "turn these notes into a strategy report", "fact-check this business advice", or
  "what do great founders say about X". It carries a curated, source-checked knowledge
  base of 32 authorities (Porter, Drucker, Roger Martin, Christensen, Blue Ocean,
  Rumelt, Paul Graham, Thiel, Andreessen, Blank, The Mom Test, Osterwalder, Hormozi,
  Eric Ries, IDEO, OKR, Sean Ellis, Sinek, Bezos, Musk, Jobs, Naval, Munger/Buffett,
  Hoffman, MrBeast, Seth Godin, Dunford, Sutherland, 정주영, 이병철, 김승호, 김봉진,
  김범수, 김범석) and a 3-pass verification + 5-point reliability method. Apply it even
  when the user doesn't say the word "보고서" but is clearly gathering or vetting
  business/startup ideas.
---

# Business Strategy Report

Turn raw business-planning material into a **single, verified, authority-backed report**
that scores every claim for reliability. Two capabilities travel together:

1. **A curated knowledge base** — 32 of the most authoritative voices on business
   definition, idea generation, planning method, and founder mindset, each item already
   cross-checked and tagged with a 5-point reliability score. Use it to *enrich* and
   *fact-check* whatever the user brings.
2. **A report workflow** — consolidate → verify 3× → score reliability → deliver a
   styled `.docx` (or Markdown / slides on request).

The reason both live in one skill: users rarely just want a summary. They want the
summary *corrected*, *backed by someone credible*, and *rated so they know what to
trust*. That is the whole value — never hand back an unscored, unverified digest.

## When to reach for what

- User pastes/uploads material (screenshots, notes, a YouTube digest, an article) and
  wants it organized/improved → run the **full workflow** below.
- User asks what authoritative people say about strategy / ideas / mindset, or wants to
  fact-check a piece of business advice → answer from the **knowledge base** (`references/`),
  still applying the reliability scoring so they can judge trust.
- User wants a deliverable file → use the **report builder script**.

## Workflow

### 1. Ingest & consolidate
Read every source completely first. For images, read them in full resolution — if a
screenshot is long/small, crop it into vertical chunks and read each (don't guess at
blurry text). Extract the real structure (sections, lists, tables, URLs, numbers)
losslessly before rewriting anything. De-duplicate overlapping points.

### 2. Verify 3× (this is non-negotiable — it's why the user came)
Run three passes over every factual claim, quote, name, number, and framework:
- **Pass 1 — facts:** check names, quotes, dates, figures against primary sources
  (books, HBR, official sites). Use web search; prefer 2+ independent reputable sources.
- **Pass 2 — authority:** confirm each claim is correctly attributed. A quote is only
  fully trusted when confirmed verbatim from the author's own book/talk/post.
- **Pass 3 — overreach:** flag anything widely repeated but weakly sourced, mis-attributed,
  or self-reported (a creator's own sales numbers, a "guru" claim). Downgrade or drop it.

When the source material is large, fan out: spawn parallel research subagents by theme
(strategy theorists / idea generation / execution / mindset / Korean founders / creator
economy), each instructed to verify 3× and return only items scoring ≥3. Then you
re-check and merge. This is how the bundled knowledge base was built.

### 3. Score reliability (5-point scale)
Tag **every** factual item:
- **5/5** — confirmed verbatim in the primary source (book, paper, official channel).
- **4/5** — attributed by multiple reputable secondary sources; strong but not primary-verified.
- **3/5** — widely used, accurate paraphrase; minor wording risk.
- **below 3** — **do not include.** If the user set a threshold ("3점 이상만"), honor it strictly.

Give the report an **overall reliability score** (weighted feel of the parts) and a short
"why not 5.0" note listing what would need first-source confirmation.

Correction discipline: when you drop or downgrade a claim, say so explicitly in a
"검수 결과 · 폐기 항목" section (e.g. the "측정되는 것이 관리된다" Drucker mis-attribution).
Transparency about what you removed is itself a trust signal.

### 4. Enrich with the knowledge base
Connect the user's material to the relevant authorities so their points gain a credible
backbone. The knowledge base is split by theme — read only what's relevant:

| Theme | File |
|---|---|
| 전략의 정의 (Porter, Drucker, R. Martin, Christensen, Blue Ocean, Rumelt) | `references/strategy-theorists.md` |
| 아이디어 발견·검증 (Graham, Thiel, Andreessen, Blank, Mom Test, Osterwalder, Hormozi) | `references/idea-generation.md` |
| 기획·실행 방법론 (Ries, IDEO, OKR, JTBD, Sean Ellis, Sinek) | `references/execution-methods.md` |
| 창업가 마인드셋 (Bezos, Musk, Jobs, Naval, Munger/Buffett, Hoffman) | `references/founder-mindset.md` |
| 크리에이터·1인 사업 (MrBeast, Godin, Dunford, Sutherland, 솔로 크리에이터) | `references/creator-economy.md` |
| 한국 성공 기업가 (정주영, 이병철, 김승호, 김봉진, 김범수, 김범석, 이해진) | `references/korean-entrepreneurs.md` |

Each item already carries a `[신뢰도 N/5]` tag and source. Prefer the highest-scoring,
most on-point authority rather than dumping everyone. If the user's claim contradicts a
5/5 authority item, surface the tension — don't paper over it.

### 5. Deliver
Default output is a styled Korean `.docx`. Build it with the bundled script instead of
hand-writing OOXML — every past run otherwise re-derives the same generator:

```bash
# from the skill directory; needs the `docx` npm package (npm install docx if absent)
node scripts/build_report.js <content.json> <output.docx>
```

Write `content.json` following `references/report-template.md` (schema + a worked
example). The builder renders the cover, optional table of contents, colored
`[신뢰도 N/5]` chips on every scored bullet, summary tables, quote call-outs, and a
linked sources section. Then send the file to the user.

If rendering tools (LibreOffice/pandoc/pdftoppm) are unavailable in the environment, the
`.docx` is still valid — verify it structurally (well-formed XML, expected paragraph/table
counts) and tell the user it opens in Word/Google Docs; don't block on a PDF preview.

On request, adapt the same content into a one-page action checklist, a slide deck (see the
`pptx` skill), or plain Markdown.

## Report structure (default template)

Use this skeleton unless the user wants otherwise:

```
# [제목]
## 1. 보고서 개요 (Executive Summary)          — 목적 + 한 줄 핵심 메시지
## 2. 검증 및 신뢰도 요약                        — 항목별 5점 점수 표 + 종합 점수
## 3. [원본 내용 정리]                          — 소스별/주제별, 손실 없이 정제, 점수 태그
## 4. 권위자 인사이트 보강                        — knowledge base로 근거 강화
## 5. 통합 실행 가이드 (Action Plan)             — 실행 순서 표
## 6. 검수 결과 · 수정/폐기 내역                  — 3-pass 결과, 내린 결정과 이유
참고 · 검증 출처                                 — 링크
```

## Guardrails
- Never invent a quote or a source. If you can't verify, score it low or omit it and say why.
- Keep Korean the primary language when the user writes Korean; keep key English terms in
  parentheses for searchability.
- The knowledge base is a starting point, not a ceiling — for a fresh topic, research and
  verify new authorities the same way, then you may add them to `references/`.
- Match effort to the ask: a quick "what does Thiel say about X" is a knowledge-base lookup,
  not a full report. A pile of screenshots to "정리하고 검수해줘" is the full workflow.
