const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  AlignmentType, BorderStyle, ShadingType, TableRow, TableCell,
  Table, WidthType, NumberFormat, PageBreak, UnderlineType,
} = require('docx');
const fs = require('fs');

// ── helpers ──────────────────────────────────────────────────────────────────

const H1 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 360, after: 120 },
});

const H2 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 280, after: 80 },
});

const H3 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 200, after: 60 },
});

const P = (text, opts = {}) => new Paragraph({
  children: [new TextRun({ text, size: 22, ...opts })],
  spacing: { before: 60, after: 100 },
});

const MONO = (text) => new Paragraph({
  children: [new TextRun({ text, font: 'Courier New', size: 20, color: '1a1a2e' })],
  spacing: { before: 40, after: 40 },
  indent: { left: 720 },
});

const BULLET = (text, bold_prefix = '') => new Paragraph({
  children: [
    ...(bold_prefix ? [new TextRun({ text: bold_prefix, bold: true, size: 22 })] : []),
    new TextRun({ text, size: 22 }),
  ],
  bullet: { level: 0 },
  spacing: { before: 40, after: 40 },
});

const NOTE = (text) => new Paragraph({
  children: [new TextRun({ text: '⚠  ' + text, size: 20, color: 'b45309', italics: true })],
  spacing: { before: 80, after: 80 },
  indent: { left: 360 },
  border: {
    left: { style: BorderStyle.SINGLE, size: 18, color: 'f59e0b', space: 8 },
  },
});

const HR = () => new Paragraph({
  text: '',
  spacing: { before: 160, after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'cccccc' } },
});

const SPACE = (pt = 120) => new Paragraph({ text: '', spacing: { before: 0, after: pt } });

