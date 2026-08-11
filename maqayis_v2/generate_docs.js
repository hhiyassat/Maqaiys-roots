#!/usr/bin/env node
// generate_docs.js — creates maqayis_v2 API documentation for Taaqol

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  PageOrientation, convertInchesToTwip, TableLayoutType,
  LevelFormat, UnderlineType, PageBreak,
} = require('docx');
const fs = require('fs');

// ──────────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────────

const BLUE   = '1F3864';   // dark blue — headings
const LBLUE  = '2E74B5';   // medium blue — sub-headings
const WHITE  = 'FFFFFF';
const LGRAY  = 'F2F2F2';   // alternate row
const DGRAY  = 'D6DCE4';   // table header
const GREEN  = '375623';   // code strings
const PURPLE = '7030A0';   // code keywords
const ORANGE = 'C55A11';   // inline code
const GOLD   = 'C9A227';   // note/tip accent

const rtl = true;

function h1(text) {
  return new Paragraph({
    text,
    heading: HeadingLevel.HEADING_1,
    bidirectional: rtl,
    spacing: { before: 400, after: 160 },
    run: { bold: true, color: BLUE, size: 32 },
  });
}

function h2(text) {
  return new Paragraph({
    text,
    heading: HeadingLevel.HEADING_2,
    bidirectional: rtl,
    spacing: { before: 320, after: 120 },
    run: { bold: true, color: LBLUE, size: 26 },
  });
}

function h3(text) {
  return new Paragraph({
    text,
    heading: HeadingLevel.HEADING_3,
    bidirectional: rtl,
    spacing: { before: 200, after: 80 },
    run: { bold: true, color: LBLUE, size: 22 },
  });
}

function para(runs, opts = {}) {
  const arr = Array.isArray(runs) ? runs : [runs];
  const textRuns = arr.map(r => {
    if (typeof r === 'string') return new TextRun({ text: r, size: 22, font: 'Arial' });
    return new TextRun({ size: 22, font: 'Arial', ...r });
  });
  return new Paragraph({
    children: textRuns,
    bidirectional: rtl,
    alignment: AlignmentType.RIGHT,
    spacing: { before: 60, after: 60 },
    ...opts,
  });
}

function bullet(runs, level = 0) {
  const arr = Array.isArray(runs) ? runs : [runs];
  const textRuns = arr.map(r =>
    typeof r === 'string'
      ? new TextRun({ text: r, size: 21, font: 'Arial' })
      : new TextRun({ size: 21, font: 'Arial', ...r })
  );
  return new Paragraph({
    children: textRuns,
    bidirectional: rtl,
    alignment: AlignmentType.RIGHT,
    bullet: { level },
    spacing: { before: 40, after: 40 },
  });
}

function code(text) {
  // Monospace code block paragraph
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: 'Courier New',
        size: 18,
        color: '1F3864',
      }),
    ],
    alignment: AlignmentType.LEFT,
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'EFF3F9' },
    spacing: { before: 40, after: 40 },
    indent: { left: 360, right: 360 },
  });
}

function inlineCode(text) {
  return new TextRun({
    text: ` ${text} `,
    font: 'Courier New',
    size: 19,
    color: ORANGE,
  });
}

function noteBox(text) {
  return new Paragraph({
    children: [
      new TextRun({ text: '📌  ملاحظة: ', bold: true, size: 21, color: GOLD, font: 'Arial' }),
      new TextRun({ text, size: 21, font: 'Arial' }),
    ],
    bidirectional: rtl,
    alignment: AlignmentType.RIGHT,
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'FFF8E7' },
    spacing: { before: 80, after: 80 },
    indent: { left: 200, right: 200 },
  });
}

