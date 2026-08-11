#!/usr/bin/env python3
"""
shamela_maqayis_scraper.py  v2
-------------------------------
يسحب نص مقاييس اللغة (كتاب 21710) من shamela.ws
ويحوّله إلى ملف JSONL بُنيته متوافقة مع pipeline المقاييس.

بنية مقاييس اللغة على شاملة:
  1. [خبز]                        ← رأس المدخل: الجذر في معقوفتين
  2. الخاء والباء والزاء أصل واحد  ← السطر الأول من النص
  3. نص الشرح...
  4. (١) حاشية...                 ← حواشي في نهاية الصفحة

الاستخدام:
    pip install requests beautifulsoup4 lxml
    python3 shamela_maqayis_scraper.py --test
    python3 shamela_maqayis_scraper.py
    python3 shamela_maqayis_scraper.py --start 214 --end 600
"""

import json
import re
import time
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── الإعدادات ─────────────────────────────────────────────────────────────────

BOOK_ID    = 21710
BASE_URL   = f"https://shamela.ws/book/{BOOK_ID}"
LAST_PAGE  = 2694
DELAY_SEC  = 1.5
MAX_RETRIES = 3
TIMEOUT_SEC = 15

RAW_OUT     = Path("shamela_maqayis_raw.jsonl")
ENTRIES_OUT = Path("shamela_maqayis_entries.jsonl")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://shamela.ws/",
})

# ── خريطة أسماء الحروف → الحرف ───────────────────────────────────────────────

LETTER_NAME_MAP = {
    "الهمزة": "أ", "الألف": "أ",
    "الباء":  "ب", "التاء":  "ت", "الثاء":  "ث",
    "الجيم":  "ج", "الحاء":  "ح", "الخاء":  "خ",
    "الدال":  "د", "الذال":  "ذ", "الراء":  "ر",
    "الزاء":  "ز", "الزاي":  "ز",
    "السين":  "س", "الشين":  "ش", "الصاد":  "ص",
    "الضاد":  "ض", "الطاء":  "ط", "الظاء":  "ظ",
    "العين":  "ع", "الغين":  "غ", "الفاء":  "ف",
    "القاف":  "ق", "الكاف":  "ك", "اللام":  "ل",
    "الميم":  "م", "النون":  "ن", "الهاء":  "ه",
    "الواو":  "و", "الياء":  "ي",
}

# نمط لالتقاط اسم حرف واحد (بالترتيب التنازلي لتجنب التطابق الجزئي)
_NAMES_RE = "|".join(
    re.escape(k) for k in sorted(LETTER_NAME_MAP, key=len, reverse=True)
)

# ── أنماط التعرّف على الهيكل ──────────────────────────────────────────────────

# 1) [خبز] — الجذر في معقوفتين (المحدّد الرئيسي للمداخل في شاملة)
RE_BRACKET_ROOT = re.compile(r"^\[([؀-ۿّ]{1,6})\]\s*$")

# بادئات مقطع المضاعف — ثلاثة أنماط:
#   "وأما الهمزة" | "وللهمزة" | "والهمزة"
_MUDA_PFX = r"(?:وأمّ?ا?\s+|وللـ?\s*|و)"

# 2a) فضفاض: "اسم_حرف و اسم_حرف" مع بادئة اختيارية — لتأكيد المعقوفة
RE_LETTER_NAMES_CONFIRM = re.compile(
    rf"^(?:{_MUDA_PFX})?(?:{_NAMES_RE})\s+(?:و\s*(?:{_NAMES_RE}))",
    re.UNICODE,
)

# 2b) صارم: يشترط كلمة دلالية — للكشف المستقل بلا معقوفة ولا بادئة مضاعف
RE_LETTER_NAMES_LINE = re.compile(
    rf"^({_NAMES_RE})"                              # اسم الحرف الأول
    rf"(?:\s+و\s*(?:{_NAMES_RE}))*"                # بقية أسماء الحروف
    rf"(?:\s+وما\s+يثلثهما|\s+في\s+|)?"
    rf".{{0,60}}?(?:أصلٌ|أصل\s+واح|وجهان|أصلان|يدلّ|يدل\s+على)",
    re.UNICODE,
)

