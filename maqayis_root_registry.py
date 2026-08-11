"""
maqayis_root_registry.py — Taaqol integration layer
Maqayis OCR v2  (production-hardened)

Loads data/maqaees/full/root_entries_corrected.jsonl (produced by
maqayis_bab_corrector.py + run_full.sh) and provides typed lookups
for the Taaqol evidence pipeline.

Typed Lookup Protocol
─────────────────────
`typed_lookup(root_letters)` returns a `LookupResult` whose `.kind` is
exactly one of:

    FOUND_AUTO_AGREED         Root present, review_status == AUTO_AGREED
    FOUND_REVIEW_REQUIRED     Root present, review_status == REVIEW_REQUIRED
    MISSING_VOLUME_COVERAGE_GAP
                              First radical is in MAQAYIS_MISSING_INITIALS.
                              The volumes covering ا ب ت ث ج are absent from
                              the corpus — this is a *structural gap*, NOT
                              evidence that the root is absent from Ibn Faris.
                              MUST NOT be treated as ROOT_NOT_IN_MAQAYIS or
                              negative evidence.
    NOT_FOUND_IN_COVERED_VOLUME
                              First radical is covered but root was not
                              extracted — genuine absence in OCR output.
    REGISTRY_LOAD_FAILURE     JSONL failed to load; no verdict possible.
    INVALID_ROOT_INPUT        root_letters is empty, None, or non-string.

Coverage Contract
─────────────────
    MAQAYIS_MISSING_INITIALS = frozenset(['ا', 'ب', 'ت', 'ث', 'ج'])

Any root whose first character is in MAQAYIS_MISSING_INITIALS yields
MISSING_VOLUME_COVERAGE_GAP regardless of whether the root appears in the
index (OCR noise entries from those initials are excluded during load).

Bab Letter Contract
───────────────────
The registry uses `corrected_bab_letter` if present in the JSONL (set by
maqayis_bab_corrector.py), falling back to `bab_letter`.  The corrected
value is derived deterministically from `BAB_LETTER_MAP[first_radical]`.

Fail-Open Contract
──────────────────
Every public function catches all exceptions.  A missing or corrupt corpus
must never block Taaqol admission — Maqayis data is supplementary only.

Architecture Note
─────────────────
Maqayis provides `maqayis_root_catalog_evidence` in Taaqol's EvidenceContract.
It does not modify: admission verdict, rank, residual codes, native Taaqol
morphological output, RelationCandidate, MaqamContextBoundary, Ifadah, Hukm,
Manat, Tanzil, or AnswerAudit.  Supplementary enrichment only.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Repo path resolution ───────────────────────────────────────────────────────
# File lives at pipeline/taaqol_integration/maqayis_root_registry.py
# parents[0] = pipeline/taaqol_integration/
# parents[1] = pipeline/
# parents[2] = hokom/  ← repo root
_REPO_ROOT    = Path(__file__).resolve().parents[2]
_JSONL_DEFAULT = _REPO_ROOT / "data" / "maqaees" / "full" / "root_entries_corrected.jsonl"
# Fallback to original file if corrected version not yet generated
_JSONL_FALLBACK = _REPO_ROOT / "data" / "maqaees" / "full" / "root_entries.jsonl"


# ── Coverage constants ─────────────────────────────────────────────────────────

#: Initial letters for which the source volumes are absent from all 6 PDFs.
#: Lookups for roots beginning with these letters MUST yield
#: MISSING_VOLUME_COVERAGE_GAP — never NOT_FOUND_IN_COVERED_VOLUME or any
#: negative-evidence classification.
MAQAYIS_MISSING_INITIALS: frozenset[str] = frozenset(['ا', 'ب', 'ت', 'ث', 'ج'])

#: Variant Hamza forms that normalise to الألف for coverage purposes only.
#: The stored root_letters are never modified.
_HAMZA_VARIANTS: frozenset[str] = frozenset(['أ', 'إ', 'آ'])

#: Map from Arabic consonant to its full classical chapter name (bab_letter).
BAB_LETTER_MAP: dict[str, str] = {
    'ا': 'الألف',  'أ': 'الألف',  'إ': 'الألف',  'آ': 'الألف',
    'ب': 'الباء',  'ت': 'التاء',  'ث': 'الثاء',  'ج': 'الجيم',
    'ح': 'الحاء',  'خ': 'الخاء',  'د': 'الدال',  'ذ': 'الذال',
    'ر': 'الراء',  'ز': 'الزاي',  'س': 'السين',  'ش': 'الشين',
    'ص': 'الصاد',  'ض': 'الضاد',  'ط': 'الطاء',  'ظ': 'الظاء',
    'ع': 'العين',  'غ': 'الغين',  'ف': 'الفاء',  'ق': 'القاف',
    'ك': 'الكاف',  'ل': 'اللام',  'م': 'الميم',  'ن': 'النون',
    'ه': 'الهاء',  'و': 'الواو',  'ؤ': 'الواو',
    'ي': 'الياء',  'ئ': 'الياء',  'ة': 'التاء',
}


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MaqayisRootEntry:
    """
    Ibn Faris's record for one Arabic root from مقاييس اللغة.

    Fields
    ──────
    root_letters          Undiacritized consonants, e.g. "حد", "كتب"
    semantic_origin_type  SINGULAR | DUAL | TRIPLE | MULTIPLE | SOUND_ROOTS | NONE
    origin_count          Explicit count or None for MULTIPLE/SOUND_ROOTS/NONE
    review_status         AUTO_AGREED | REVIEW_REQUIRED
    entry_count           Number of JSONL entries containing this root
    source_pdfs           Tuple of PDF file names where this root was found
    heading_sample        Ibn Faris's original heading text (first occurrence)
    bab_letter            Corrected chapter letter name (e.g. "الحاء")
    original_bab_letter   As stored in raw OCR output (may differ from bab_letter)
    correction_version    Version of the bab-letter correction applied
    """
    root_letters:          str
    semantic_origin_type:  str
    origin_count:          Optional[int]
    review_status:         str
    entry_count:           int
    source_pdfs:           tuple
    heading_sample:        str
    bab_letter:            str          # corrected value
    original_bab_letter:   str          # raw OCR value
    correction_version:    str          # "v1" or ""


class LookupResultKind(enum.Enum):
    """Exact typed outcome of a Maqayis root lookup."""
    FOUND_AUTO_AGREED           = "FOUND_AUTO_AGREED"
    FOUND_REVIEW_REQUIRED       = "FOUND_REVIEW_REQUIRED"
    MISSING_VOLUME_COVERAGE_GAP = "MISSING_VOLUME_COVERAGE_GAP"
    NOT_FOUND_IN_COVERED_VOLUME = "NOT_FOUND_IN_COVERED_VOLUME"
    REGISTRY_LOAD_FAILURE       = "REGISTRY_LOAD_FAILURE"
    INVALID_ROOT_INPUT          = "INVALID_ROOT_INPUT"


@dataclass(frozen=True)
class LookupResult:
    """
    Typed result of `MaqayisRootRegistry.typed_lookup()`.

    Attributes
    ──────────
    kind    Exact discriminant (see LookupResultKind).
    entry   MaqayisRootEntry when kind is FOUND_*; None otherwise.

    Usage
    ─────
    result = registry.typed_lookup("حد")
    if result.kind == LookupResultKind.FOUND_AUTO_AGREED:
        # safe to emit positive origin evidence
        ...
    elif result.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP:
        # structural gap — do NOT treat as negative evidence
        ...
    """
    kind:  LookupResultKind
    entry: Optional[MaqayisRootEntry] = None

    # Convenience predicates
    @property
    def found(self) -> bool:
        return self.kind in (
            LookupResultKind.FOUND_AUTO_AGREED,
            LookupResultKind.FOUND_REVIEW_REQUIRED,
        )

    @property
    def auto_agreed(self) -> bool:
        return self.kind == LookupResultKind.FOUND_AUTO_AGREED

    @property
    def review_required(self) -> bool:
        return self.kind == LookupResultKind.FOUND_REVIEW_REQUIRED

    @property
    def coverage_gap(self) -> bool:
        return self.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP


# Pre-built sentinel results for non-found outcomes (no entry object needed)
_RESULT_COVERAGE_GAP   = LookupResult(LookupResultKind.MISSING_VOLUME_COVERAGE_GAP)
_RESULT_NOT_FOUND      = LookupResult(LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME)
_RESULT_LOAD_FAILURE   = LookupResult(LookupResultKind.REGISTRY_LOAD_FAILURE)
_RESULT_INVALID_INPUT  = LookupResult(LookupResultKind.INVALID_ROOT_INPUT)


# ── Registry ──────────────────────────────────────────────────────────────────

class MaqayisRootRegistry:
    """
    In-memory index of Ibn Faris root entries with typed lookup.

    Keyed by undiacritized root letters. Entries from MAQAYIS_MISSING_INITIALS
    are excluded from the index during load (they are OCR noise entries that
    cannot represent real root attestations for those volumes).

    Load cost: ~3,500 JSONL lines ≈ 5–15 ms cold start.
    Memory:    < 3 MB.
    Thread-safety: index is read-only after construction.
    """

    def __init__(self, jsonl_path: str | Path | None = None) -> None:
        self._index:      dict[str, MaqayisRootEntry] = {}
        self._load_error: Optional[str] = None

        if jsonl_path is None:
            # Use corrected file; fall back to original if corrected not yet generated
            if _JSONL_DEFAULT.exists():
                jsonl_path = _JSONL_DEFAULT
            elif _JSONL_FALLBACK.exists():
                jsonl_path = _JSONL_FALLBACK
            else:
                jsonl_path = _JSONL_DEFAULT  # will trigger "file not found" path

        self._source_path = str(jsonl_path)
        try:
            self._load(Path(jsonl_path))
        except Exception as exc:
            self._load_error = str(exc)

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self, path: Path) -> None:
        if not path.exists():
            # Corpus not yet generated — fail silent, registry is empty.
            # Callers will receive REGISTRY_LOAD_FAILURE via typed_lookup.
            self._load_error = f"Corpus file not found: {path}"
            return

        # Group raw JSONL entries by root_letters
        raw: dict[str, list[dict]] = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                root = (entry.get("root_letters") or "").strip()
                if not root:
                    continue
                # Exclude OCR noise entries for missing-volume initials
                if self._is_missing_initial(root):
                    continue
                raw.setdefault(root, []).append(entry)

        # Build MaqayisRootEntry for each unique root
        for root, pages in raw.items():
            self._index[root] = self._merge_pages(root, pages)

    @staticmethod
    def _is_missing_initial(root: str) -> bool:
        """True if the first radical falls in the structurally absent volumes."""
        first = root[0] if root else ""
        # Normalise Hamza variants to ا for coverage check
        if first in _HAMZA_VARIANTS:
            first = 'ا'
        return first in MAQAYIS_MISSING_INITIALS

    @staticmethod
    def _merge_pages(root: str, pages: list[dict]) -> MaqayisRootEntry:
        """
        Merge multiple JSONL entries for the same root into one MaqayisRootEntry.

        Rules
        ─────
        • review_status: AUTO_AGREED wins over REVIEW_REQUIRED if any page agrees.
        • origin_type: first page with non-NONE/UNKNOWN type wins.
        • bab_letter: use corrected_bab_letter if present; else bab_letter;
          else derive from BAB_LETTER_MAP.
        • heading_sample: first occurrence.
        • source_pdfs: deduped, order-preserved.
        """
        # ── review_status ─────────────────────────────────────────────────────
        statuses = [p.get("review_status", "REVIEW_REQUIRED") for p in pages]
        review_status = (
            "AUTO_AGREED" if "AUTO_AGREED" in statuses else "REVIEW_REQUIRED"
        )

        # ── origin type: take from AUTO_AGREED page first, else first non-NONE ─
        preferred_pages = (
            [p for p in pages if p.get("review_status") == "AUTO_AGREED"]
            or pages
        )
        detected = [
            p for p in preferred_pages
            if p.get("semantic_origin_type") not in ("NONE", "UNKNOWN", None, "")
        ]
        if detected:
            winner       = detected[0]
            origin_type  = winner["semantic_origin_type"]
            origin_count = winner.get("origin_count")
        else:
            origin_type  = "NONE"
            origin_count = None

        # ── bab letter (corrected first) ──────────────────────────────────────
        corrected_bab = ""
        original_bab  = ""
        correction_ver = ""

        # Look for corrected_bab_letter written by maqayis_bab_corrector.py
        for p in pages:
            if p.get("corrected_bab_letter"):
                corrected_bab  = p["corrected_bab_letter"]
                original_bab   = p.get("original_bab_letter", p.get("bab_letter", ""))
                correction_ver = p.get("correction_version", "v1")
                break

        if not corrected_bab:
            # Fall back: derive authoritatively from first radical
            first_radical = root[0] if root else ""
            corrected_bab  = BAB_LETTER_MAP.get(first_radical, "")
            # Find original value from OCR
            original_bab   = next((p.get("bab_letter", "") for p in pages if p.get("bab_letter")), "")
            correction_ver = "v1-derived"

        # ── provenance ────────────────────────────────────────────────────────
        pdfs = list(dict.fromkeys(p.get("source_pdf", "") for p in pages if p.get("source_pdf")))
        heading = next((p["root_heading_text"] for p in pages if p.get("root_heading_text")), "")

        return MaqayisRootEntry(
            root_letters         = root,
            semantic_origin_type = origin_type,
            origin_count         = origin_count,
            review_status        = review_status,
            entry_count          = len(pages),
            source_pdfs          = tuple(pdfs),
            heading_sample       = heading,
            bab_letter           = corrected_bab,
            original_bab_letter  = original_bab,
            correction_version   = correction_ver,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def typed_lookup(self, root_letters: str) -> LookupResult:
        """
        Return a typed LookupResult for *root_letters*.

        This is the authoritative lookup method.  The .kind discriminant
        must be inspected before using .entry.

        Never raises.
        """
        try:
            # ── Validate input ─────────────────────────────────────────────
            if not root_letters or not isinstance(root_letters, str):
                return _RESULT_INVALID_INPUT

            root = root_letters.strip()
            if not root:
                return _RESULT_INVALID_INPUT

            # ── Registry load failure ──────────────────────────────────────
            if self._load_error and not self._index:
                return _RESULT_LOAD_FAILURE

            # ── Coverage gap (structural) ──────────────────────────────────
            if self._is_missing_initial(root):
                return _RESULT_COVERAGE_GAP

            # ── Index lookup ───────────────────────────────────────────────
            entry = self._index.get(root)
            if entry is None:
                return _RESULT_NOT_FOUND

            kind = (
                LookupResultKind.FOUND_AUTO_AGREED
                if entry.review_status == "AUTO_AGREED"
                else LookupResultKind.FOUND_REVIEW_REQUIRED
            )
            return LookupResult(kind=kind, entry=entry)

        except Exception:
            return _RESULT_LOAD_FAILURE

    def lookup(self, root_letters: str) -> Optional[MaqayisRootEntry]:
        """
        Backward-compatible convenience wrapper.

        Returns the MaqayisRootEntry if found (any review_status), or None.
        Prefer typed_lookup() for production code so the review_status
        contract can be enforced by the caller.
        """
        result = self.typed_lookup(root_letters)
        return result.entry  # None for all non-FOUND kinds

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def total_roots(self) -> int:
        """Number of unique roots indexed (excluding missing-volume initials)."""
        return len(self._index)

    @property
    def load_error(self) -> Optional[str]:
        """Non-None if the JSONL failed to load."""
        return self._load_error

    @property
    def source_path(self) -> str:
        return self._source_path

    @property
    def is_healthy(self) -> bool:
        """True if the registry loaded successfully and has entries."""
        return not self._load_error and len(self._index) > 0

    def __len__(self) -> int:
        return len(self._index)

    def __repr__(self) -> str:
        if self._load_error:
            return f"MaqayisRootRegistry(LOAD_ERROR: {self._load_error!r})"
        return (
            f"MaqayisRootRegistry({self.total_roots} roots, "
            f"path={self._source_path!r})"
        )


# ── Module-level singleton ─────────────────────────────────────────────────────

_singleton: Optional[MaqayisRootRegistry] = None


def get_registry() -> MaqayisRootRegistry:
    """
    Return the singleton MaqayisRootRegistry.

    Loads on first call (~5–15 ms); subsequent calls return cached instance.
    Thread-safe: construction is idempotent in CPython (GIL held during
    assignment).  A race between two threads may build the registry twice
    on the very first call — harmless, both produce identical objects.
    """
    global _singleton
    if _singleton is None:
        _singleton = MaqayisRootRegistry()
    return _singleton


def typed_lookup(root_letters: str) -> LookupResult:
    """
    Typed lookup in the singleton registry.  Never raises.

    Returns a LookupResult whose .kind is one of:
        FOUND_AUTO_AGREED | FOUND_REVIEW_REQUIRED |
        MISSING_VOLUME_COVERAGE_GAP | NOT_FOUND_IN_COVERED_VOLUME |
        REGISTRY_LOAD_FAILURE | INVALID_ROOT_INPUT
    """
    try:
        return get_registry().typed_lookup(root_letters)
    except Exception:
        return _RESULT_LOAD_FAILURE


def lookup(root_letters: str) -> Optional[MaqayisRootEntry]:
    """
    Backward-compatible convenience wrapper.  Never raises.

    Returns MaqayisRootEntry or None.
    Use typed_lookup() for production code requiring the full result kind.
    """
    try:
        return get_registry().lookup(root_letters)
    except Exception:
        return None


# ── CLI self-check ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    reg = MaqayisRootRegistry()
    if reg.load_error:
        print(f"LOAD ERROR: {reg.load_error}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {reg.total_roots} unique roots from {reg.source_path}")
    print(f"Registry healthy: {reg.is_healthy}")

    samples = [
        ("حد",   "should be FOUND (حاء chapter)"),
        ("كتب",  "should be FOUND"),
        ("دين",  "should be FOUND"),
        ("بسط",  "MISSING_VOLUME_COVERAGE_GAP (ب)"),
        ("تكل",  "MISSING_VOLUME_COVERAGE_GAP (ت)"),
        ("ثلث",  "MISSING_VOLUME_COVERAGE_GAP (ث)"),
        ("جمل",  "MISSING_VOLUME_COVERAGE_GAP (ج)"),
        ("أمر",  "MISSING_VOLUME_COVERAGE_GAP (ا/أ)"),
        ("zzz",  "NOT_FOUND_IN_COVERED_VOLUME"),
        ("",     "INVALID_ROOT_INPUT"),
    ]

    print()
    for root, note in samples:
        result = reg.typed_lookup(root)
        entry_info = ""
        if result.entry:
            e = result.entry
            entry_info = (
                f" → {e.semantic_origin_type}(count={e.origin_count}) "
                f"bab={e.bab_letter!r} status={e.review_status}"
            )
        print(f"  {root!r:8}  {result.kind.value:<35} {note}{entry_info}")