function divider() {
  return new Paragraph({
    children: [new TextRun({ text: '' })],
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: DGRAY } },
    spacing: { before: 120, after: 120 },
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function tableHeader(cells) {
  return new TableRow({
    children: cells.map(t =>
      new TableCell({
        children: [new Paragraph({
          children: [new TextRun({ text: t, bold: true, color: WHITE, size: 21, font: 'Arial' })],
          alignment: AlignmentType.CENTER,
          bidirectional: rtl,
        })],
        shading: { type: ShadingType.CLEAR, color: 'auto', fill: BLUE },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        width: { size: Math.floor(9000 / cells.length), type: WidthType.DXA },
      })
    ),
    tableHeader: true,
  });
}

function tableRow(cells, shade = false) {
  return new TableRow({
    children: cells.map((t, i) =>
      new TableCell({
        children: [new Paragraph({
          children: typeof t === 'string'
            ? [new TextRun({ text: t, size: 20, font: 'Arial' })]
            : t,
          alignment: i === 0 ? AlignmentType.CENTER : AlignmentType.RIGHT,
          bidirectional: rtl,
        })],
        shading: shade ? { type: ShadingType.CLEAR, color: 'auto', fill: LGRAY } : undefined,
        margins: { top: 60, bottom: 60, left: 120, right: 120 },
        width: { size: Math.floor(9000 / cells.length), type: WidthType.DXA },
      })
    ),
  });
}

function dataTable(headers, rows) {
  return new Table({
    columnWidths: headers.map(() => Math.floor(9000 / headers.length)),
    width: { size: 9000, type: WidthType.DXA },
    layout: TableLayoutType.FIXED,
    rows: [
      tableHeader(headers),
      ...rows.map((r, i) => tableRow(r, i % 2 === 1)),
    ],
    margins: { top: 0, bottom: 0, left: 0, right: 0 },
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// Document sections
// ──────────────────────────────────────────────────────────────────────────────

const children = [];

// ── Cover / Title ─────────────────────────────────────────────────────────────
children.push(
  new Paragraph({ children: [], spacing: { before: 1440 } }),
  new Paragraph({
    children: [
      new TextRun({ text: 'توثيق واجهة برمجة التطبيقات', bold: true, size: 52, color: BLUE, font: 'Arial' }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 200 },
  }),
  new Paragraph({
    children: [
      new TextRun({ text: 'معجم المقاييس الإلكتروني — النسخة الثانية', bold: true, size: 36, color: LBLUE, font: 'Arial' }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
  }),
  new Paragraph({
    children: [
      new TextRun({ text: 'maqayis_v2 API Documentation for Taaqol Integration', italic: true, size: 26, color: '595959', font: 'Arial' }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { after: 800 },
  }),
  divider(),
  new Paragraph({
    children: [new TextRun({ text: 'مُعَدٌّ لفريق تعقّل  |  Hokom Pipeline Integration', size: 22, color: '595959', font: 'Arial' })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 80 },
  }),
  new Paragraph({
    children: [new TextRun({ text: 'الإصدار: 2.0  —  2026', size: 22, color: '595959', font: 'Arial' })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
  }),
  pageBreak(),
);

// ── 1. مقدمة ──────────────────────────────────────────────────────────────────
children.push(
  h1('١. مقدمة'),
  para([
    'معجم المقاييس الإلكتروني (maqayis_v2) هو نظام قاعدة بيانات مبني على كتاب ',
    { text: 'مقاييس اللغة', bold: true },
    ' لابن فارس (ت٣٩٥هـ)، يُغطِّي ',
    { text: '٤٫٥٤٨', bold: true },
    ' جذراً عربياً مُستخرجاً من مكتبة الشاملة (shamela.ws/book/21710). يُزوِّد هذا النظامُ pipeline تعقّل بأدلةٍ لغوية أصيلة لاختبار الادعاءات الدلالية.',
  ]),
  para([
    'يشتمل النظام على ثلاثة مكوِّنات رئيسية:',
  ]),
  bullet([{ text: 'maqayis.db', bold: true }, ' — قاعدة البيانات (SQLite، 9.1 MB) المحتوية على الجذور والمحاور الدلالية والشواهد الشعرية.']),
  bullet([{ text: 'maqayis_api.py', bold: true }, ' — طبقة الاستعلام المباشر: ٧ عائلات، ١٩ نوع استعلام.']),
  bullet([{ text: 'maqayis_v2_adapter.py', bold: true }, ' — طبقة التكامل مع تعقّل: ٥ دوال جاهزة للاستخدام، مع ضمان Fail-open.']),
);

// ── 2. التثبيت والإعداد ────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٢. التثبيت والإعداد'),
  h2('٢.١ هيكل الملفات'),
  para('يجب أن تكون الملفات في المسارات التالية:'),
  code('~/maqayis/maqayis.db                          ← قاعدة البيانات'),
  code('pipeline/taaqol_integration/maqayis_v2/'),
  code('    ├── maqayis_api.py                        ← API المباشر'),
  code('    ├── maqayis_v2_adapter.py                 ← طبقة التكامل'),
  code('    └── test_api.py                           ← أداة الاختبار'),

  h2('٢.٢ الاستيراد'),
  para('استوردْ دوال الطبقة المباشرة من الموقع التالي:'),
  code('from pipeline.taaqol_integration.maqayis_v2.maqayis_v2_adapter import ('),
  code('    get_root_claims,'),
  code('    get_evidence_ids,'),
  code('    check_claim,'),
  code('    find_roots_by_concept,'),
  code('    get_root_summary,'),
  code(')'),

  h2('٢.٣ المتطلبات'),
  dataTable(['المكوِّن', 'الإصدار', 'ملاحظة'], [
    ['Python', '3.8+', 'لا حاجة لمكتبات إضافية'],
    ['sqlite3', 'مُدمج', 'مكتبة معيارية في Python'],
    ['maqayis.db', '9.1 MB', 'يجب أن يكون في ~/maqayis/'],
  ]),

  noteBox('المسار الافتراضي لقاعدة البيانات هو ~/maqayis/maqayis.db (Path.home() / "maqayis" / "maqayis.db"). لا يحتاج المطوِّر إلى تمرير المسار يدوياً عند استخدام طبقة التكامل.'),
);

// ── 3. طبقة التكامل ───────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٣. طبقة التكامل — maqayis_v2_adapter'),
  para([
    'توفِّر هذه الطبقة ',
    { text: 'خمس دوال', bold: true },
    ' جاهزة للاستخدام المباشر داخل pipeline تعقّل. جميع الدوال تعمل بمبدأ ',
    { text: 'Fail-open', bold: true, color: LBLUE },
    ': أي خطأ في قاعدة البيانات أو في المعجم يُعيد قيمة فارغة بدلاً من رفع استثناء.',
  ]),

  h2('٣.١  get_root_claims'),
  h3('الوصف'),
  para('يعيد ادعاءات ابن فارس عن جذر معيَّن (المحاور الدلالية الأصلية + الدليل النصي).'),
  h3('التوقيع'),
  code('def get_root_claims(root: str) -> list[dict]'),
  h3('المعاملات'),
  dataTable(['المعامل', 'النوع', 'الوصف'], [
    ['root', 'str', 'الجذر العربي (بدون تشكيل، مثل: حكم)'],
  ]),
  h3('المخرج'),
  code('['),
  code('  {'),
  code("    'root_display' : str,    # الجذر كما يظهر في المعجم"),
  code("    'claim_text'   : str,    # نص المحور الدلالي"),
  code("    'claim_rank'   : int,    # ترتيب المحور (١، ٢، ٣...)"),
  code("    'claim_type'   : str,    # SEMANTIC_AXIS | RAW_TEXT_ONLY"),
  code("    'source'       : str,    # IBN_FARIS_DIRECT"),
  code("    'evidence'     : str,    # النص الأصلي من المعجم"),
  code('  }'),
  code(']'),
  h3('مثال'),
  code("claims = get_root_claims('حكم')"),
  code('for c in claims:'),
  code("    print(c['claim_text'], '—', c['evidence'][:80])"),
  code(''),
  code("# مثال على المخرج:"),
  code("# المنع — أصل واحد صحيح، وهو المنع. يُقال: حكَمتُ السَّفيهَ..."),

  divider(),

  h2('٣.٢  get_evidence_ids'),
  h3('الوصف'),
  para('يعيد مُعرِّفات الأدلة بالصيغة المتوافقة مع EvidenceContract في pipeline تعقّل.'),
  h3('التوقيع'),
  code('def get_evidence_ids(root: str) -> tuple[str, ...]'),
  h3('صيغة المُعرِّفات'),
  code('maqayis:v2:{root}:axis:{n}:{axis_text}'),
  code('maqayis:v2:{root}:type:{entry_type}'),
  h3('مثال'),
  code("ids = get_evidence_ids('حكم')"),
  code('# →'),
  code("# ('maqayis:v2:حكم:axis:1:المنع',"),
  code("#  'maqayis:v2:حكم:type:SINGLE_ORIGIN')"),

  divider(),

  h2('٣.٣  check_claim'),
  h3('الوصف'),
  para('يتحقَّق من مدى دعم ابن فارس لادعاءٍ معيَّن عن جذرٍ محدَّد.'),
  h3('التوقيع'),
  code('def check_claim(root: str, claim_text: str) -> str'),
  h3('القيم المُعادة'),
  dataTable(['القيمة', 'المعنى'], [
    ['SUPPORTED', 'الادعاء مدعوم صراحةً في المعجم'],
    ['PARTIALLY_SUPPORTED', 'الادعاء مدعوم جزئياً أو ضمنياً'],
    ['NOT_SUPPORTED', 'الادعاء غير موجود في المعجم'],
    ['ERROR', 'قاعدة البيانات غير متاحة أو حدث خطأ'],
  ]),
  h3('مثال'),
  code("status = check_claim('حكم', 'المنع')"),
  code("# → 'SUPPORTED'"),
  code(''),
  code("status = check_claim('قوم', 'القيام')"),
  code("# → 'SUPPORTED'"),

  divider(),

  h2('٣.٤  find_roots_by_concept'),
  h3('الوصف'),
  para('بحث عكسي: من مفهوم دلالي إلى الجذور التي تشاركه في المعجم.'),
  h3('التوقيع'),
  code('def find_roots_by_concept(concept: str, limit: int = 20) -> list[dict]'),
  h3('المخرج'),
  code('['),
  code('  {'),
  code("    'root_display' : str,"),
  code("    'root_letters' : str,"),
  code("    'matched_axis' : str | None,"),
  code("    'match_type'   : str,"),
  code('  }'),
  code(']'),
  h3('مثال'),
  code("roots = find_roots_by_concept('المنع', limit=5)"),
  code('for r in roots:'),
  code("    print(r['root_display'], '←', r.get('matched_axis', ''))"),
  code(''),
  code('# مثال على المخرج:'),
  code('# حكم ← المنع'),
  code('# حجر ← المنع والحبس'),
  code('# منع ← المنع'),

  divider(),

  h2('٣.٥  get_root_summary'),
  h3('الوصف'),
  para('يعيد ملخصاً شاملاً للجذر: نوع المدخلة، عدد المحاور، النص الكامل.'),
  h3('التوقيع'),
  code('def get_root_summary(root: str) -> Optional[dict]'),
  h3('المخرج'),
  code('{'),
  code("  'found'   : bool,"),
  code("  'root'    : str,"),
  code("  'entries' : ["),
  code('    {'),
  code("      'root_display'  : str,"),
  code("      'entry_type'    : str,    # SINGLE_ORIGIN | MULTI_ORIGIN | ..."),
  code("      'axes_count'    : int,"),
  code("      'axes'          : [str, ...],"),
  code("      'evidence_text' : str,"),
  code("      'ocr_confidence': float,"),
  code('    }'),
  code('  ]'),
  code('}'),
);

// ── 4. API المباشر ─────────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٤. الـ API المباشر — MaqayisAPI'),
  para([
    'للاستخدام المتقدم، يمكن الاستعلام مباشرةً عبر الكلاس ',
    inlineCode('MaqayisAPI'),
    '. يوفِّر ',
    { text: '١٩ نوع استعلام', bold: true },
    ' موزَّعة على ٧ عائلات وظيفية.',
  ]),

  h2('٤.١ التهيئة والاستخدام'),
  code('from maqayis_api import MaqayisAPI'),
  code(''),
  code("api = MaqayisAPI('~/maqayis/maqayis.db')"),
  code('result = api.query({'),
  code("    'query_type': 'ROOT_SEMANTIC_ORIGINS',"),
  code("    'root': 'حكم',"),
  code('})'),
  code('api.close()'),

  h2('٤.٢ بنية الجواب المعياري (Response Envelope)'),
  para('كل استعلام يعيد قاموساً بالبنية التالية:'),
  dataTable(['الحقل', 'النوع', 'الوصف'], [
    ['found', 'bool', 'هل وُجد الجذر في قاعدة البيانات؟'],
    ['query_status', 'str', 'OK | NOT_FOUND | ERROR | UNKNOWN_QUERY_TYPE'],
    ['canonical_root', 'str | None', 'الجذر المُعيَّر بعد إزالة التشكيل'],
    ['results', 'Any', 'البيانات الفعلية (تختلف حسب نوع الاستعلام)'],
    ['source_entry_ids', 'list', 'معرِّفات المصادر المستخدمة'],
    ['review_state', 'str | None', 'حالة المراجعة البشرية (إن وُجدت)'],
    ['confidence', 'float | None', 'مؤشر الثقة (0.0 – 1.0)'],
    ['partial_load', 'bool', 'هل تحميل البيانات جزئي؟'],
    ['error', 'str | None', 'رسالة الخطأ (None عند النجاح)'],
  ]),

  h2('٤.٣ العائلة الأولى — ROOT_LOOKUP'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['ROOT_LOOKUP', 'استرجاع بيانات الجذر الكاملة', 'root'],
    ['ROOT_SEMANTIC_ORIGINS', 'المحاور الدلالية الأصلية لابن فارس', 'root'],
  ]),
  code("api.query({'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': 'شكر'})"),

  h2('٤.٤ العائلة الثانية — ROOT_QUALIFICATION'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['ROOT_EXISTS', 'هل الجذر موجود في المعجم؟', 'root'],
    ['ROOT_CANONICAL_IDENTITY', 'الهوية المعيارية للجذر', 'root'],
    ['ROOT_EXISTENCE_AND_QUALIFICATION', 'الوجود + التصنيف معاً', 'root'],
    ['ENTRY_QUALIFICATION', 'تصنيف المدخلة (SINGLE_ORIGIN...)', 'root'],
  ]),
  code("api.query({'query_type': 'ROOT_EXISTS', 'root': 'عدل'})"),
  code("# results.entry_statuses → ['SINGLE_ORIGIN']"),

  h2('٤.٥ العائلة الثالثة — SEMANTIC_REVERSE_SEARCH'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['SEMANTIC_REVERSE_SEARCH', 'بحث عكسي في المحاور الدلالية', 'concept, limit?'],
    ['CONCEPT_TO_ROOT_SEARCH', 'من مفهوم إلى جذور المعجم', 'concept, limit?'],
  ]),
  code("api.query({"),
  code("    'query_type': 'CONCEPT_TO_ROOT_SEARCH',"),
  code("    'concept': 'المنع',"),
  code("    'limit': 10,"),
  code("})"),

  h2('٤.٦ العائلة الرابعة — CLAIM_EVIDENCE'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['CLAIM_TO_MAQAYIS_EVIDENCE', 'دليل ابن فارس على ادعاء محدد', 'root, claim_text'],
    ['ROOT_MEANING_EVIDENCE_RETRIEVAL', 'استرجاع أدلة معنى الجذر', 'root'],
    ['CLAIM_EVIDENCE', 'تحقق عام من الادعاء', 'root, claim_text'],
  ]),
  code("api.query({"),
  code("    'query_type': 'CLAIM_TO_MAQAYIS_EVIDENCE',"),
  code("    'root': 'قوم',"),
  code("    'claim_text': 'القيام',"),
  code("})"),

  h2('٤.٧ العائلة الخامسة — ROOT_ORIGIN_RELATIONS'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['ROOT_ORIGIN_RELATIONS', 'العلاقات بين الأصول والمشتقات', 'root'],
    ['ROOT_INTERNAL_CONFLICT_LOOKUP', 'تعارض الأصول الداخلي', 'root'],
    ['DERIVATIVE_TO_ORIGIN_ATTESTATION', 'إثبات رجوع المشتق إلى الأصل', 'root'],
  ]),
  code("api.query({'query_type': 'ROOT_ORIGIN_RELATIONS', 'root': 'شكر'})"),

  h2('٤.٨ العائلة السادسة — SOURCE_AND_PROVENANCE'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['SOURCE_EVIDENCE_LOOKUP', 'نص الشاهد الأصلي من المصدر', 'root'],
    ['CLAIM_ATTRIBUTION_LOOKUP', 'نسبة الادعاء إلى مصدره', 'root, claim_text'],
    ['ROOT_SENSE_CANDIDATES', 'مرشَّحات المعنى لجذر مُعيَّن', 'root'],
  ]),
  code("api.query({'query_type': 'ROOT_SENSE_CANDIDATES', 'root': 'حد'})"),

  h2('٤.٩ العائلة السابعة — TRACE_AND_INTEGRITY'),
  dataTable(['نوع الاستعلام', 'الوصف', 'المعاملات'], [
    ['RECORD_INTEGRITY_LOOKUP', 'التحقق من سلامة سجل الجذر', 'root'],
    ['TRACE_LOOKUP', 'تتبُّع أثر الجذر في قاعدة البيانات', 'root'],
    ['ASSERTION_PROVENANCE_CHECK', 'فحص مصدر التأكيدات', 'root'],
  ]),
  code("api.query({'query_type': 'TRACE_LOOKUP', 'root': 'حكم'})"),
);

// ── 5. إحصاءات قاعدة البيانات ─────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٥. إحصاءات قاعدة البيانات'),
  dataTable(['الجدول', 'العدد', 'الوصف'], [
    ['entries', '٤٫٥٤٨', 'إجمالي الجذور المُدخَلة'],
    ['semantic_axes', '٣٫٢٠٠', 'المحاور الدلالية المُستخرَجة'],
    ['poetry_evidence', '٤٫١١٧', 'الأبيات الشعرية الشاهدة'],
    ['source_passages', 'متغيِّر', 'نصوص المصادر الأصلية'],
    ['trace_events', 'متغيِّر', 'أحداث تتبُّع الأمانة'],
  ]),

  h2('٥.١ توزيع أنواع المدخلات'),
  dataTable(['النوع', 'العدد', 'الوصف'], [
    ['SINGLE_ORIGIN', '٢٫٢٤٥', 'جذر بأصل دلالي واحد واضح'],
    ['SINGLE_WORD', '٨٢٢', 'جذر من كلمة واحدة'],
    ['MULTI_ORIGIN', '٤٥٨', 'جذر بأصول دلالية متعددة'],
    ['UNKNOWN', '٨٤٦', 'غير مُصنَّف'],
    ['NO_ROOT_OR_UNCERTAIN', '١٧١', 'غير محدَّد أو مشكوك فيه'],
    ['UNCERTAIN', '٦', 'مشكوك في تصنيفه'],
  ]),

  noteBox('الجذور من نوع SINGLE_ORIGIN هي الأكثر موثوقية للاستدلال الدلالي — يُوصى بالتركيز عليها أولاً عند بناء الادعاءات.'),
);