# 2c) كاشف مداخل المضاعف بلا معقوفة — يشترط وجود البادئة (وأما/ولل/و)
# يكفي أن يبدأ السطر ببادئة ثم اسمَي حرفين (بلا حاجة لكلمة دلالية)
RE_MADADIF_ENTRY = re.compile(
    rf"^{_MUDA_PFX}(?:{_NAMES_RE})\s+(?:و\s*(?:{_NAMES_RE}))",
    re.UNICODE,
)

# 3) عناوين الأبواب والكتب
RE_CHAPTER = re.compile(
    r"^(?:كتاب|باب|فصل)\s+[؀-ۿ]",
    re.MULTILINE
)

# 4) الحواشي: سطر يبدأ بـ (١) أو (١٠) ... أو footnote markers
RE_FOOTNOTE_START = re.compile(r"^\s*[\(\（]\s*[١٢٣٤٥٦٧٨٩٠0-9]{1,2}\s*[\)\）]")

# 5) أبيات الشعر
#    المعيار: يحتوي حرف "…" (U+2026 ELLIPSIS) وسط السطر بين مصراعين
#    لا نستخدم النقطة العادية "." لأنها تظهر في كل جملة نثرية
RE_POETRY_LINE = re.compile(
    r"[؀-ۿ\w].{5,}\s…\s.{5,}[؀-ۿ\w]",   # مصراع … مصراع
    re.UNICODE
)

# 6) مراجع الصفحات الأصلية
#    نقبل: (ص٤٥) أو (٣١٢: ٢) — لا نقبل (١) المجردة (حواشي)
RE_PAGE_REF = re.compile(
    r"[\[\(]ص\s*([٠-٩0-9]+)[\]\)]"                       # (ص٤٥)
    r"|[\[\(]([٠-٩0-9]+)\s*:\s*[٠-٩0-9]+[\]\)]"          # (٣١٢: ٢)
)


def _letter_names_to_root(text: str) -> str:
    """
    استخرج حروف الجذر من نص يحتوي أسماء الحروف.
    مثال: "الخاء والباء والزاء" → "خبز"
    """
    found = re.findall(_NAMES_RE, text)
    root = "".join(LETTER_NAME_MAP.get(n, "") for n in found)
    return root or ""


# ── هياكل البيانات ─────────────────────────────────────────────────────────────

@dataclass
class RawPage:
    page_num: int
    url: str
    vol: Optional[str]
    page_label: Optional[str]
    text: str
    footnotes: list


@dataclass
class ParsedEntry:
    entry_num: int
    source: str = "shamela_21710"
    root_letters: Optional[str] = None      # حروف الجذر مثل: خبز
    root_display: Optional[str] = None      # الجذر كما يظهر في المعقوفتين
    chapter_header: Optional[str] = None
    is_lexical_entry: bool = False          # True = جذر حقيقي، False = مقدمة/حاشية
    body_text: str = ""
    poetry_lines: list = field(default_factory=list)
    footnote_lines: list = field(default_factory=list)
    page_refs: list = field(default_factory=list)
    raw_page_nums: list = field(default_factory=list)


# ── دوال المساعدة ──────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_vol_page(soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
    text = soup.get_text(" ")
    vol = page_label = None
    m = re.search(r"(ج\s*\d+)\s*[-–]\s*(ص\s*\d+)", text)
    if m:
        vol        = m.group(1).replace(" ", "")
        page_label = m.group(2).replace(" ", "")
    return vol, page_label


