"""
مرحلة الإثراء — النسخة النهائية
تحوّل shamela_maqayis_entries.jsonl إلى shamela_maqayis_enriched.jsonl
مع استخلاص: semantic_axes، entry_type، quoted_authorities، ocr_confidence
"""

import json, re
from pathlib import Path
from collections import Counter

# ── التطبيع ───────────────────────────────────────────────────────────────────

def strip_diacritics(t: str) -> str:
    """يحذف حروف التشكيل العربية (الحركات والشدة والمد)."""
    return re.sub(r'[ً-ْٰٱ]', '', t)

def norm_alef(t: str) -> str:
    """يوحّد أشكال الألف (أ إ آ → ا) والألف المقصورة (ى → ي)
    والهمزة على الواو (ؤ → و) والهمزة على الياء (ئ → ي)."""
    t = re.sub(r'[أإآ]', 'ا', t)
    t = re.sub(r'ى', 'ي', t)
    t = re.sub(r'ؤ', 'و', t)   # همزة على واو → واو
    t = re.sub(r'ئ', 'ي', t)   # همزة على ياء → ياء
    return t

def normalize(t: str) -> str:
    return norm_alef(strip_diacritics(t))

# ── نمط الحروف في بداية المدخل ───────────────────────────────────────────────
# "الهمزة والجيم" | "الحاء والجيم والزاء" | "الكاف والحرف المعتل"
_LC = r'(?:ال\w{2,6}(?:\s+و(?:ال)?\w{2,6})*(?:\s+و(?:ال)?(?:حرف\s+)?المعتل)?)'

# الفاصل بعد سلسلة الحروف: مسافة عادية أو "فله/فلها" (مع اللام — لا يستهلك "ف" مفردة)
_SEP = r'(?:\s+ف(?:له\s+|لها\s+|لهما\s+)|[\s:،.]+)'

RE_AFTER_LETTERS = re.compile(rf'^{_LC}{_SEP}(.{{1,400}})', re.UNICODE | re.DOTALL)

# بعض المداخل تبدأ بـ "وأما" أو "و" قبل الحروف
RE_AFTER_WAMA = re.compile(
    rf'^(?:وأم?ا?\s+|و){_LC}{_SEP}(.{{1,400}})',
    re.UNICODE | re.DOTALL,
)

# ── أنماط تصنيف الأصول ───────────────────────────────────────────────────────

RE_NOROOT = re.compile(
    r'^(?:كلمة\s+ان\s+صحت|'
    r'ليست?\s+(?:باصل|في\s+هذا|اصلا|بعربية|عربية)|'
    r'فليس\s+باصل|ليس\s+له\s+اصل|لا\s+اصل\s+له|'
    r'فرع\s+(?:ليس|لا)|'          # فرع ليس بأصل
    r'ليس\s+(?:باصل|اصلا|بشئ)(?:\s+(?:ولا|الا|و)|$))',
    re.UNICODE,
)

RE_UNCERT = re.compile(
    r'(?:فيها?\s+نظر|امر\s+مشكل|لا\s+اعرف\s+له\s+اصلا)',
    re.UNICODE,
)

# أصلان / معنيان / وجهان / كلمتان
RE_TWO = re.compile(
    r'^(?:ف?اصلان|ف?معنيان|وجهان|كلمتان|له\s+معنيان|له\s+اصلان|لها\s+اصلان)'
    r'\s*[^:،.]{0,30}?[،:\s]\s*'
    r'(?:احدهما|الاول|احد\s+المعنيين|\[احدهما\])?\s*([^،.]{3,120})'
    r'(?:[،.]\s*(?:والاخر|والثاني|والثانى|الاخر|والمعني\s+الاخر|والكلمة\s+الاخري)\s+([^،.]{3,120}))?',
    re.UNICODE,
)

