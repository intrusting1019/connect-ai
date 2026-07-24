#!/usr/bin/env node
/*
 * build_report.js — JSON-driven Korean business-report generator (.docx)
 *
 * Usage:
 *   node build_report.js <content.json> <output.docx>
 *
 * Requires the `docx` npm package. If it is not installed in the current
 * project, run `npm install docx` once (or copy node_modules), then re-run.
 *
 * The JSON schema is documented in references/report-template.md.
 * Every reliability-tagged bullet renders a colored [신뢰도 N/5] chip so the
 * reader can judge trust at a glance — that scoring discipline is the whole
 * point of this skill, so keep the `s` field on factual claims.
 */
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  LevelFormat, PageBreak, ExternalHyperlink, TableOfContents } = require('docx');
const fs = require('fs');

const FONT = "Malgun Gothic";               // Korean-safe; falls back gracefully
const NAVY = "1F3864", BLUE = "2E5496", ACCENT = "C55A11", GREY = "595959";
const LIGHTG = "F2F2F2", GREEN = "2E7D32", AMBER = "B26A00";

const args = process.argv.slice(2);
if (args.length < 2) { console.error("usage: node build_report.js <content.json> <out.docx>"); process.exit(1); }
const spec = JSON.parse(fs.readFileSync(args[0], "utf8"));
const OUT = args[1];

function t(text, o = {}) {
  return new TextRun({ text: String(text), font: FONT, size: o.size || 20, bold: !!o.bold,
    italics: !!o.italics, color: o.color || "222222" });
}
function runsFrom(arr) { // arr of {t,bold,italics,color,size}
  return arr.map(r => t(r.t, r));
}
function P(runs, o = {}) {
  return new Paragraph({ children: Array.isArray(runs) ? runs : [runs],
    spacing: { after: o.after == null ? 120 : o.after, before: o.before || 0, line: o.line || 276 },
    alignment: o.align, indent: o.indent, border: o.border, shading: o.shading });
}
function H1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 340, after: 150 },
    border: { bottom: { color: NAVY, style: BorderStyle.SINGLE, size: 14, space: 4 } },
    children: [new TextRun({ text, font: FONT, size: 30, bold: true, color: NAVY })] });
}
function H2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 90 },
    children: [new TextRun({ text, font: FONT, size: 25, bold: true, color: BLUE })] });
}
function H3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { before: 160, after: 70 },
    children: [new TextRun({ text, font: FONT, size: 22, bold: true, color: "333333" })] });
}
function scoreChip(n) {
  const col = n >= 5 ? GREEN : n >= 4 ? BLUE : AMBER;
  return new TextRun({ text: `  [신뢰도 ${n}/5]`, font: FONT, size: 15, bold: true, color: col });
}
function bullet(b, level = 0) {
  const runs = [];
  if (b.label) runs.push(t(b.label + ": ", { bold: true, color: NAVY }));
  runs.push(t(b.text || ""));
  if (b.s) runs.push(scoreChip(b.s));
  return new Paragraph({ numbering: { reference: "bul", level: level || b.level || 0 },
    spacing: { after: 60, line: 264 }, children: runs });
}
function quote(text) {
  return new Paragraph({ spacing: { after: 60, before: 20 }, indent: { left: 460 },
    border: { left: { color: ACCENT, style: BorderStyle.SINGLE, size: 16, space: 8 } },
    children: [t(text, { italics: true, color: "444444" })] });
}
function cell(children, w, fill) {
  return new TableCell({ width: { size: w, type: WidthType.DXA },
    shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: Array.isArray(children) ? children : [children] });
}
function table(tb) {
  const W = tb.widths, total = W.reduce((a, b) => a + b, 0);
  const rows = [ new TableRow({ tableHeader: true, children: tb.header.map((h, i) =>
    cell(P([t(h, { bold: true, color: "FFFFFF" })], { after: 0 }), W[i], NAVY)) }) ];
  tb.rows.forEach((r, ri) => {
    const fill = ri % 2 ? LIGHTG : undefined;
    rows.push(new TableRow({ children: r.map((c, ci) =>
      cell(P([t(c, { bold: ci === 0 && tb.boldFirst })], { after: 0 }), W[ci], fill)) }));
  });
  return new Table({ width: { size: total, type: WidthType.DXA }, columnWidths: W,
    borders: { top: { style: BorderStyle.SINGLE, size: 2, color: "AAAAAA" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "AAAAAA" },
      left: { style: BorderStyle.SINGLE, size: 2, color: "AAAAAA" },
      right: { style: BorderStyle.SINGLE, size: 2, color: "AAAAAA" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "CCCCCC" } }, rows });
}

