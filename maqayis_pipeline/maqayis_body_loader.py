"""
maqayis_body_loader.py — Body text resolver + semantic segmenter
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Resolves body_line_ids from root_entries JSONL against lines.jsonl
to retrieve full lexical entry text — excluding poetry_line_ids per
constitutional contract ("بدون الشعر").

Additionally provides segment_body() which splits the assembled text into
typed spans using the discourse markers attested in the Maqayis corpus.

Marker taxonomy (derived from full-corpus scan — 11,164 body lines):
──────────────────────────────────────────────────────────────────────
  USAGE        يقال / فيقال / يقولون / تقول   (2,530+ occurrences)
  AUTHORITY    قال X : / قالوا :               (3,453+ occurrences)
  BRANCH       ومن الباب / ومن هذا الباب       (414 occurrences)
  INTRO        من ذلك / فمن ذلك / وذلك         (502 occurrences)
  SECOND_ORIG  والأصل الآخر / والثانى          (265 occurrences)
  EXCEPTION    ومما شذّ (عن الباب)             (141 occurrences)
  ETYMOLOGY    أصله / لأنّه / كأنّه / سُمِّي  (609+ occurrences)
  HADITH       وفى الحديث / فى الحديث          (112 occurrences)
  PLURAL       والجمع / وجمعه                  (185 occurrences)
  CONTINUATION (default — unmarked opening prose)

OCR normalisation applied before matching:
  وبقال → ويقال    (62 OCR artifacts corrected)
"""
from __future__ import annotations

import json
import pathlib
import re
import threading
from dataclasses import dataclass
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — MARKER TAXONOMY
#   Corpus-attested discourse markers, compiled from full scan.
# ═══════════════════════════════════════════════════════════════════════════════