# ثلاثة أصول / أصول ثلاثة / كلمات ثلاث / له ثلاثة / بناء على أصول ثلاثة
RE_THREE = re.compile(
    r'^(?:ثلاثة\s+اصول?|اصول?\s+ثلاثة|كلمات\s+ثلاث|'
    r'له?\s+ثلاثة\s+اصول?|'
    r'بناء\s+علي\s+اصول\s+ثلاثة|علي\s+اصول\s+ثلاثة|'
    r'علي\s+ثلاثة\s+اصول?)[^:،]{0,50}[،:]?\s*'
    r'(?:\[علي\]\s+)?(?:الاولي?\s+|الاول\s+)?([^،.]{3,120})'
    r'(?:[،.]\s*(?:والثاني?|الثاني?|والاخري?)\s+([^،.]{3,120}))?',
    re.UNICODE,
)

# أصول أربعة / أربعة أصول / لها أربعة
RE_FOUR = re.compile(
    r'^(?:اصول?\s+اربعة|اربعة\s+اصول?|لها\s+اربعة\s+اصول?)[^:،]{0,80}?[،:.\n]\s*'
    r'(?:فالاول|الاول|احدها|وهي)\s*[:\s]\s*([^.،\n]{3,120})',
    re.UNICODE,
)

# أصل واحد ، وهو / يدل على — وأصيل يدل على — وقياس واحد
RE_SINGLE = re.compile(
    r'^(?:\*?\s*)?'
    r'(?:في\s+المضاعف\s+|قريب\s+من\s+\w+\s+)?'
    r'(?:'
    # نمط 1: أصيل يدل على X
    r'اصيل\s+(?:يدل|تدل)\s+علي?\s+([^.\n]{3,150})'
    r'|'
    # نمط 2: أصل [واحد/صحيح/...] [تفاصيل] ، وهو/يدل على X
    r'(?:ف?اصيل?|ف?اصل\s+(?:واحد|صحيح|مطرد|[^،:]{0,30})?|قياس\s+واحد\s+و?اصل\s+(?:واحد)?)'
    r'(?:[^،:.]{0,80}?)'
    r'(?:(?:،|:|\.)\s*\n?\s*'
    r'(?:وهو|وهي|وهى|يدل\s+علي?|تدل\s+علي?|فال\w+\s*:\s*|فالمعني\s+)'
    r'\s*([^.\n]{3,150}))'
    r')',
    re.UNICODE,
)

# يدلّ على X / تدلّ على X / يدلّ بناؤها على X — بلا كلمة "أصل" صريحة
RE_YADULL = re.compile(
    r'^(?:\*?\s*)?(?:يدل|تدل)(?:\s+بناوها?)?\s+علي?\s+([^.\n]{3,150})',
    re.UNICODE,
)

# كلمة تدلّ على X
RE_WORD = re.compile(
    r'^كلمة\s*(?:واحدة)?\s+(?:تدل|يدل)\s+علي?\s+([^.،\n]{3,120})',
    re.UNICODE,
)

# معظم بابه X
RE_MAAZAM = re.compile(r'^معظم\s+بابه\s+([^.،\n]{3,100})', re.UNICODE)

# ── أعلام يُنقل عنهم ─────────────────────────────────────────────────────────
AUTHORITY_NAMES = [
    'الخليل', 'ابن دريد', 'أبو عبيدة', 'الأصمعي', 'أبو زيد',
    'الفراء', 'ابن الأعرابي', 'سيبويه', 'المبرد', 'ثعلب',
    'قطرب', 'الكسائي', 'أبو عمرو', 'الليث', 'الجوهري',
    'أبو بكر', 'ابن السكيت', 'أبو عمر', 'ابن قتيبة',
]
RE_AUTHORITIES = re.compile(
    '|'.join(re.escape(a) for a in AUTHORITY_NAMES), re.UNICODE
)

# ── OCR ──────────────────────────────────────────────────────────────────────
RE_OCR_SUSPECT = re.compile(r'[^؀-ۿ\s\w\d،.:؟!()«»\[\]٠-٩\-/\n*]')

# ── دوال ──────────────────────────────────────────────────────────────────────

def _clean(t: str) -> str:
    return re.sub(r'\s+', ' ', (t or '').strip())