// ── 6. معالجة النصوص العربية ──────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٦. معالجة النصوص العربية'),
  para([
    'يُعيِّر النظام تلقائياً أي جذر مُدخَل قبل الاستعلام، وذلك عبر الدالة الداخلية ',
    inlineCode('_norm_root()'),
    ':',
  ]),
  dataTable(['التحويل', 'مثال'], [
    ['إزالة التشكيل (diacritics)', 'حُكْم → حكم'],
    ['توحيد الهمزة (أإآ → ا)', 'أحمد → احمد'],
    ['تحويل ى → ي', 'مستوى → مستوي'],
    ['تحويل ة → ه', 'حكمة → حكمه'],
  ]),
  para('أي من هذه الصيغ ستُعطي نفس النتيجة:'),
  code("get_root_claims('حُكْم')   # → نفس نتيجة 'حكم'"),
  code("get_root_claims('حكم')    # ← الصيغة الموصى بها"),
  noteBox('لا يحتاج المستخدم إلى تعيير الجذر يدوياً — يتولى النظام ذلك تلقائياً.'),
);

// ── 7. عقد Fail-open ──────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٧. عقد Fail-open'),
  para([
    'الفلسفة الأساسية لطبقة التكامل: ',
    { text: 'خطأ في المعجم لا يوقف الـ pipeline أبداً.', bold: true },
  ]),
  para('في حالة أي خطأ — غياب قاعدة البيانات، خطأ في الاستعلام، بيانات تالفة — تعيد كل دالة قيمة فارغة:'),
  dataTable(['الدالة', 'القيمة عند الخطأ'], [
    ['get_root_claims()', '[] (قائمة فارغة)'],
    ['get_evidence_ids()', '() (مُجمَّع فارغ)'],
    ['check_claim()', "'ERROR'"],
    ['find_roots_by_concept()', '[] (قائمة فارغة)'],
    ['get_root_summary()', 'None'],
  ]),
  para('النمط الموصى به في الكود:'),
  code("claims = get_root_claims(root)"),
  code("if not claims:"),
  code("    # المعجم غير متاح أو الجذر غير موجود"),
  code("    proceed_without_maqayis()"),
  code("else:"),
  code("    use_claims(claims)"),
);

