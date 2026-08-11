"""
أنماط الاستخلاص — النسخة النهائية
"""
import re

# ── التطبيع ───────────────────────────────────────────────────────────────────

def strip_diacritics(t: str) -> str:
    return re.sub(r'[ً-ْٰٱ]', '', t)

def norm_alef(t: str) -> str:
    t = re.sub(r'[أإآ]', 'ا', t)
    t = re.sub(r'ى', 'ي', t)
    return t

def normalize(t: str) -> str:
    return norm_alef(strip_diacritics(t))

# ── استخراج ما بعد سلسلة الحروف ──────────────────────────────────────────────
# مثال: "الهاء والجيم والراء أصل" → after = "أصل..."
# مثال: "وأما الهمزة والجيم فأصلان" → after = "فأصلان..."
_LC = (
    r'(?:ال\w{2,6}'          # الهاء | الحاء | ...
    r'(?:\s+و(?:ال)?\w{2,6})*'       # والجيم | والراء | ...
    r'(?:\s+والحرف\s+المعتل?)?'     # والحرف المعتل
    r')'
)
RE_AFTER_LETTERS = re.compile(rf'^{_LC}[\s:،.]+(.{{1,400}})', re.UNICODE | re.DOTALL)
RE_AFTER_WAMA    = re.compile(rf'^(?:وام?ا?\s+|و){_LC}[\s:،.]+(.{{1,400}})', re.UNICODE | re.DOTALL)

def get_after(body: str) -> str:
    """يستخرج النص بعد سلسلة أسماء الحروف."""
    m = RE_AFTER_LETTERS.match(body) or RE_AFTER_WAMA.match(body)
    after = m.group(1).strip() if m else body.strip()
    # أحياناً يبقى "المعتل" في البداية بسبب "والحرف المعتل" المركّبة
    after = re.sub(r'^المعتل?\s*', '', after)
    return after

# ── أنماط التصنيف ─────────────────────────────────────────────────────────────

# لا أصل
RE_NOROOT = re.compile(
    r'^(?:\*\s*)?(?:'
    r'كلمة\s+ان\s+صحت|'
    r'ليست?\s+(?:باصل|بشئ|في\s+هذا|بذات\s+وجهين)|'
    r'فليس\s+(?:باصل|بشئ|له\s+اصل)|'
    r'ليس\s+له\s+اصل|لا\s+اصل\s+له|'
    r'ليس\s+(?:باصل|اصلا|بشئ)(?:\s+(?:ولا|الا|و)|$)|'
    r'لا\s+اصل\s+ولا\s+فرع|'
    r'ليس\s+فيه\s+الا\s+\w+|'
    r'ليس\s+في\s+هذا\s+الباب'
    r')',
    re.UNICODE,
)

RE_UNCERT = re.compile(r'(?:فيها?\s+نظر|فيه\s+نظر|امر\s+مشكل|لا\s+اعرف\s+له\s+اصلا)', re.UNICODE)

# أصلان / معنيان / وجهان / كلمتان
RE_TWO = re.compile(
    r'^(?:\*?\s*)?(?:ف?اصلان|ف?معنيان|وجهان|كلمتان)\s*[^:،.]{0,30}?[،:\s]\s*'
    r'(?:احدهما|الاول|احد\s+المعنيين|\[احدهما\])?\s*([^،.]{3,120})'
    r'(?:[،.]\s*(?:والاخر|والثاني|والثانى|الاخر|والمعني\s+الاخر|والكلمة\s+الاخري)\s+([^،.]{3,120}))?',
    re.UNICODE,
)

# ثلاثة أصول / أصول ثلاثة / كلمات ثلاث
RE_THREE = re.compile(
    r'^(?:\*?\s*)?(?:ثلاثة\s+اصول?|اصول?\s+ثلاثة|كلمات\s+ثلاث)[^:،]{0,50}[،:]?\s*'
    r'(?:الاولي?\s+)?([^،.]{3,120})'
    r'(?:[،.]\s*(?:والثاني?|الثاني?|والاخري?)\s+([^،.]{3,120}))?',
    re.UNICODE,
)

# أصول أربعة / أربعة أصول
RE_FOUR = re.compile(
    r'^(?:\*?\s*)?(?:اصول?\s+اربعة|اربعة\s+اصول?)[^:،]{0,80}?[،:.\n]\s*'
    r'(?:فالاول|الاول|احدها)\s*[:\s]\s*([^.،\n]{3,120})',
    re.UNICODE,
)

# أصل واحد / أصيل — مع اتساع أكبر في التطابق
RE_SINGLE = re.compile(
    r'^(?:\*?\s*)?'
    r'(?:في\s+المضاعف\s+|قريب\s+من\s+\w+\s+)?'  # بادئات اختيارية
    r'(?:'
    # نمط 1: أصيل يدل على X
    r'اصيل\s+(?:يدل|تدل)\s+علي?\s+([^.\n]{3,150})'
    r'|'
    # نمط 2: أصل [واحد/صحيح/مطرد/...]، وهو / يدل على / فال...
    r'(?:اصيل?|اصل\s+(?:واحد|صحيح|مطرد|[^،:]{0,30})?)'
    r'(?:[^،:.]{0,50}?)'
    r'(?:(?:،|:|\.)\s*\n?\s*'
    r'(?:وهو|وهي|وهى|يدل\s+علي?|تدل\s+علي?|فال\w+\s*:\s*|فالمعني\s+)'
    r'\s*([^.\n]{3,150}))'
    r')',
    re.UNICODE,
)