def _get_content(soup: BeautifulSoup) -> tuple[str, list]:
    """استخرج النص الرئيسي والحواشي من الصفحة."""
    container = (
        soup.find("div", id="nass")
        or soup.find("div", class_="nass")
        or soup.find("div", id="book-text")
        or soup.find("div", class_="book-text")
        or soup.find("div", id="content")
        or soup.find("article")
    )

    if container is None:
        candidates = soup.find_all(["div", "section", "article"])
        best, best_len = None, 0
        for el in candidates:
            n = len(re.findall(r"[؀-ۿ]", el.get_text()))
            if n > best_len:
                best, best_len = el, n
        container = best

    if container is None:
        return "", []

    # افصل الحواشي
    footnotes_collected = []
    for fn in container.find_all(class_=re.compile(r"foot|hawashi|حاشية", re.I)):
        footnotes_collected.append(fn.get_text(" ").strip())
        fn.decompose()

    # أزل عناصر التنقل
    for el in container.find_all(["nav", "button", "script", "style"]):
        el.decompose()
    for el in container.find_all(class_=re.compile(r"nav|pager|btn|toc|header|footer", re.I)):
        el.decompose()

    text = container.get_text("\n")
    text = _clean_text(text)
    return text, footnotes_collected


# ── الجلب ─────────────────────────────────────────────────────────────────────

def fetch_page(page_num: int) -> Optional[RawPage]:
    url = f"{BASE_URL}/{page_num}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.get(url, timeout=TIMEOUT_SEC)
            if resp.status_code == 404:
                log.warning("404 — صفحة %d", page_num)
                return None
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            vol, page_label = _extract_vol_page(soup)
            text, footnotes = _get_content(soup)
            return RawPage(
                page_num=page_num,
                url=url,
                vol=vol,
                page_label=page_label,
                text=text,
                footnotes=footnotes,
            )
        except requests.RequestException as e:
            wait = DELAY_SEC * (2 ** attempt)
            log.warning("محاولة %d/3 — صفحة %d — %s — انتظر %.1fث", attempt, page_num, e, wait)
            if attempt < MAX_RETRIES:
                time.sleep(wait)
    log.error("فشل جلب صفحة %d", page_num)
    return None


# ── التقطيع ────────────────────────────────────────────────────────────────────