// ── 8. أمثلة متكاملة ──────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٨. أمثلة متكاملة'),

  h2('٨.١ سيناريو: التحقق من ادعاء دلالي'),
  code('from pipeline.taaqol_integration.maqayis_v2.maqayis_v2_adapter import ('),
  code('    check_claim, get_root_claims'),
  code(')'),
  code(''),
  code("root      = 'حكم'"),
  code("claim     = 'المنع'"),
  code(''),
  code("status = check_claim(root, claim)"),
  code("print(f'الادعاء «{claim}» عن الجذر [{root}]: {status}')"),
  code("# → الادعاء «المنع» عن الجذر [حكم]: SUPPORTED"),
  code(''),
  code('# للاطلاع على الدليل النصي كاملاً:'),
  code('claims = get_root_claims(root)'),
  code('for c in claims:'),
  code("    if c['claim_text'] == claim:"),
  code("        print('الدليل:', c['evidence'][:200])"),

  h2('٨.٢ سيناريو: بناء قائمة أدلة لعقد EvidenceContract'),
  code('from pipeline.taaqol_integration.maqayis_v2.maqayis_v2_adapter import get_evidence_ids'),
  code(''),
  code("roots = ['حكم', 'عدل', 'قوم', 'كتب']"),
  code(''),
  code('evidence_registry = {}'),
  code('for root in roots:'),
  code('    ids = get_evidence_ids(root)'),
  code('    if ids:'),
  code('        evidence_registry[root] = ids'),
  code(''),
  code("# evidence_registry['حكم'] →"),
  code("# ('maqayis:v2:حكم:axis:1:المنع', 'maqayis:v2:حكم:type:SINGLE_ORIGIN')"),

  h2('٨.٣ سيناريو: بحث عكسي من مفهوم إلى جذور'),
  code('from pipeline.taaqol_integration.maqayis_v2.maqayis_v2_adapter import find_roots_by_concept'),
  code(''),
  code("concept = 'الإصلاح'"),
  code("results = find_roots_by_concept(concept, limit=10)"),
  code(''),
  code("print(f'الجذور التي تشمل مفهوم «{concept}»:')"),
  code('for r in results:'),
  code("    axis = r.get('matched_axis') or '—'"),
  code("    print(f\"  {r['root_display']} ← {axis}\")"),

  h2('٨.٤ سيناريو: الاستخدام المباشر عبر MaqayisAPI'),
  code('from maqayis_api import MaqayisAPI'),
  code("DB = '/Users/username/maqayis/maqayis.db'"),
  code(''),
  code('api = MaqayisAPI(DB)'),
  code(''),
  code("# استعلام متعدد"),
  code("roots = ['حكم', 'شكر', 'حد']"),
  code('for root in roots:'),
  code('    r = api.query({'),
  code("        'query_type': 'ROOT_SEMANTIC_ORIGINS',"),
  code("        'root': root,"),
  code('    })'),
  code("    if r['found']:"),
  code("        axes = r['results'].get('axes', [])"),
  code("        print(f'{root}: {len(axes)} محاور — {axes[:2]}')"),
  code(''),
  code('api.close()'),
);