// Two-column key/value table (label | value)
const KVTable = (rows) => new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [2880, 6480],
  borders: {
    top:          { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    bottom:       { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    left:         { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    right:        { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    insideH:      { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    insideV:      { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
  },
  rows: rows.map(([label, value], i) => new TableRow({
    children: [
      new TableCell({
        width: { size: 2880, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: i % 2 === 0 ? 'f9fafb' : 'ffffff' },
        children: [new Paragraph({
          children: [new TextRun({ text: label, bold: true, size: 20, color: '374151' })],
          spacing: { before: 60, after: 60 },
          indent: { left: 100 },
        })],
      }),
      new TableCell({
        width: { size: 6480, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: i % 2 === 0 ? 'f9fafb' : 'ffffff' },
        children: [new Paragraph({
          children: [new TextRun({ text: value, size: 20, font: typeof value === 'string' && value.startsWith('maqayis') ? 'Courier New' : undefined })],
          spacing: { before: 60, after: 60 },
          indent: { left: 100 },
        })],
      }),
    ],
  })),
});

// Coverage table
const CoverageTable = () => new Table({
  width: { size: 9360, type: WidthType.DXA },
  columnWidths: [1440, 2160, 1800, 3960],
  borders: {
    top:     { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    bottom:  { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    left:    { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    right:   { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    insideH: { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
    insideV: { style: BorderStyle.SINGLE, size: 4, color: 'e5e7eb' },
  },
  rows: [
    // header
    new TableRow({
      tableHeader: true,
      children: ['PDF', 'Pages', 'Roots', 'Content'].map(h => new TableCell({
        width: { size: [1440,2160,1800,3960][['PDF','Pages','Roots','Content'].indexOf(h)], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: '1e3a5f' },
        children: [new Paragraph({
          children: [new TextRun({ text: h, bold: true, size: 20, color: 'ffffff' })],
          spacing: { before: 80, after: 80 },
          indent: { left: 100 },
        })],
      })),
    }),
    ...([
      ['01.pdf', '48', '0 (†)',  "Front matter only — publisher's preface, second edition preface, Ibn Faris introduction. No lexical content."],
      ['02.pdf', '~410', '~580', 'ح  ·  خ'],
      ['03.pdf', '~410', '~580', 'د  ·  ذ  ·  ر  ·  ز  ·  س  ·  ش'],
      ['04.pdf', '~410', '~580', 'ص  ·  ض  ·  ط  ·  ظ  ·  ع  ·  غ'],
      ['05.pdf', '~410', '~580', 'ف  ·  ق  ·  ك  ·  ل'],
      ['06.pdf', '~410', '~580', 'م  ·  ن  ·  ه  ·  و  ·  ي'],
    ]).map(([pdf, pages, roots, content], i) => new TableRow({
      children: [pdf, pages, roots, content].map((cell, ci) => new TableCell({
        width: { size: [1440,2160,1800,3960][ci], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: i % 2 === 0 ? 'ffffff' : 'f9fafb' },
        children: [new Paragraph({
          children: [new TextRun({ text: cell, size: 19, font: ci === 3 ? undefined : undefined })],
          spacing: { before: 60, after: 60 },
          indent: { left: 100 },
        })],
      })),
    })),
  ],
});

// ── document ──────────────────────────────────────────────────────────────────

const doc = new Document({
  styles: {
    paragraphStyles: [
      {
        id: 'Normal',
        name: 'Normal',
        run: { font: 'Calibri', size: 22, color: '111827' },
      },
      {
        id: 'Heading1',
        name: 'Heading 1',
        basedOn: 'Normal',
        run: { bold: true, size: 32, color: '1e3a5f' },
      },
      {
        id: 'Heading2',
        name: 'Heading 2',
        basedOn: 'Normal',
        run: { bold: true, size: 26, color: '1e3a5f' },
      },
      {
        id: 'Heading3',
        name: 'Heading 3',
        basedOn: 'Normal',
        run: { bold: true, size: 23, color: '374151' },
      },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: 12240, height: 15840 } },
      margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
    },
    children: [

      // ── TITLE PAGE ────────────────────────────────────────────────────────

      new Paragraph({
        children: [new TextRun({ text: 'Maqayis Integration', bold: true, size: 52, color: '1e3a5f' })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 1440, after: 240 },
      }),
      new Paragraph({
        children: [new TextRun({ text: 'Handoff — Hokom Engineering', size: 28, color: '6b7280' })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 120 },
      }),
      new Paragraph({
        children: [new TextRun({ text: 'مقاييس اللغة · Ibn Faris lexical evidence wired into Taaqol', size: 24, color: '9ca3af', italics: true })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 2400 },
      }),

      HR(),

      // ── 1. WHAT WAS BUILT ─────────────────────────────────────────────────

      H1('1. What Was Built'),

      P("Maqayis al-Lugha (مقاييس اللغة) — Ibn Faris's 10th-century Arabic root dictionary — has been OCR'd, parsed, and wired into the Taaqol evidence pipeline as a supplementary lexical evidence source. When Hokom identifies a root in a token, Taaqol Stage 0 now receives Ibn Faris's semantic-origin and bab classifications for that root alongside the standard admission evidence."),

      SPACE(),

      H2('1.1 Components Delivered'),

      BULLET(' — Apple Vision OCR pipeline (Swift + Python) over 6 PDFs, 2,461 pages', 'OCR pipeline'),
      BULLET(' — Classified JSONL corpus: 3,486 root entries with semantic-origin types and bab letters', 'Corpus'),
      BULLET(' — In-memory registry (maqayis_root_registry.py) with O(1) root lookup', 'Registry'),
      BULLET(' — Evidence adapter (maqayis_evidence_adapter.py) — root extraction and evidence ID generation', 'Adapter'),
      BULLET(' — Taaqol wiring: evidence_adapter.py + full_target_orchestrator.py updated to classify and propagate Maqayis IDs', 'Taaqol wiring'),

      SPACE(),

      // ── 2. CORPUS ─────────────────────────────────────────────────────────

      H1('2. Corpus'),

      H2('2.1 Run Stats'),
      SPACE(80),
      KVTable([
        ['Total PDFs',       '6  (01.pdf – 06.pdf)'],
        ['Pages processed',  '2,461'],
        ['Lines extracted',  '52,513'],
        ['Root entries',     '3,486'],
        ['Semantic origins', '1,691  (detected automatically)'],
        ['OCR errors',       '0  (run_manifest.json)'],
        ['DPI',              '400'],
        ['OCR engine',       'Apple Vision (ar-SA), two passes: raw + corrected'],
      ]),

      SPACE(160),

      H2('2.2 PDF Coverage'),
      SPACE(80),
      CoverageTable(),

      SPACE(120),
      new Paragraph({
        children: [new TextRun({ text: '† PDF 01 contains zero lexical entries. The handful of apparent root hits (e.g. جو on p. 44) are incidental in-text mentions within the introduction, not actual root chapters.', size: 19, italics: true, color: '6b7280' })],
        spacing: { before: 80, after: 80 },
      }),

      SPACE(),

      H2('2.3 Missing Volumes — ا ب ت ث ج'),

      NOTE('The chapters for ا, ب, ت, ث, and ج are ABSENT from the six PDFs. This is a missing physical volume, not an OCR failure. Approximately 465 roots are unrepresented. The only remedy is obtaining the missing volume PDF(s).'),

      SPACE(80),

      P('Evidence of the gap: PDF 02, page 3 opens directly with كتاب الحَاء (the ح chapter). The ا–ج portion of the dictionary was in a separate volume not included in this set. Until that volume is scanned and processed, Maqayis lookups for roots beginning with ا, ب, ت, ث, or ج will silently return empty tuples — by design, per the fail-open contract.'),

      SPACE(),

      // ── 3. DATA LOCATION ──────────────────────────────────────────────────

      H1('3. Data Location'),
      SPACE(80),
      KVTable([
        ['Root entries JSONL',   'data/maqaees/full/root_entries.jsonl'],
        ['Page JSON files',      'data/maqaees/full/{pdf_stem}/{pdf_stem}_p{n}_page.json'],
        ['Run manifest',         'data/maqaees/full/run_manifest.json'],
        ['OCR Swift source',     'tools/maqayis_ocr/vision_ocr.swift'],
        ['OCR shell runner',     'tools/maqayis_ocr/run_full.sh'],
        ['Entry parser',         'tools/maqayis_ocr/entry_parser.py'],
      ]),

      SPACE(160),

      H2('3.1 root_entries.jsonl Schema'),

      P('Each line is a JSON object with the following fields:'),

      BULLET(': "01.pdf:p3:r001"  — unique per entry', 'entry_id'),
      BULLET(': "حد"  — undiacritized Arabic consonants', 'root_letters'),
      BULLET(': "الحاء"  — first-radical chapter letter (Arabic full name)', 'bab_letter'),
      BULLET(': "أصل واحد"  — matched phrase from text (stripped of diacritics)', 'semantic_origin_text'),
      BULLET(': SINGULAR | DUAL | TRIPLE | MULTIPLE | SOUND_ROOTS | NONE', 'semantic_origin_type'),
      BULLET(': integer or null  — explicit count when expressed in text', 'origin_count'),
      BULLET(': "AUTO_AGREED" | "REVIEW_REQUIRED"', 'review_status'),
      BULLET(': false — not yet human-reviewed', 'human_verified'),

      SPACE(),

      // ── 4. ARCHITECTURE ───────────────────────────────────────────────────

      H1('4. Architecture'),

      H2('4.1 Data Flow'),

      P('At Taaqol admission time, the per-token flow is:'),

      SPACE(60),
      MONO('analyze_token_constitutionally(surface)'),
      MONO('    → HokomTaaqolResult'),
      MONO('         .hokom_claim_bundle          ← carries root_claim.canonical_root'),
      MONO('         .admission'),
      MONO(''),
      MONO('augment_evidence_from_bundle(bundle)'),
      MONO('    → extract_root_letters_from_bundle(bundle)  ← joins canonical_root radicals'),
      MONO('    → get_maqayis_evidence_ids(root_letters)    ← registry lookup'),
      MONO('    → tuple[str, ...]                           ← evidence IDs or ()'),
      MONO(''),
      MONO('_record_stage_0_from_admission(..., extra_evidence_ids=maqayis_ids)'),
      MONO('    → StageExecutionRecord.evidence_ids = maqayis_ids'),
      SPACE(60),

      H2('4.2 Module Map'),
      SPACE(80),
      KVTable([
        ['maqayis_root_registry.py',    'Loads root_entries.jsonl once at import time; exposes lookup(root_letters) → MaqayisRootEntry | None'],
        ['maqayis_evidence_adapter.py', 'extract_root_letters_from_bundle, get_maqayis_evidence_ids, augment_evidence_from_bundle'],
        ['evidence_adapter.py',         'EVIDENCE_TYPES list + _classify_evidence_id() — updated to recognise maqayis:root:* IDs'],
        ['full_target_orchestrator.py', 'Per-token loop — calls augment_evidence_from_bundle, passes result to Stage 0 record'],
      ]),

      SPACE(),

      // ── 5. API REFERENCE ──────────────────────────────────────────────────

      H1('5. API Reference'),

      H2('5.1 Primary Entry Point'),

      P('The only function callers outside this module need is:'),

      SPACE(60),
      MONO('from pipeline.taaqol_integration.maqayis_evidence_adapter import ('),
      MONO('    augment_evidence_from_bundle,'),
      MONO(')'),
      MONO(''),
      MONO('evidence_ids: tuple[str, ...] = augment_evidence_from_bundle(bundle)'),
      SPACE(60),

      P('Parameters: bundle — a HokomLinguisticClaimBundle (or None).'),
      P('Returns: tuple of evidence ID strings, empty tuple on any failure.'),
      P('Raises: never — fully fail-open.'),

      SPACE(),

      H2('5.2 Low-Level Functions'),
      SPACE(80),
      KVTable([
        ['extract_root_letters_from_bundle(bundle)',   'str | None — joins bundle.root_claim.canonical_root radicals into undiacritized consonants'],
        ['get_maqayis_evidence_ids(root_letters)',     'tuple[str, ...] — hits registry and builds IDs; () if root not found'],
        ['lookup(root_letters)',                       'MaqayisRootEntry | None — raw registry lookup (maqayis_root_registry.py)'],
      ]),

      SPACE(),

      // ── 6. EVIDENCE IDS ───────────────────────────────────────────────────

      H1('6. Evidence IDs'),

      H2('6.1 Format'),

      P('Each root generates up to two evidence IDs:'),

      SPACE(60),
      MONO('# Semantic-origin classification (always emitted when root found):'),
      MONO('maqayis:root:{root_letters}:origin:{origin_type}:count:{n|none}'),
      MONO(''),
      MONO('# Chapter letter (emitted when bab_letter is non-empty):'),
      MONO('maqayis:root:{root_letters}:bab:{bab_letter}'),
      SPACE(60),

      P('Examples:'),
      MONO('maqayis:root:حد:origin:SINGULAR:count:1'),
      MONO('maqayis:root:حد:bab:الحاء'),
      MONO('maqayis:root:كتب:origin:DUAL:count:2'),
      MONO('maqayis:root:وجد:origin:MULTIPLE:count:none'),

      SPACE(),

      H2('6.2 Origin Types'),
      SPACE(80),
      KVTable([
        ['SINGULAR',    'أصل واحد — one semantic root'],
        ['DUAL',        'أصلان / كلمتان — two semantic roots'],
        ['TRIPLE',      'ثلاثة أصول — three semantic roots'],
        ['MULTIPLE',    'أربعة أصول and higher, or bare أصول (count may be None)'],
        ['SOUND_ROOTS', 'أصول صحيحة — sound roots marker (no count)'],
        ['NONE',        'Pattern not found in heading or first body lines (review_status = REVIEW_REQUIRED)'],
      ]),

      SPACE(),

      H2('6.3 Evidence Type in Taaqol'),

      P('All Maqayis IDs classify to the evidence type maqayis_root_catalog_evidence, which is registered in evidence_adapter.EVIDENCE_TYPES. This is distinct from root_catalog_evidence (Hokom-internal) so downstream analytics can filter by source.'),

      SPACE(60),
      MONO('_classify_evidence_id("maqayis:root:حد:origin:SINGULAR:count:1")'),
      MONO('  → "maqayis_root_catalog_evidence"'),
      SPACE(60),

      NOTE('The classifier checks eid.lower().startswith("maqayis:root:") first, before the generic root+catalog branch. This ordering must be preserved if _classify_evidence_id is ever refactored.'),

      SPACE(),

      // ── 7. FAIL-OPEN CONTRACT ─────────────────────────────────────────────

      H1('7. Fail-Open Contract'),

      P('Every function in maqayis_evidence_adapter.py catches all exceptions and returns an empty result. A missing or corrupt corpus must never block Taaqol admission. Specifically:'),

      BULLET(' does not raise. Returns () if: bundle is None, root_claim is None, canonical_root is empty, registry lookup throws, or any other exception.', 'augment_evidence_from_bundle(bundle)'),
      BULLET(' does not raise. Returns () if: root_letters is empty or None, root not found in corpus, or lookup throws.', 'get_maqayis_evidence_ids(root_letters)'),
      BULLET(': if the entire registry fails to load, lookup() returns None silently.', 'Registry failure'),

      SPACE(80),

      P('In full_target_orchestrator.py the guard is:'),
      MONO('maqayis_ids = augment_evidence_from_bundle(bundle) if bundle is not None else ()'),

      P('This means Stage 0 records always have evidence_ids as a tuple (possibly empty). A missing Maqayis result never mutates the admission verdict, rank, or residual codes — those come exclusively from the admission object.'),

      SPACE(),

      // ── 8. KNOWN ISSUES ───────────────────────────────────────────────────

      H1('8. Known Issues'),

      H2('8.1 Wrong bab_letter on ~67 Entries'),

      P('The OCR entry parser\'s extract_bab_letter() uses RE_BAB_LETTER.search(text), which finds the first Arabic letter name in the heading. When the first radical\'s name is OCR-corrupted (e.g. الخاء → انداء), the regex picks up the second radical\'s name (والباء) instead.'),

      P('Result: approximately 67 entries in root_entries.jsonl have bab_letter set to the wrong chapter letter (الباء, التاء, etc.) when the entry actually belongs to ح, خ, ط, etc.'),

      P('Impact: the bab ID (maqayis:root:…:bab:الباء) is incorrect for those entries. The origin ID (maqayis:root:…:origin:…) is unaffected and correct.'),

      NOTE('Fix: a post-processing script should overwrite bab_letter = BAB_LETTER_MAP.get(first_letter_of_root_letters). This is safe because root_letters is always correctly extracted from the parenthesised form. The fix has not been applied to the current JSONL; it should be run before the registry is regenerated.'),

      SPACE(),

      H2('8.2 REVIEW_REQUIRED Entries'),

      P('1,795 entries (51%) carry review_status = REVIEW_REQUIRED. Most have a valid root and bab but the semantic-origin phrase was not found on the heading line or the first few body lines. They default to semantic_origin_type = NONE and origin_count = null.'),

      P('These entries still produce a bab ID but no origin ID. They are not errors — human review would fill in the correct type.'),

      SPACE(),

      // ── 9. RE-RUNNING THE OCR ─────────────────────────────────────────────

      H1('9. Re-Running the OCR Pipeline'),

      P('To regenerate the corpus (e.g. after obtaining the missing ا–ج volume):'),

      SPACE(60),
      MONO('cd hokom/'),
      MONO('bash tools/maqayis_ocr/run_full.sh \\'),
      MONO('    --dpi 400 \\'),
      MONO('    --mode full \\'),
      MONO('    --out data/maqaees/full/'),
      SPACE(60),

      P('The shell script orchestrates: Swift OCR binary → Python pipeline (page_regions.py → entry_parser.py) → JSONL assembly. Output files are pages.jsonl, lines.jsonl, root_entries.jsonl, and run_manifest.json.'),

      P('After regeneration, the in-memory registry reloads automatically on the next process start (or explicit registry.reload()). No other pipeline changes are needed.'),

      SPACE(),

      // ── 10. NEXT STEPS ────────────────────────────────────────────────────

      H1('10. Next Steps'),

      BULLET('Obtain missing PDF volume for ا, ب, ت, ث, ج — contact original publisher or locate a scan of مقاييس اللغة الجزء الأول', '1. Missing volume.'),
      BULLET('Run post-processing script to correct 67 wrong bab_letter values from root_letters[0] before next corpus regen', '2. bab_letter fix.'),
      BULLET('Review the 1,795 REVIEW_REQUIRED entries with a human Arabic linguist to assign correct semantic_origin_type values', '3. Human review.'),
      BULLET('Confirm Taaqol analytics downstream distinguish maqayis_root_catalog_evidence from root_catalog_evidence', '4. Analytics check.'),
      BULLET('Consider enriching body_line_ids content into a corpus_text field for downstream quote retrieval from Ibn Faris definitions', '5. Definition retrieval (optional).'),

      SPACE(240),
      HR(),
      new Paragraph({
        children: [new TextRun({ text: 'Hokom · Maqayis Integration Handoff · 2026-08-03', size: 18, color: '9ca3af' })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 120, after: 0 },
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/root/maqayis_handoff.docx', buf);
  console.log('written');
});