class EntryParser:
    """
    يقطّع الصفحات إلى مداخل جذرية بناءً على هيكل مقاييس اللغة الفعلي:

    المحدّد الأساسي:  [خبز]  ← سطر وحيد في معقوفتين يحمل الجذر
    المحدّد الثانوي:  سطر يبدأ بأسماء حروف + "أصل" أو "وجهان"
                      (يُستخدم كاحتياطي إذا لم يسبقه معقوف)
    """

    def __init__(self):
        self._counter       = 0
        self._cur_entry: Optional[ParsedEntry] = None
        self._cur_chapter: Optional[str] = None
        self._entries: list[ParsedEntry] = []
        self._pending_root: Optional[str] = None   # جذر مُرصد من [معقوفة] ينتظر سطر النص

    # ── إدارة المدخل الحالي ──────────────────────────────────────────────────

    def _flush(self):
        if self._cur_entry and self._cur_entry.body_text.strip():
            self._entries.append(self._cur_entry)
        self._cur_entry = None

    def _start_entry(self, root_display: str, root_letters: str, page_num: int):
        self._flush()
        self._counter += 1
        self._cur_entry = ParsedEntry(
            entry_num=self._counter,
            root_letters=root_letters or root_display,
            root_display=root_display,
            chapter_header=self._cur_chapter,
            raw_page_nums=[page_num],
        )

    def _add_line(self, line: str, page_num: int):
        if self._cur_entry is None:
            return
        if page_num not in self._cur_entry.raw_page_nums:
            self._cur_entry.raw_page_nums.append(page_num)

        # حاشية؟
        if RE_FOOTNOTE_START.match(line):
            self._cur_entry.footnote_lines.append(line)
            return

        # بيت شعر؟
        if RE_POETRY_LINE.search(line):
            self._cur_entry.poetry_lines.append(line)
            # أضفه كذلك في النص الرئيسي لاستمرارية القراءة
            self._cur_entry.body_text += line + "\n"
            return

        # مراجع صفحات أصلية — findall يُعيد قوائم بسبب مجموعتَي الـ regex
        refs = RE_PAGE_REF.findall(line)
        if refs:
            # كل عنصر tuple (g1, g2) — نأخذ أول غير فارغ
            flat = [g1 or g2 for g1, g2 in refs if g1 or g2]
            self._cur_entry.page_refs.extend(flat)

        self._cur_entry.body_text += line + "\n"

    # ── استيعاب صفحة ─────────────────────────────────────────────────────────

    def feed_page(self, page: RawPage):
        if not page.text:
            return

        lines = page.text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line:
                continue

            # ── 1) عنوان باب / كتاب ─────────────────────────────────────────
            if RE_CHAPTER.match(line):
                self._cur_chapter = line
                self._pending_root = None
                continue

            # ── 2) معقوفة: [خبز] ────────────────────────────────────────────
            m_bracket = RE_BRACKET_ROOT.match(line)
            if m_bracket:
                root_display = m_bracket.group(1)
                self._pending_root = root_display
                # لا نفتح المدخل حتى يأتي السطر الأول من النص
                continue

            # ── 3a) معقوفة معلّقة + سطر يبدأ بأسماء حروف (فضفاض) → مدخل مؤكَّد ──
            #       يشمل مداخل المضاعف "الهمزة والصاد كلمتان إن صحّتا"
            m_confirm = RE_LETTER_NAMES_CONFIRM.match(line)
            if self._pending_root and m_confirm:
                root_display = self._pending_root
                root_letters = _letter_names_to_root(m_confirm.group(0))  # الجزء المطابق فقط
                self._start_entry(root_display, root_letters, page.page_num)
                if self._cur_entry:
                    self._cur_entry.is_lexical_entry = True
                self._pending_root = None
                self._add_line(line, page.page_num)
                continue

            # ── 3b) بلا معقوفة + سطر صارم (أصل/وجه/يدل) → مدخل مستقل ────────
            m_strict = RE_LETTER_NAMES_LINE.match(line)
            if not self._pending_root and m_strict:
                root_letters = _letter_names_to_root(m_strict.group(0))  # الجزء المطابق فقط
                self._start_entry(root_letters, root_letters, page.page_num)
                if self._cur_entry:
                    self._cur_entry.is_lexical_entry = True
                self._add_line(line, page.page_num)
                continue

            # ── 3c) بلا معقوفة + بادئة مضاعف (وأما/ولل/و) → مدخل مضاعف ─────
            #       مثال: "وأما الهمزة والصاد فله معنيان"
            #              "وللهمزة والطاء معنى واحد"
            #              "والهمزة واللام فى المضاعف"
            m_madadif = RE_MADADIF_ENTRY.match(line)
            if not self._pending_root and m_madadif:
                root_letters = _letter_names_to_root(m_madadif.group(0))  # الجزء المطابق فقط
                self._start_entry(root_letters, root_letters, page.page_num)
                if self._cur_entry:
                    self._cur_entry.is_lexical_entry = True
                self._add_line(line, page.page_num)
                continue

            # ── 4) معقوفة معلّقة لكن السطر لا يبدأ بأسماء حروف → عنوان فصل ──
            #       نُسقط المعقوفة ونُضيف السطر إلى المدخل الجاري
            if self._pending_root:
                self._pending_root = None
                self._add_line(line, page.page_num)
                continue

            # ── 5) سطر عادي — يُضاف إلى المدخل الحالي ──────────────────────
            self._add_line(line, page.page_num)

    def finish(self) -> list[ParsedEntry]:
        self._flush()
        return self._entries


# ── نقطة الدخول ───────────────────────────────────────────────────────────────