// ── 9. اختبار التشغيل ─────────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('٩. اختبار التشغيل'),
  h2('٩.١ الاختبار السريع — test_api.py'),
  para('الأداة تقع في نفس مجلد maqayis_v2 وتقبل ثلاث صيغ تشغيل:'),
  dataTable(['الأمر', 'الوظيفة'], [
    ['python3 test_api.py', 'تشغيل كل الأمثلة (٨ استعلامات)'],
    ['python3 test_api.py حكم', 'ROOT_SEMANTIC_ORIGINS لجذر محدَّد'],
    ['python3 test_api.py --concept المنع', 'بحث عكسي CONCEPT_TO_ROOT_SEARCH'],
  ]),
  code('$ python3 test_api.py حكم'),
  code('════════════════════════════════════════════════════════════'),
  code('  ROOT_SEMANTIC_ORIGINS — حكم'),
  code('════════════════════════════════════════════════════════════'),
  code('{'),
  code('  "found": true,'),
  code('  "query_status": "OK",'),
  code('  "results": {'),
  code('    "axes": ["المنع"],'),
  code('    "evidence": "أصل واحد صحيح، وهو المنع..."'),
  code('  }'),
  code('}'),

  h2('٩.٢ الاختبار عبر maqayis_v2_adapter.py'),
  code('$ python3 maqayis_v2_adapter.py'),
  code('قاعدة البيانات: /Users/username/maqayis/maqayis.db'),
  code('متاحة: True'),
  code(''),
  code('══ حكم ══'),
  code('  ادعاء: المنع'),
  code('  IDs: ("maqayis:v2:حكم:axis:1:المنع", "maqayis:v2:حكم:type:SINGLE_ORIGIN")'),
  code('  check "المنع": SUPPORTED'),
);