#: Human-readable catalogue of all discovered markers with corpus frequencies.
LEXICAL_MARKERS: dict[str, dict[str, Any]] = {
    # ── Usage / Citation ──────────────────────────────────────────────────────
    "يقال": {
        "type": "USAGE",
        "pattern": r"(?:و|ف)?(?:ي|ب)قال\b|(?:و)?يُقال\b|فيقال\b",
        "freq": 2530,
        "note": "introduces attested usage; وبقال is OCR artifact of ويقال",
    },
    "يقولون": {
        "type": "USAGE",
        "pattern": r"(?:و)?يقولون\b|(?:و)?تقول\b",
        "freq": 926,
        "note": "alternate usage introduction",
    },
    "قيل": {
        "type": "USAGE",
        "pattern": r"\bقيل\b",
        "freq": 112,
        "note": "passive — 'it was said'",
    },
    # ── Authority Citation ─────────────────────────────────────────────────────
    "قال": {
        "type": "AUTHORITY",
        "pattern": r"(?:و)?قال\s+[؀-ۿ\w]+|قالوا\b",
        "freq": 3453,
        "note": "top authorities: ابن دريد, أبو بكر, أبو عبيد, رسول اللّٰه",
    },
    # ── Structural: Branch introduction ───────────────────────────────────────
    "ومن الباب": {
        "type": "BRANCH",
        "pattern": r"ومن (?:هذا )?(?:الباب|الأصل)\b",
        "freq": 414,
        "note": "introduces a derived or related lexical item",
    },
    "من ذلك": {
        "type": "INTRO",
        "pattern": r"(?:ف)?من ذلك\b|وذلك\b",
        "freq": 502,
        "note": "introduces the first or main example after the origin claim",
    },
    # ── Structural: Second / other origin ─────────────────────────────────────
    "والأصل الآخر": {
        "type": "SECOND_ORIG",
        "pattern": r"(?:و)?(?:الأصل|والأصل) (?:الآخر|الثانى|الثاني)\b|فالأوَّل\b|فالأول\b",
        "freq": 265,
        "note": "signals DUAL-origin entries; marks the split between two origins",
    },
    # ── Structural: Exception ──────────────────────────────────────────────────
    "ومما شذّ": {
        "type": "EXCEPTION",
        "pattern": r"ومما شذَّ?(?:\s+عن\s+الباب)?",
        "freq": 141,
        "note": "marks items that deviate from the root's regular derivation",
    },
    # ── Etymology ─────────────────────────────────────────────────────────────
    "أصله": {
        "type": "ETYMOLOGY",
        "pattern": r"\bأصل(?:ه|ها|هُ|ان)\b",
        "freq": 68,
        "note": "introduces the underlying meaning or derivational source",
    },
    "لأنّه": {
        "type": "ETYMOLOGY",
        "pattern": r"\bلأنَّ?ه\b",
        "freq": 288,
        "note": "causal clause explaining why a word has its form/meaning",
    },
    "كأنّه": {
        "type": "ETYMOLOGY",
        "pattern": r"\bكأنَّ?ه\b",
        "freq": 251,
        "note": "analogical comparison supporting an etymological claim",
    },
    "سمّي": {
        "type": "ETYMOLOGY",
        "pattern": r"\bسُمِّي(?:ت)?\b|سمِّي(?:ت)?\b|(?:وإنما\s+)?تسميت?هم\b",
        "freq": 40,
        "note": "explains why a word was given its name",
    },
    "اشتقاقه": {
        "type": "ETYMOLOGY",
        "pattern": r"\bاشتقاق(?:ه|ها)?\b|\bمشتق\b",
        "freq": 39,
        "note": "derivational analysis",
    },
    "يدلّ على": {
        "type": "ETYMOLOGY",
        "pattern": r"\bيدلُّ? على\b",
        "freq": 27,
        "note": "semantic pointer — states what the root denotes",
    },
    # ── Hadith ────────────────────────────────────────────────────────────────
    "الحديث": {
        "type": "HADITH",
        "pattern": r"(?:و)?(?:فى|في)\s+الحديث\b",
        "freq": 112,
        "note": "introduces a Prophetic hadith as evidence",
    },
    # ── Grammatical ───────────────────────────────────────────────────────────
    "والجمع": {
        "type": "PLURAL",
        "pattern": r"(?:و)?(?:الجمع|جمعه)\b",
        "freq": 185,
        "note": "introduces the plural form of the word being defined",
    },
}


# ── Compiled split-pattern ───────────────────────────────────────────────────

_PRIORITY_ORDER = [
    "ومما شذّ", "والأصل الآخر", "ومن الباب", "من ذلك",
    "الحديث", "يقال", "يقولون", "قيل", "قال",
    "سمّي", "أصله", "يدلّ على", "لأنّه", "كأنّه",
    "اشتقاقه", "والجمع",
]

def _build_split_regex() -> re.Pattern:
    parts = [LEXICAL_MARKERS[k]["pattern"] for k in _PRIORITY_ORDER]
    return re.compile("(" + "|".join(parts) + ")", re.UNICODE)

_SPLIT_RE: re.Pattern = _build_split_regex()

_MARKER_TYPE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(v["pattern"], re.UNICODE), v["type"])
    for v in LEXICAL_MARKERS.values()
]

_OCR_FIX = re.compile(r"\bوبقال\b", re.UNICODE)


def _ocr_normalise(text: str) -> str:
    return _OCR_FIX.sub("ويقال", text)


def _classify_marker(marker_text: str) -> str:
    for pat, stype in _MARKER_TYPE_MAP:
        if pat.search(marker_text):
            return stype
    return "CONTINUATION"


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — SEGMENT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BodySegment:
    """
    One typed unit of a lexical entry's body text.

    Attributes
    ──────────
    type    : semantic type (USAGE, AUTHORITY, BRANCH, INTRO, SECOND_ORIG,
              EXCEPTION, ETYMOLOGY, HADITH, PLURAL, CONTINUATION)
    marker  : the discourse marker that opened this segment (may be "")
    text    : the content text following the marker
    """
    type:   str
    marker: str
    text:   str

    def full_text(self) -> str:
        """Marker + text joined with a space (if marker is non-empty)."""
        if self.marker:
            return f"{self.marker} {self.text}".strip()
        return self.text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — LINE TEXT SELECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _best_text(line_obj: dict[str, Any]) -> str:
    """human_text → corrected_ocr → raw_ocr → ''."""
    for key in ("human_text", "corrected_ocr", "raw_ocr"):
        val = line_obj.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — MAQAYIS BODY LOADER
