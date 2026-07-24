# content.json schema for build_report.js

`scripts/build_report.js` renders a styled Korean `.docx` from a single JSON file.
Write the JSON, then run:

```bash
node scripts/build_report.js content.json output.docx
```

The `docx` npm package must be resolvable. If `require('docx')` fails, run
`npm install docx` once in a directory whose `node_modules` the script can see
(run the script from that directory, or install inside the skill folder).

## Top-level fields

| field | type | notes |
|---|---|---|
| `title` | string | cover title (required) |
| `subtitle` | string | grey line under the title |
| `meta` | array of `{label, value}` | cover metadata lines (작성 목적, 검수 상태, 작성일 …) |
| `reliability` | `{stars, score, note}` | e.g. `{"stars":"★★★★☆","score":"4.4 / 5.0","note":"..."}` |
| `toc` | bool | insert a table of contents (Word updates it on open) |
| `sections` | array of Section | body |
| `sources` | array of `[title, url]` (or `{title,url}`) | linked sources section |
| `sourcesTitle` | string | default "참고 · 검증 출처" |

## Section

```json
{
  "h1": "3. 영상별 핵심 내용 정리",
  "intro": "optional paragraph under the H1",
  "pageBreak": true,          // default true; set false to keep on same page
  "blocks": [ ...Block ]
}
```

## Block types

- `{"type":"h2","text":"..."}` / `{"type":"h3","text":"..."}`
- `{"type":"para","text":"..."}` — plain paragraph
- `{"type":"para","runs":[{"t":"굵게","bold":true,"color":"1F3864"},{"t":" 일반"}]}` — mixed runs
- `{"type":"bullet","label":"정의","text":"...","s":5,"q":"선택적 인용문","level":0}`
  - `label` renders bold navy; `s` (1–5) renders a colored **[신뢰도 N/5]** chip
    (5=green, 4=blue, 3=amber); `q` adds an accent-bar quote line; `level` 0/1 nesting.
- `{"type":"quote","text":"..."}` — standalone accent-bar quote
- `{"type":"table","header":["구분","방향성","액션"],"widths":[1500,3000,4620],"rows":[["1","...","..."]],"boldFirst":true}`
  - `widths` are DXA (twips); on A4 with default margins the usable width ≈ 9120.

## Worked example (minimal)

```json
{
  "title": "통합 기획 · 사업 전략 지침서",
  "subtitle": "1인 기업 · 전략 · 기획 프레임워크",
  "meta": [
    {"label":"작성 목적","value":"영상 7편을 검수·정리한 실무 지침서"},
    {"label":"검수 상태","value":"3회 교차 검수 완료"}
  ],
  "reliability": {"stars":"★★★★☆","score":"4.1 / 5.0","note":"전략 이론은 검증, 개별 실적은 자기 보고"},
  "toc": true,
  "sections": [
    {
      "h1": "1. 보고서 개요",
      "blocks": [
        {"type":"para","runs":[{"t":"핵심: ","bold":true,"color":"1F3864"},{"t":"검증된 승리 모델을 나의 강점으로 재해석하라."}]},
        {"type":"h2","text":"핵심 프레임"},
        {"type":"bullet","label":"승리 이론","text":"고객의 선택을 끌어낼 차별화 가설.","s":5,"q":"The essence of strategy is choosing what not to do."}
      ]
    },
    {
      "h1": "2. 검증 및 신뢰도 요약",
      "blocks": [
        {"type":"table","header":["항목","주제","신뢰도"],"widths":[1500,4620,3000],
         "rows":[["①","전략 정의","★★★★★ 5"],["②","AI 발상","★★★☆☆ 3"]],"boldFirst":true}
      ]
    }
  ],
  "sources": [
    ["Roger Martin, Playing to Win (HBR)","https://hbr.org/2014/12/playing-to-win-how-strategy-really-works"]
  ]
}
```

## Verifying the output without a renderer
Some sandboxes have no working LibreOffice/pandoc. The `.docx` is still valid — check it
structurally and tell the user it opens in Word/Google Docs:

```bash
python3 -c "import zipfile,xml.dom.minidom as m; z=zipfile.ZipFile('output.docx'); \
[m.parseString(z.read(n)) for n in ['word/document.xml','word/numbering.xml','word/styles.xml','[Content_Types].xml']]; \
print('valid docx')"
```