const children = [];

// ---- cover ----
children.push(new Paragraph({ spacing: { before: 240, after: 80 },
  children: [new TextRun({ text: spec.title || "보고서", font: FONT, size: 40, bold: true, color: NAVY })] }));
if (spec.subtitle) children.push(new Paragraph({ spacing: { after: 200 },
  children: [new TextRun({ text: spec.subtitle, font: FONT, size: 22, color: GREY })] }));
children.push(new Paragraph({ border: { bottom: { color: ACCENT, style: BorderStyle.SINGLE, size: 18, space: 6 } },
  spacing: { after: 160 }, children: [t("", { size: 2 })] }));
(spec.meta || []).forEach(m => children.push(P([t(m.label + ": ", { bold: true, color: NAVY }), t(m.value)], { after: 60 })));
if (spec.reliability) children.push(P([t("종합 신뢰도: ", { bold: true, color: NAVY }),
  t(spec.reliability.stars + "  " + spec.reliability.score, { bold: true, color: ACCENT }),
  t(spec.reliability.note ? "   " + spec.reliability.note : "")], { after: 60 }));

// ---- optional TOC ----
if (spec.toc) {
  children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(H1("목차"));
  children.push(new TableOfContents("목차", { hyperlink: true, headingStyleRange: "1-2" }));
}

// ---- sections ----
(spec.sections || []).forEach(sec => {
  if (sec.pageBreak !== false) children.push(new Paragraph({ children: [new PageBreak()] }));
  if (sec.h1) children.push(H1(sec.h1));
  if (sec.intro) children.push(P([t(sec.intro)]));
  (sec.blocks || []).forEach(b => {
    switch (b.type) {
      case "h2": children.push(H2(b.text)); break;
      case "h3": children.push(H3(b.text)); break;
      case "para": children.push(P(b.runs ? runsFrom(b.runs) : [t(b.text)], b.opts || {})); break;
      case "bullet": children.push(bullet(b)); if (b.q) children.push(quote(b.q)); break;
      case "quote": children.push(quote(b.text)); break;
      case "table": children.push(table(b)); break;
      default: children.push(P([t(b.text || "")]));
    }
  });
});

// ---- sources ----
if (spec.sources && spec.sources.length) {
  children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(H1(spec.sourcesTitle || "참고 · 검증 출처"));
  spec.sources.forEach(s => {
    const kids = [t((Array.isArray(s) ? s[0] : s.title) + " — ", { size: 18 })];
    const url = Array.isArray(s) ? s[1] : s.url;
    if (url) kids.push(new ExternalHyperlink({ link: url, children: [new TextRun({ text: url, font: FONT, size: 18, color: "0563C1", underline: {} })] }));
    children.push(new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { after: 50 }, children: kids }));
  });
}

const doc = new Document({
  creator: "business-strategy-report skill",
  features: { updateFields: !!spec.toc },
  styles: { default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 30, bold: true, color: NAVY } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 25, bold: true, color: BLUE } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 22, bold: true, color: "333333" } },
    ] },
  numbering: { config: [ { reference: "bul", levels: [
    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 220 } } } },
    { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 220 } } } },
  ] } ] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1100, bottom: 1100, left: 1200, right: 1200 } } }, children }]
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log("written", buf.length, OUT); });