# ═══════════════════════════════════════════════════════════════════════════════

class MaqayisBodyLoader:
    """
    Lazy-loaded, thread-safe resolver from line_id → text, with semantic
    segmentation of body text using corpus-attested discourse markers.

    Parameters
    ──────────
    lines_jsonl : path to the lines.jsonl file (52 K lines).
    """

    def __init__(self, lines_jsonl: "pathlib.Path | str") -> None:
        self._path   = pathlib.Path(lines_jsonl)
        self._lock   = threading.Lock()
        self._loaded = False
        self._index: dict[str, dict[str, Any]] = {}

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        index: dict[str, dict[str, Any]] = {}
        with open(self._path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    lid = obj.get("line_id")
                    if lid:
                        index[lid] = obj
                except json.JSONDecodeError:
                    pass
        self._index  = index
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            with self._lock:
                if not self._loaded:
                    self._load()

    # ── Line-level API ────────────────────────────────────────────────────────

    @property
    def line_count(self) -> int:
        self._ensure_loaded()
        return len(self._index)

    def get_line_text(self, line_id: str) -> str:
        self._ensure_loaded()
        obj = self._index.get(line_id)
        if obj is None:
            return ""
        return _best_text(obj)

    def get_lines_text(
        self,
        line_ids: list,
        *,
        exclude: Optional[set] = None,
        separator: str = "\n",
    ) -> str:
        self._ensure_loaded()
        exclude = exclude or set()
        parts: list[str] = []
        for lid in line_ids:
            if lid in exclude:
                continue
            text = self.get_line_text(lid)
            if text:
                parts.append(text)
        return separator.join(parts)

    # ── Entry-level API ───────────────────────────────────────────────────────

    def get_body_text(
        self,
        entry: dict[str, Any],
        *,
        include_footnotes: bool = False,
        separator: str = " ",
    ) -> str:
        """
        Return body text for a root entry dict.

        Poetry lines ALWAYS excluded (constitutional: بدون الشعر).
        Footnotes excluded by default; set include_footnotes=True to include.
        OCR normalisation applied (وبقال → ويقال).
        """
        body_ids     = entry.get("body_line_ids", []) or []
        poetry_ids   = set(entry.get("poetry_line_ids", []) or [])
        footnote_ids = entry.get("footnote_line_ids", []) or []

        ids_to_fetch = list(body_ids)
        if include_footnotes:
            ids_to_fetch.extend(footnote_ids)

        raw = self.get_lines_text(ids_to_fetch, exclude=poetry_ids, separator=separator)
        return _ocr_normalise(raw)

    def get_entry_text(
        self,
        entry: dict[str, Any],
        *,
        include_footnotes: bool = False,
        heading_separator: str = "\n",
        line_separator: str = " ",
    ) -> str:
        """Return heading + body (no poetry, no footnotes)."""
        heading = (entry.get("root_heading_text") or "").strip()
        body    = self.get_body_text(
            entry,
            include_footnotes=include_footnotes,
            separator=line_separator,
        )
        if heading and body:
            return heading + heading_separator + body
        return heading or body

    # ── Segmentation API ──────────────────────────────────────────────────────

    def segment_body(
        self,
        entry: dict[str, Any],
        *,
        include_footnotes: bool = False,
        min_text_len: int = 3,
    ) -> list[BodySegment]:
        """
        Split the body text into typed BodySegment spans.

        Segment types:
          USAGE        يقال / فيقال / يقولون / تقول
          AUTHORITY    قال X / قالوا
          BRANCH       ومن الباب / ومن هذا الباب
          INTRO        من ذلك / فمن ذلك / وذلك
          SECOND_ORIG  والأصل الآخر / والثانى / فالأوّل
          EXCEPTION    ومما شذّ (عن الباب)
          ETYMOLOGY    أصله / لأنّه / كأنّه / سُمِّي / اشتقاقه
          HADITH       وفى الحديث / فى الحديث
          PLURAL       والجمع / وجمعه
          CONTINUATION (unmarked opening prose)
        """
        body = self.get_body_text(entry, include_footnotes=include_footnotes)
        if not body:
            return []

        parts = _SPLIT_RE.split(body)
        segments: list[BodySegment] = []
        current_marker = ""
        current_type   = "CONTINUATION"

        for part in parts:
            if not part or not part.strip():
                continue
            if _SPLIT_RE.fullmatch(part.strip()):
                current_marker = part.strip()
                current_type   = _classify_marker(current_marker)
            else:
                text = part.strip()
                if len(text) >= min_text_len:
                    segments.append(BodySegment(
                        type=current_type,
                        marker=current_marker,
                        text=text,
                    ))
                current_marker = ""
                current_type   = "CONTINUATION"

        return segments

    def entry_summary(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Return a structured dict with all key fields for an entry."""
        from collections import Counter
        root_letters = entry.get("root_letters", "?")
        heading      = (entry.get("root_heading_text") or "").strip()
        body         = self.get_body_text(entry)
        body_ids     = entry.get("body_line_ids", []) or []
        poetry_ids   = entry.get("poetry_line_ids", []) or []
        footnote_ids = entry.get("footnote_line_ids", []) or []
        segments     = self.segment_body(entry)
        type_counts  = Counter(s.type for s in segments)

        poetry_texts: list[str] = []
        for lid in poetry_ids:
            t = self.get_line_text(lid)
            if t:
                poetry_texts.append(t)

        return {
            "root_letters":    root_letters,
            "source":          f"{entry.get('source_pdf', '?')} p.{entry.get('pdf_page', '?')}",
            "semantic_origin": entry.get("semantic_origin_type", "?"),
            "review_status":   entry.get("review_status", "?"),
            "heading":         heading,
            "body":            body,
            "body_line_count": len(body_ids),
            "body_resolved":   bool(body),
            "poetry_excluded": len(poetry_ids),
            "footnote_count":  len(footnote_ids),
            "poetry_texts":    poetry_texts,
            "segments":        segments,
            "segment_types":   dict(type_counts),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — AUTO-DISCOVERY AND SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

def _find_lines_jsonl(start: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Walk up from start looking for data/maqaees/full/lines.jsonl."""
    here = (start or pathlib.Path(__file__).resolve().parent)
    for _ in range(6):
        candidate = here / "data" / "maqaees" / "full" / "lines.jsonl"
        if candidate.is_file():
            return candidate
        if here.parent == here:
            break
        here = here.parent
    return None


_DEFAULT_LOADER: Optional[MaqayisBodyLoader] = None
_LOADER_LOCK    = threading.Lock()


def get_default_loader(lines_jsonl: Optional[pathlib.Path] = None) -> MaqayisBodyLoader:
    """
    Return the module-level singleton loader, auto-discovering lines.jsonl.
    Subsequent calls return the cached instance.
    """
    global _DEFAULT_LOADER
    if _DEFAULT_LOADER is None:
        with _LOADER_LOCK:
            if _DEFAULT_LOADER is None:
                if lines_jsonl is None:
                    lines_jsonl = _find_lines_jsonl()
                if lines_jsonl is None:
                    raise FileNotFoundError(
                        "Could not locate lines.jsonl. "
                        "Pass an explicit path to MaqayisBodyLoader()."
                    )
                _DEFAULT_LOADER = MaqayisBodyLoader(lines_jsonl)
    return _DEFAULT_LOADER