# يدلّ على X / تدلّ على X
RE_YADULL = re.compile(
    r'^(?:\*?\s*)?(?:يدل|تدل)(?:\s+بناوها?)?\s+علي?\s+([^.\n]{3,150})',
    re.UNICODE,
)

# كلمة [واحدة] — مع أو بدون معنى
RE_WORD = re.compile(
    r'^(?:\*?\s*)?كلمة\s*(?:واحدة)?\s*'
    r'(?:(?:تدل|يدل)\s+علي?\s+([^.،\n]{3,120})'
    r'|(?:[،.]\s*(?:وهو|وهي|وهى)\s+([^.،\n]{3,120})))',
    re.UNICODE,
)

# معظم بابه X
RE_MAAZAM = re.compile(r'^(?:\*?\s*)?معظم\s+بابه\s+([^.،\n]{3,100})', re.UNICODE)

# ── أعلام مرجعية ─────────────────────────────────────────────────────────────
AUTHORITY_NAMES = [
    'الخليل', 'ابن دريد', 'أبو عبيدة', 'الأصمعي', 'أبو زيد',
    'الفراء', 'ابن الأعرابي', 'سيبويه', 'المبرد', 'ثعلب',
    'قطرب', 'الكسائي', 'أبو عمرو', 'الليث', 'الجوهري',
    'أبو بكر', 'ابن السكيت', 'أبو عمر', 'ابن قتيبة',
]
RE_AUTHORITIES = re.compile(
    '|'.join(re.escape(a) for a in AUTHORITY_NAMES), re.UNICODE
)

RE_OCR_SUSPECT = re.compile(r'[^؀-ۿ\s\w\d،.:؟!()«»\[\]٠-٩\-/\n*]')

# ── دالة الاستخلاص الرئيسية ───────────────────────────────────────────────────

def _clean(t: str) -> str:
    return re.sub(r'\s+', ' ', (t or '').strip())


def extract_axes(body: str) -> dict:
    after_orig = get_after(body)
    after = normalize(after_orig)

    if RE_NOROOT.match(after):
        return {'axes': [], 'axes_count': 0, 'entry_type': 'NO_ROOT_OR_UNCERTAIN'}
    if RE_UNCERT.search(after[:120]):
        return {'axes': [], 'axes_count': None, 'entry_type': 'UNCERTAIN'}

    axes, axes_count, entry_type = [], None, 'UNKNOWN'

    m2 = RE_TWO.match(after)
    if m2:
        axes_count, entry_type = 2, 'MULTI_ORIGIN'
        for g in [m2.group(1), m2.group(2)]:
            if g and g.strip():
                axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    elif RE_THREE.match(after):
        m3 = RE_THREE.match(after)
        axes_count, entry_type = 3, 'MULTI_ORIGIN'
        for g in [m3.group(1), m3.group(2)]:
            if g and g.strip():
                axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    elif RE_FOUR.match(after):
        m4 = RE_FOUR.match(after)
        axes_count, entry_type = 4, 'MULTI_ORIGIN'
        if m4.group(1):
            axes.append({'text': _clean(m4.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    elif RE_SINGLE.match(after):
        ms = RE_SINGLE.match(after)
        axes_count, entry_type = 1, 'SINGLE_ORIGIN'
        g = ms.group(1) or ms.group(2) or ''
        if g.strip():
            axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    elif RE_YADULL.match(after):
        md = RE_YADULL.match(after)
        axes_count, entry_type = 1, 'SINGLE_ORIGIN'
        axes.append({'text': _clean(md.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    elif re.match(r'^(?:\*?\s*)?كلمة\s*(?:واحدة)?', after):
        mw = RE_WORD.match(after)
        axes_count, entry_type = 1, 'SINGLE_WORD'
        if mw:
            g = mw.group(1) or mw.group(2) or ''
            if g.strip():
                axes.append({'text': _clean(g), 'attribution': 'IBN_FARIS_DIRECT'})

    elif RE_MAAZAM.match(after):
        mm = RE_MAAZAM.match(after)
        axes_count, entry_type = 1, 'SINGLE_ORIGIN'
        axes.append({'text': _clean(mm.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    else:
        # fallback: بحث عن "يدل على" في أول 300 حرف
        m_yd = re.search(r'يدل[ُّ]?\s+علي?\s+([^.،\n]{3,120})', after[:300])
        if m_yd:
            axes_count, entry_type = 1, 'SINGLE_ORIGIN'
            axes.append({'text': _clean(m_yd.group(1)), 'attribution': 'IBN_FARIS_DIRECT'})

    return {'axes': axes, 'axes_count': axes_count, 'entry_type': entry_type}