def _restore(normalized_text: str, original: str) -> str:
    """يعيد النص الأصلي المقابل للجزء المُطبَّع (تقريبي — للعرض فقط)."""
    # نستخدم النص المطبَّع للتصنيف، لكن نخزّن النص الأصلي في المخرجات
    return _clean(normalized_text)


def extract_axes(body: str) -> dict:
    """يستخلص الأصول المعنوية من body_text."""

    # ١. تنظيف أولي: إزالة النجوم العشوائية (OCR artefacts) من سلسلة الحروف
    body_clean = re.sub(r'\s*\*\s*', ' ', body)
    body_clean = re.sub(r'\s+', ' ', body_clean).strip()

    # ١ب. استخراج ما بعد أسماء الحروف
    # نحذف التشكيل فقط (ونبقي الهمزات) لأنماط سلسلة الحروف، ثم نطبّع المجموعة للتصنيف
    body_stripped = strip_diacritics(body_clean)  # يحذف الحركات ويبقي أ/إ/آ/ؤ/ئ
    m = RE_AFTER_LETTERS.match(body_stripped) or RE_AFTER_WAMA.match(body_stripped)
    after_orig = m.group(1).strip() if m else body_stripped.strip()
    after = normalize(after_orig)  # تطبيع الهمزات والألف المقصورة للتصنيف

    # ١ج. حذف البوادئ السياقية التي لا تُعدّ تصنيفاً
    # "فى المضاعف فأصلان" → "فأصلان"
    # "مضاعفة فأصل واحد" → "فأصل واحد"
    # "وما بعدهما من المعتل أصلان" → "أصلان"
    after = re.sub(r'^في\s+المضاعف\s*', '', after).strip()
    after = re.sub(r'^مضاعف[ةه]?\s*', '', after).strip()
    after = re.sub(r'^(?:وما|ما)\s+بعده?(?:ما|م)?\s+(?:من\s+)?المعتل?\s*', '', after).strip()

    # ٢. حالات خاصة: لا أصل / غامض
    if RE_NOROOT.match(after):
        return {'axes': [], 'axes_count': 0, 'entry_type': 'NO_ROOT_OR_UNCERTAIN'}
    if RE_UNCERT.search(after[:100]):
        return {'axes': [], 'axes_count': None, 'entry_type': 'UNCERTAIN'}

    axes = []
    axes_count = None
    entry_type = 'UNKNOWN'

    # ٣. أصلان / معنيان / وجهان
    m2 = RE_TWO.match(after)
    if m2:
        axes_count = 2
        entry_type = 'MULTI_ORIGIN'
        for g in [m2.group(1), m2.group(2)]:
            if g and g.strip():
                axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٤. ثلاثة أصول
    elif RE_THREE.match(after):
        m3 = RE_THREE.match(after)
        axes_count = 3
        entry_type = 'MULTI_ORIGIN'
        for g in [m3.group(1), m3.group(2)]:
            if g and g.strip():
                axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٥. أصول أربعة
    elif RE_FOUR.match(after):
        m4 = RE_FOUR.match(after)
        axes_count = 4
        entry_type = 'MULTI_ORIGIN'
        if m4.group(1):
            axes.append({'text': _clean(m4.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٦. أصل واحد / أصيل
    elif RE_SINGLE.match(after):
        ms = RE_SINGLE.match(after)
        axes_count = 1
        entry_type = 'SINGLE_ORIGIN'
        g = ms.group(1) or ms.group(2) or ''
        if g.strip():
            axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٧. يدلّ على X
    elif RE_YADULL.match(after):
        md = RE_YADULL.match(after)
        axes_count = 1
        entry_type = 'SINGLE_ORIGIN'
        axes.append({'text': _clean(md.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٨. كلمة تدلّ على X
    elif RE_WORD.match(after):
        mw = RE_WORD.match(after)
        axes_count = 1
        entry_type = 'SINGLE_WORD'
        axes.append({'text': _clean(mw.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٩. معظم بابه X
    elif RE_MAAZAM.match(after):
        mm = RE_MAAZAM.match(after)
        axes_count = 1
        entry_type = 'SINGLE_ORIGIN'
        axes.append({'text': _clean(mm.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    # ٩ب. كلمة [واحدة] — مع أو بدون "يدل على"
    elif re.match(r'^(?:\*?\s*)?كلمة\s*(?:واحدة)?(?:\s|[،.:]|$)', after):
        mw = RE_WORD.match(after)
        axes_count = 1
        entry_type = 'SINGLE_WORD'
        if mw:
            axes.append({'text': _clean(mw.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    # ١٠. fallback أ — بحث عن "يدل على" في أول 300 حرف
    else:
        m_yd = re.search(r'يدل[ُّ]?\s+علي?\s+([^.،\n]{3,120})', after[:300])
        if m_yd:
            axes_count = 1
            entry_type = 'SINGLE_ORIGIN'
            axes.append({'text': _clean(m_yd.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

        # ١٠ب. fallback ب — "فالأصل X" أو "وهو X" بعد "أصل واحد..."
        elif re.search(r'^اصل\s+واحد|^قياس\s+واحد', after):
            m_fa = re.search(
                r'(?:فالاصل\s+|فهو\s+|وهو\s+|وهي\s+|والمعني\s+)([^.،\n]{3,120})',
                after[:400],
            )
            if m_fa:
                axes_count = 1
                entry_type = 'SINGLE_ORIGIN'
                axes.append({'text': _clean(m_fa.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})
            else:
                # نُصنَّف SINGLE_ORIGIN وإن لم نستخلص النص الدقيق
                axes_count = 1
                entry_type = 'SINGLE_ORIGIN'

    return {'axes': axes, 'axes_count': axes_count, 'entry_type': entry_type}


def enrich_entry(e: dict) -> dict:
    body = e.get('body_text', '')
    ai = extract_axes(body)
    authorities = sorted(set(RE_AUTHORITIES.findall(body)))
    suspect = len(RE_OCR_SUSPECT.findall(body))
    total = max(len(body), 1)
    ocr_conf = max(0.0, round(1.0 - (suspect / total) * 10, 2))

    return {
        **e,
        'semantic_axes': ai['axes'],
        'axes_count': ai['axes_count'],
        'entry_type': ai['entry_type'],
        'quoted_authorities': authorities,
        'ocr_confidence': ocr_conf,
        'review_state': 'PENDING',
        'claim_status': 'UNVERIFIED',
    }


# ── تشغيل ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    src = Path('/mnt/user-data/uploads/hokom-maqayis-v1/shamela_maqayis_entries.jsonl')
    dst = Path('/root/maqayis_v2/shamela_maqayis_enriched.jsonl')

    entries = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    enriched = [enrich_entry(e) for e in entries]

    with dst.open('w', encoding='utf-8') as f:
        for e in enriched:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')

    types = Counter(e['entry_type'] for e in enriched)
    has_axes = sum(1 for e in enriched if e['semantic_axes'])
    multi = sum(1 for e in enriched if (e['axes_count'] or 0) >= 2)
    low_ocr = sum(1 for e in enriched if e['ocr_confidence'] < 0.8)
    unknown = sum(1 for e in enriched if e['entry_type'] == 'UNKNOWN')

    print(f'✓ إجمالي: {len(enriched)}')
    print(f'✓ لها أصول مستخلصة: {has_axes}  ({has_axes*100//len(enriched)}%)')
    print(f'↑ متعددة الأصول: {multi}')
    print(f'⚠ OCR ضعيف (<0.8): {low_ocr}')
    print(f'? غير محدد (UNKNOWN): {unknown}')
    print()
    print('توزيع الأنواع:')
    for t, c in types.most_common():
        print(f'  {c:5d}  {t}')

    # نماذج تحقق من كل نوع
    print('\nنماذج:')
    seen = set()
    for e in enriched:
        et = e['entry_type']
        if et not in seen:
            seen.add(et)
            ax = e['semantic_axes'][0]['text'][:50] if e['semantic_axes'] else '—'
            print(f'  [{e["root_display"]:6s}] {et:25s} → "{ax}"')