// ── 10. ملخص مرجعي سريع ───────────────────────────────────────────────────────
children.push(
  pageBreak(),
  h1('١٠. ملخص مرجعي سريع'),

  h2('دوال طبقة التكامل'),
  dataTable(['الدالة', 'الغرض', 'المخرج'], [
    ['get_root_claims(root)', 'محاور ابن فارس + الدليل', 'list[dict]'],
    ['get_evidence_ids(root)', 'مُعرِّفات EvidenceContract', 'tuple[str, ...]'],
    ['check_claim(root, claim_text)', 'هل الادعاء مدعوم؟', 'str (SUPPORTED…)'],
    ['find_roots_by_concept(concept, limit)', 'بحث عكسي من مفهوم', 'list[dict]'],
    ['get_root_summary(root)', 'ملخص شامل للجذر', 'Optional[dict]'],
  ]),

  h2('جميع أنواع الاستعلامات'),
  dataTable(['العائلة', 'أنواع الاستعلامات'], [
    ['١. ROOT_LOOKUP', 'ROOT_LOOKUP، ROOT_SEMANTIC_ORIGINS'],
    ['٢. ROOT_QUALIFICATION', 'ROOT_EXISTS، ROOT_CANONICAL_IDENTITY، ROOT_EXISTENCE_AND_QUALIFICATION، ENTRY_QUALIFICATION'],
    ['٣. SEMANTIC_REVERSE_SEARCH', 'SEMANTIC_REVERSE_SEARCH، CONCEPT_TO_ROOT_SEARCH'],
    ['٤. CLAIM_EVIDENCE', 'CLAIM_TO_MAQAYIS_EVIDENCE، ROOT_MEANING_EVIDENCE_RETRIEVAL، CLAIM_EVIDENCE'],
    ['٥. ROOT_ORIGIN_RELATIONS', 'ROOT_ORIGIN_RELATIONS، ROOT_INTERNAL_CONFLICT_LOOKUP، DERIVATIVE_TO_ORIGIN_ATTESTATION'],
    ['٦. SOURCE_AND_PROVENANCE', 'SOURCE_EVIDENCE_LOOKUP، CLAIM_ATTRIBUTION_LOOKUP، ROOT_SENSE_CANDIDATES'],
    ['٧. TRACE_AND_INTEGRITY', 'RECORD_INTEGRITY_LOOKUP، TRACE_LOOKUP، ASSERTION_PROVENANCE_CHECK'],
  ]),

  divider(),
  new Paragraph({
    children: [
      new TextRun({ text: 'نهاية الوثيقة  —  maqayis_v2 API Documentation v2.0', italic: true, color: '595959', size: 18, font: 'Arial' }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 400 },
  }),
);

// ──────────────────────────────────────────────────────────────────────────────
// Build & write
// ──────────────────────────────────────────────────────────────────────────────

const doc = new Document({
  creator: 'Maqayis v2 Documentation Generator',
  title: 'توثيق مقاييس اللغة الإلكتروني — API Reference',
  description: 'وثيقة مرجعية لواجهة البرمجة — معجم المقاييس الإلكتروني النسخة الثانية',
  styles: {
    default: {
      document: {
        run: { font: 'Arial', size: 22, color: '000000' },
        paragraph: { spacing: { line: 340 } },
      },
    },
    paragraphStyles: [
      {
        id: 'Heading1',
        name: 'Heading 1',
        run: { bold: true, size: 32, color: BLUE, font: 'Arial' },
        paragraph: {
          spacing: { before: 400, after: 160 },
          bidirectional: true,
        },
      },
      {
        id: 'Heading2',
        name: 'Heading 2',
        run: { bold: true, size: 26, color: LBLUE, font: 'Arial' },
        paragraph: {
          spacing: { before: 320, after: 120 },
          bidirectional: true,
        },
      },
      {
        id: 'Heading3',
        name: 'Heading 3',
        run: { bold: true, size: 22, color: LBLUE, font: 'Arial' },
        paragraph: {
          spacing: { before: 200, after: 80 },
          bidirectional: true,
        },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: convertInchesToTwip(8.5), height: convertInchesToTwip(11) },
        margin: {
          top: convertInchesToTwip(1),
          right: convertInchesToTwip(1),
          bottom: convertInchesToTwip(1),
          left: convertInchesToTwip(1),
        },
      },
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/root/maqayis_v2/maqayis_v2_api_docs.docx', buffer);
  console.log('✓ Created: maqayis_v2_api_docs.docx');
});