def reparse_from_raw(raw_path: Path = RAW_OUT):
    """
    أعد تشغيل الـ parser على ملف الصفحات الخام دون إعادة السحب.
    مفيد لاختبار التعديلات بسرعة بعد اكتمال السحب.
    """
    if not raw_path.exists():
        log.error("ملف الصفحات الخام غير موجود: %s", raw_path)
        return
    log.info("إعادة التقطيع من: %s", raw_path)
    parser = EntryParser()
    count = 0
    with open(raw_path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            page = RawPage(**data)
            parser.feed_page(page)
            count += 1
    entries = parser.finish()
    lexical = [e for e in entries if e.is_lexical_entry]
    with open(ENTRIES_OUT, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    log.info("صفحات: %d — مداخل: %d إجمالاً (%d جذر، %d مقدمة)",
             count, len(entries), len(lexical), len(entries) - len(lexical))
    _print_sample(lexical)

    # فحص مدخل أش تحديداً
    ash = [e for e in entries if e.root_display in ("أش", "أشّ", "أشش")]
    if ash:
        print("\n" + "="*60)
        print("مدخل أش (فحص التقطيع):")
        print("="*60)
        for e in ash:
            d = asdict(e)
            d["body_text"] = d["body_text"][:300] + ("…" if len(d["body_text"]) > 300 else "")
            d["poetry_lines"] = f"[{len(e.poetry_lines)} بيت]"
            d["footnote_lines"] = f"[{len(e.footnote_lines)} حاشية]"
            print(json.dumps(d, ensure_ascii=False, indent=2))


def run(start: int = 1, end: int = LAST_PAGE,
        write_raw: bool = True, write_entries: bool = True):

    log.info("بدء السحب: صفحات %d – %d", start, end)

    parser  = EntryParser()
    raw_fp  = open(RAW_OUT, "w", encoding="utf-8") if write_raw else None
    total   = end - start + 1

    for idx, page_num in enumerate(range(start, end + 1), 1):
        page = fetch_page(page_num)
        if page:
            parser.feed_page(page)
            if raw_fp:
                raw_fp.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")

        if idx % 50 == 0 or idx == total:
            log.info("تقدّم: %d/%d (%.0f%%)", idx, total, idx / total * 100)

        time.sleep(DELAY_SEC)

    if raw_fp:
        raw_fp.close()

    if write_entries:
        entries = parser.finish()
        lexical = [e for e in entries if e.is_lexical_entry]
        with open(ENTRIES_OUT, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        log.info("حُفظ %s — %d مدخل إجمالاً (%d جذر حقيقي، %d مقدمة/حاشية)",
                 ENTRIES_OUT, len(entries), len(lexical), len(entries) - len(lexical))
        _print_sample(lexical)


def run_test(pages: list[int] | None = None):
    """اختبار سريع على صفحات محددة."""
    if pages is None:
        pages = [50, 214, 215, 216, 800, 1500]
    log.info("وضع الاختبار — صفحات: %s", pages)
    parser = EntryParser()
    for pn in pages:
        page = fetch_page(pn)
        if page:
            parser.feed_page(page)
            log.info("  ص%d — نص: %d حرف", pn, len(page.text))
        time.sleep(DELAY_SEC)
    entries = parser.finish()
    log.info("مداخل مُقطَّعة: %d", len(entries))
    _print_sample(entries, n=6)


def _print_sample(entries: list, n: int = 5):
    print(f"\n{'='*60}")
    print(f"نموذج أول {n} مداخل:")
    print('='*60)
    for e in entries[:n]:
        d = asdict(e)
        # اختصر body_text لتسهيل القراءة
        body = d["body_text"]
        d["body_text"] = body[:200] + ("…" if len(body) > 200 else "")
        print(json.dumps(d, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="سحب مقاييس اللغة من شاملة — v2")
    ap.add_argument("--test",    action="store_true", help="اختبار 6 صفحات فقط")
    ap.add_argument("--reparse", action="store_true", help="أعد التقطيع من الملف الخام المحفوظ")
    ap.add_argument("--start",   type=int, default=1,         help="رقم أول صفحة")
    ap.add_argument("--end",     type=int, default=LAST_PAGE, help="رقم آخر صفحة")
    ap.add_argument("--no-raw",  action="store_true",         help="لا تحفظ الصفحات الخام")
    ap.add_argument("--pages",   nargs="+", type=int,         help="صفحات محددة للاختبار")
    args = ap.parse_args()

    if args.reparse:
        reparse_from_raw()
    elif args.test:
        run_test(args.pages)
    else:
        run(start=args.start, end=args.end, write_raw=not args.no_raw)
