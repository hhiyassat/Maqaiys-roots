"""
maqayis_source_evidence_builder.py — Layer 1 builder: SourceEvidence + RootIdentityCandidate
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Builds SourceEvidence, RootIdentityCandidate, and SourceClaimRecord (Layer 1 of
MaqayisSourceBundle) from root_entries.jsonl and lines.jsonl.

Constitutional contract (enforced here):
  • Maqayis NEVER extracts a root from running text — only from entry headings.
    hokom_canonical_root_ref is left None; the Hokom interface fills it later.
  • Machine code NEVER promotes to IDENTITY_VERIFIED, TEXT_VERIFIED, or
    LEXICALLY_REVIEWED. Only human reviewers may set those states.
  • OCR candidates are never represented as verified lexical evidence.
  • If a blocking residual is added, OntologyCandidateProfile MUST NOT be built
    (enforced by ExtractionMetadata.is_ontology_buildable()).

Entry path routing (by entry_kind):
  CHAPTER_HEADER   → SourceEvidence only.  No claim, no origin, no OntoCandidates.
  CROSS_REFERENCE  → SourceEvidence + SourceClaimRecord(claim_kind=CROSS_REFERENCE).
  NEGATIVE_ENTRY   → SourceEvidence + SourceClaimRecord(claim_kind=NEGATIVE_CLAIM).
  DISPUTED_ENTRY   → SourceEvidence + SourceClaimRecord(claim_kind=DISPUTED_CLAIM).
  ROOT_ENTRY       → Full pipeline — all four layers.
  OCR_NOISE        → SourceEvidence only + MISSING_SOURCE_PASSAGE residual.

Blocking residuals added by THIS builder:
  ROOT_IDENTITY_UNRESOLVED  — bab_letter empty, corrected_bab_letter also empty.
  ROOT_IDENTITY_CONFLICT    — root_letters first letter ≠ bab_letter prefix AND
                              no correction resolves the mismatch.
  MISSING_SOURCE_PASSAGE    — all body_line_ids resolve to empty / whitespace text.
  TEXT_VERIFICATION_FAILED  — OCR confidence < OCR_CONF_THRESHOLD across all lines
                              AND no human_text present.

Data sources:
  root_entries.jsonl          — primary entry catalogue (3 486 entries)
  root_entries_corrected.jsonl — same entries with bab-letter corrections applied
  data/maqaees/full/lines.jsonl — all OCR line records (≈52 000 lines)

Preferred data source priority:
  root_entries_corrected.jsonl overrides root_entries.jsonl when both exist.
  For line text: human_text > corrected_ocr > raw_ocr.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .maqayis_body_loader import MaqayisBodyLoader
from .maqayis_source_schema import (
    AUTHOR_ID,
    BLOCKING_RESIDUALS,
    ONTOLOGY_CANDIDATE_ONLY,
    SCHEMA_VERSION,
    WORK_ID,
    AggregationState,
    AssertionStrength,
    AuthorPosition,
    ClaimAttribution,
    ClaimKind,
    CoverageState,
    EntryKind,
    EvidenceStatus,
    ExtractionMetadata,
    ExtractionMethod,
    HeadingType,
    LexicalClaimGraph,
    MaqayisSourceBundle,
    OntologyCandidateProfile,
    OriginType,
    Polarity,
    ResidualType,
    ReviewState,
    RootIdentityCandidate,
    RootIdentityMatch,
    SemanticOriginGraph,
    SourceClaimRecord,
    SourceEvidence,
    TextReviewState,
)


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

#: Minimum average OCR confidence before TEXT_VERIFICATION_FAILED is added.
OCR_CONF_THRESHOLD: float = 0.60

#: Edition ID for the Maqayis edition in use.
EDITION_ID: str = "MAQAYIS-DKI-BEIRUT-1420H"

#: Known OCR character confusions in Maqayis corpus (raw → expected).
#: Derived from comparing raw_candidates vs corrected_candidates across 52 000 lines.
OCR_CHAR_CONFUSIONS: List[Tuple[str, str]] = [
    ("وب", "وي"),   # وب → وي  (وبقال → ويقال)
    ("هـ", "ه"),          # هـ → ه   (final marker artefact)
    ("ان", "إن"),    # ان → إن  (hamza drop)
    ("الى", "الي"),  # الى → الي
    ("�", "?"),                     # replacement chars
]

#: Mapping from source_pdf filename to volume number.
_VOLUME_MAP: Dict[str, int] = {
    "01.pdf": 1, "02.pdf": 2, "03.pdf": 3,
    "04.pdf": 4, "05.pdf": 5, "06.pdf": 6,
}

#: semantic_origin_type values that map to CHAPTER_HEADER heading.
_CHAPTER_HEADER_TYPES = frozenset({"CHAPTER_HEADER"})

#: semantic_origin_type values that map to CROSS_REFERENCE heading.
_CROSS_REFERENCE_TYPES = frozenset({"CROSS_REFERENCE"})

#: semantic_origin_type values that map to NOT_ROOT heading (no valid origin).
_NOT_ROOT_TYPES = frozenset({"NOT_ROOT", "NONE"})

#: semantic_origin_type values that signal a full root entry.
_ROOT_ENTRY_TYPES = frozenset({
    "SINGULAR", "DUAL", "TRIPLE", "MULTIPLE", "SOUND_ROOTS",
})

#: Patterns that detect cross-reference phrasing in heading text.
_XREF_RE = re.compile(
    r"(?:قد\s+مضى|يُنظر|انظر|مرَّ\s+ذكره|تقدَّم|راجع)",
    re.UNICODE,
)

#: Assertion-strength markers in semantic_origin_text.
_STRENGTH_MARKERS: List[Tuple[re.Pattern, AssertionStrength]] = [
    (re.compile(r"\bلَا\s+(?:شكَّ|ريب)\b"), AssertionStrength.EMPHATIC_ASSERTED),
    (re.compile(r"\bوَلَا\s+خلاف\b"), AssertionStrength.EMPHATIC_ASSERTED),
    (re.compile(r"\bيدلُّ\s+على\b|\bأصله\b"), AssertionStrength.ASSERTED),
    (re.compile(r"\bوأَحسَب\b|\bأَظنُّ\b|\bيُشبه\b"), AssertionStrength.PROBABLE),
    (re.compile(r"\bيُقال\b"), AssertionStrength.POSSIBLE),
    (re.compile(r"\bقال\s+(?:فلان|بعض)\b"), AssertionStrength.REPORTED),
    (re.compile(r"\bولا\s+أَرَى\b|\bلا\s+أَعرف\b"), AssertionStrength.DOUBTFUL),
    (re.compile(r"\bوليس\s+بشيء\b|\bولا\s+أَحسبه\b"), AssertionStrength.REJECTED),
]


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — PRIVATE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _volume_from_filename(filename: str) -> int:
    """Return the volume number derived from the PDF filename (e.g. '01.pdf' → 1)."""
    return _VOLUME_MAP.get(filename, 0)


def _passage_checksum(text: str) -> str:
    """SHA-256 hex digest of the normalised passage text (first 16 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _best_line_text(line_obj: dict) -> str:
    """Return the highest-quality text from a line object.

    Priority: human_text > corrected_ocr > raw_ocr > ''.
    """
    if line_obj.get("human_text"):
        return line_obj["human_text"]
    if line_obj.get("corrected_ocr"):
        return line_obj["corrected_ocr"]
    return line_obj.get("raw_ocr") or ""


def _line_ocr_confidence(line_obj: dict) -> float:
    """Return the best-candidate OCR confidence for a line (0.0 – 1.0)."""
    candidates = line_obj.get("raw_candidates") or []
    if candidates:
        return float(candidates[0].get("confidence", 0.0))
    return 0.0


def _aggregate_ocr_confidence(line_objects: List[dict]) -> float:
    """Mean OCR confidence across all provided line objects (0.0 if empty)."""
    if not line_objects:
        return 0.0
    confidences = [_line_ocr_confidence(lo) for lo in line_objects]
    return sum(confidences) / len(confidences)


def _replacement_char_count(text: str) -> int:
    """Count U+FFFD replacement characters in the raw OCR text."""
    return text.count("�")


def _detect_confusions(raw: str, corrected: str) -> List[str]:
    """Return a list of human-readable confusion descriptions found in raw text."""
    found: List[str] = []
    for raw_pat, expected in OCR_CHAR_CONFUSIONS:
        if raw_pat in raw and raw_pat not in corrected:
            found.append(f"'{raw_pat}'→'{expected}'")
    return found


def _map_text_review_state(review_status: str, human_text: Optional[str]) -> TextReviewState:
    """Map line-level review_status to TextReviewState.

    Constitutional: NEVER returns TEXT_VERIFIED — that requires a human reviewer.
    human_text presence → HUMAN_CORRECTED (still not TEXT_VERIFIED until reviewed).
    """
    if human_text:
        return TextReviewState.HUMAN_CORRECTED
    if review_status in ("AUTO_AGREED", "AUTO_ACCEPTED"):
        return TextReviewState.TEXT_CANDIDATE
    return TextReviewState.TEXT_CANDIDATE


def _map_coverage_state(body_line_ids: List[str], resolved_text: str) -> CoverageState:
    """Determine coverage state from body_line_ids and the resolved body text."""
    if not body_line_ids:
        return CoverageState.MISSING_VOLUME
    if not resolved_text or not resolved_text.strip():
        return CoverageState.UNREADABLE_PAGE
    return CoverageState.COVERED


def _map_origin_type(semantic_origin_type: str) -> OriginType:
    """Map semantic_origin_type string to OriginType enum."""
    mapping = {
        "SINGULAR":    OriginType.SINGULAR,
        "DUAL":        OriginType.DUAL,
        "TRIPLE":      OriginType.TRIPLE,
        "MULTIPLE":    OriginType.MULTIPLE,
        "SOUND_ROOTS": OriginType.SOUND_ROOTS,
        "NONE":        OriginType.NOT_EXTRACTED,
        "NOT_ROOT":    OriginType.NOT_EXTRACTED,
        "CHAPTER_HEADER": OriginType.NOT_EXTRACTED,
        "CROSS_REFERENCE": OriginType.NOT_EXTRACTED,
    }
    return mapping.get(semantic_origin_type, OriginType.UNKNOWN)


def _map_claim_kind(semantic_origin_type: str, heading_text: str) -> ClaimKind:
    """Map semantic_origin_type (and optionally heading text) to ClaimKind."""
    if semantic_origin_type == "CROSS_REFERENCE":
        return ClaimKind.CROSS_REFERENCE
    if semantic_origin_type == "CHAPTER_HEADER":
        # No claim for chapter headers; caller should not build SourceClaimRecord.
        return ClaimKind.CROSS_REFERENCE  # sentinel — builder skips claim anyway
    if semantic_origin_type == "NOT_ROOT":
        return ClaimKind.NEGATIVE_CLAIM
    if semantic_origin_type == "NONE":
        # Examine heading text for cross-reference phrasing
        if _XREF_RE.search(heading_text or ""):
            return ClaimKind.CROSS_REFERENCE
        return ClaimKind.INCOMPLETE_CLAIM
    if semantic_origin_type in _ROOT_ENTRY_TYPES:
        return ClaimKind.POSITIVE_ORIGIN
    return ClaimKind.POSITIVE_ORIGIN


def _map_heading_type(semantic_origin_type: str, heading_text: str) -> HeadingType:
    """Derive HeadingType from semantic_origin_type and heading text."""
    if semantic_origin_type in _CHAPTER_HEADER_TYPES:
        return HeadingType.CHAPTER_HEADER
    if semantic_origin_type in _CROSS_REFERENCE_TYPES:
        return HeadingType.CROSS_REFERENCE
    if semantic_origin_type == "NOT_ROOT":
        return HeadingType.NOT_ROOT
    if semantic_origin_type == "NONE":
        # Check for CHAPTER_HEADER-like single-letter headings
        stripped = re.sub(r"[()،\s]", "", heading_text or "")
        if len(stripped) <= 2 and re.match(r"^[؀-ۿ]+$", stripped):
            return HeadingType.CHAPTER_HEADER
        if _XREF_RE.search(heading_text or ""):
            return HeadingType.CROSS_REFERENCE
        return HeadingType.UNCERTAIN
    if semantic_origin_type in _ROOT_ENTRY_TYPES:
        return HeadingType.ROOT_ENTRY
    return HeadingType.UNCERTAIN


def _map_entry_kind(
    heading_type: HeadingType,
    claim_kind: ClaimKind,
    body_text: str,
) -> EntryKind:
    """Derive EntryKind from heading type and body text availability."""
    if heading_type == HeadingType.CHAPTER_HEADER:
        return EntryKind.OCR_NOISE
    if heading_type == HeadingType.CROSS_REFERENCE:
        return EntryKind.CROSS_REFERENCE
    if heading_type == HeadingType.NOT_ROOT:
        return EntryKind.NEGATIVE_ENTRY
    if heading_type == HeadingType.UNCERTAIN:
        if not body_text or not body_text.strip():
            return EntryKind.OCR_NOISE
        return EntryKind.SUBENTRY
    if heading_type == HeadingType.ROOT_ENTRY:
        return EntryKind.ROOT_ENTRY
    return EntryKind.ROOT_ENTRY


def _map_root_identity_match(entry: dict) -> RootIdentityMatch:
    """
    Determine RootIdentityMatch from correction fields.

    Exact:            corrected_bab_letter matches bab_letter (or both empty with root given)
    NormalizedMatch:  bab_letter was corrected to corrected_bab_letter
    Conflict:         correction_reason indicates a conflict
    Unresolved:       bab_letter empty, no corrected_bab_letter either
    """
    bab = entry.get("bab_letter") or ""
    corrected = entry.get("corrected_bab_letter") or ""
    reason = entry.get("correction_reason") or ""

    if "conflict" in reason.lower():
        return RootIdentityMatch.CONFLICT

    if bab == corrected:
        return RootIdentityMatch.EXACT

    # Normalise Arabic hamza variants for comparison
    def _norm(s: str) -> str:
        return (
            s.strip()
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
        )

    if corrected and _norm(bab) == _norm(corrected):
        return RootIdentityMatch.NORMALIZED_MATCH

    if corrected and corrected != bab:
        return RootIdentityMatch.NORMALIZED_MATCH  # correction applied = resolved

    if not bab and not corrected:
        return RootIdentityMatch.UNRESOLVED

    return RootIdentityMatch.EXACT


def _assert_strength_from_text(text: Optional[str]) -> AssertionStrength:
    """
    Heuristic: scan semantic_origin_text for assertion-strength markers.
    Returns AssertionStrength.ASSERTED as default when no marker is found.
    """
    if not text:
        return AssertionStrength.UNKNOWN
    for pattern, strength in _STRENGTH_MARKERS:
        if pattern.search(text):
            return strength
    return AssertionStrength.ASSERTED


def _new_id(prefix: str) -> str:
    """Generate a short UUID-based identifier with a prefix."""
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — LINE INDEX
# ═══════════════════════════════════════════════════════════════════════════════

class LineIndex:
    """
    Lazy-loaded index of all OCR line records from lines.jsonl.

    Provides O(1) lookup by line_id and batch retrieval for entry line sets.
    """

    def __init__(self, lines_jsonl: "pathlib.Path | str") -> None:
        self._path = pathlib.Path(lines_jsonl)
        self._index: Dict[str, dict] = {}
        self._loaded = False

    def _load(self) -> None:
        index: Dict[str, dict] = {}
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
        self._index = index
        self._loaded = True

    def _ensure(self) -> None:
        if not self._loaded:
            self._load()

    def get(self, line_id: str) -> Optional[dict]:
        self._ensure()
        return self._index.get(line_id)

    def get_many(self, line_ids: List[str]) -> List[dict]:
        self._ensure()
        return [self._index[lid] for lid in line_ids if lid in self._index]

    def __len__(self) -> int:
        self._ensure()
        return len(self._index)


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — SOURCE EVIDENCE BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class SourceEvidenceBuilder:
    """
    Builds Layer 1 of MaqayisSourceBundle from a root_entries dict + line index.

    Usage::

        builder = SourceEvidenceBuilder(
            lines_jsonl="data/maqaees/full/lines.jsonl",
            entries_jsonl="data/maqaees/full/root_entries_corrected.jsonl",
        )
        for bundle in builder.iter_bundles():
            process(bundle)
    """

    def __init__(
        self,
        lines_jsonl: "pathlib.Path | str",
        entries_jsonl: "pathlib.Path | str",
    ) -> None:
        self._lines = LineIndex(pathlib.Path(lines_jsonl))
        self._entries_path = pathlib.Path(entries_jsonl)

    # ── Entry iteration ───────────────────────────────────────────────────────

    def _iter_entries(self) -> Iterator[dict]:
        with open(self._entries_path, encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    # ── SourceEvidence construction ───────────────────────────────────────────

    def build_source_evidence(
        self,
        entry: dict,
        body_text: str,
        all_line_objects: List[dict],
    ) -> SourceEvidence:
        """
        Build a SourceEvidence record from a root_entry dict.

        Covers all 25 SourceEvidence fields defined in maqayis_source_schema.py:
          Source identity, passage location, text layers, OCR metadata, coverage.

        Constitutional: text_review_state is never TEXT_VERIFIED (machine code only).
        """
        filename = entry.get("source_pdf") or ""
        pdf_page = entry.get("pdf_page") or 0
        entry_id = entry.get("entry_id") or ""
        body_line_ids = entry.get("body_line_ids") or []
        line_ids = entry.get("line_ids") or []
        poetry_ids: set = set(entry.get("poetry_line_ids") or [])

        # Collect line objects for body lines only (poetry excluded per constitution)
        body_only_ids = [lid for lid in body_line_ids if lid not in poetry_ids]
        body_line_objs = self._lines.get_many(body_only_ids)

        # Text layers
        raw_texts = [lo.get("raw_ocr") or "" for lo in body_line_objs]
        corrected_texts = [lo.get("corrected_ocr") or "" for lo in body_line_objs]
        human_texts = [lo.get("human_text") or "" for lo in body_line_objs]

        raw_ocr_text = " ".join(t for t in raw_texts if t)
        normalized_text = " ".join(t for t in corrected_texts if t)
        human_corrected_text: Optional[str] = (
            " ".join(t for t in human_texts if t) or None
        )

        # OCR metadata
        ocr_confidence = _aggregate_ocr_confidence(body_line_objs)

        # Review state: aggregate across all lines
        any_human = any(lo.get("human_text") for lo in body_line_objs)
        review_statuses = [lo.get("review_status") or "" for lo in body_line_objs]
        dominant_review = (
            "HUMAN_CORRECTED" if any_human
            else (review_statuses[0] if review_statuses else "")
        )
        text_review_state = _map_text_review_state(dominant_review, human_corrected_text)

        # Coverage
        coverage_state = _map_coverage_state(body_line_ids, body_text)

        # Bounding box: union of all body line bounding boxes
        bboxes = [
            lo.get("bounding_box") for lo in body_line_objs
            if lo.get("bounding_box")
        ]
        if bboxes:
            xs = [b["x"] for b in bboxes]
            ys = [b["y"] for b in bboxes]
            ws = [b["x"] + b["w"] for b in bboxes]
            hs = [b["y"] + b["h"] for b in bboxes]
            bounding_box: Optional[dict] = {
                "x": min(xs), "y": min(ys),
                "w": max(ws) - min(xs), "h": max(hs) - min(ys),
            }
        else:
            bounding_box = None

        # Replacement char count across raw texts
        replacement_count = sum(_replacement_char_count(t) for t in raw_texts)

        # Character confusion detection
        confusions: List[str] = []
        for raw_t, corr_t in zip(raw_texts, corrected_texts):
            confusions.extend(_detect_confusions(raw_t, corr_t))
        suspected_confusions = list(dict.fromkeys(confusions))  # deduplicate, keep order

        # Passage checksum on best available text
        best = human_corrected_text or normalized_text or raw_ocr_text
        checksum = _passage_checksum(best)

        return SourceEvidence(
            # Source identity
            source_id=_new_id("SE"),
            work_id=WORK_ID,
            author_id=AUTHOR_ID,
            edition_id=EDITION_ID,
            # Bibliographic location
            volume_number=_volume_from_filename(filename),
            filename=filename,
            pdf_sha256=None,            # populated by ingestion pipeline
            page_count=None,            # populated by ingestion pipeline
            # Passage location
            passage_id=_new_id("PASS"),
            page_number=pdf_page,
            entry_id=entry_id,
            line_ids=body_only_ids,
            char_start=None,
            char_end=None,
            bounding_box=bounding_box,
            image_ref=None,
            # Text layers
            raw_ocr_text=raw_ocr_text or None,
            normalized_text=normalized_text or None,
            human_corrected_text=human_corrected_text,
            # OCR metadata
            ocr_engine=None,            # engine name recorded at ingestion
            ocr_pass_id=None,
            ocr_confidence=ocr_confidence,
            text_review_state=text_review_state,
            passage_checksum=checksum,
            # OCR quality indicators
            replacement_character_count=replacement_count,
            suspected_character_confusions=suspected_confusions,
            # Coverage
            coverage_state=coverage_state,
        )

    # ── RootIdentityCandidate construction ───────────────────────────────────

    def build_root_identity_candidate(self, entry: dict) -> RootIdentityCandidate:
        """
        Build RootIdentityCandidate from the entry heading.

        Constitutional:
          - hokom_canonical_root_ref = None (Hokom fills it via pipeline interface)
          - correction_review_state = EXTRACTION_CANDIDATE (never IDENTITY_VERIFIED)
          - root_letters comes from the heading field, NOT from running body text
        """
        root_letters = entry.get("root_letters") or ""
        bab_letter = entry.get("bab_letter") or ""
        heading_text = entry.get("root_heading_text") or ""
        semantic_origin_type = entry.get("semantic_origin_type") or "NONE"

        heading_type = _map_heading_type(semantic_origin_type, heading_text)
        root_identity_match = _map_root_identity_match(entry)

        # Root length candidate from root_letters
        letter_count = len(
            re.sub(r"[^؀-ۿ]", "", root_letters)
        )
        if letter_count == 0:
            letter_count = None  # type: ignore[assignment]

        # Correction confidence: 1.0 if exact, 0.9 if normalised, 0.5 if conflict
        match_confidence: float
        if root_identity_match == RootIdentityMatch.EXACT:
            match_confidence = 1.0
        elif root_identity_match == RootIdentityMatch.NORMALIZED_MATCH:
            match_confidence = 0.9
        elif root_identity_match == RootIdentityMatch.CONFLICT:
            match_confidence = 0.3
        else:
            match_confidence = 0.0  # UNRESOLVED

        return RootIdentityCandidate(
            # Source-side identity
            source_root_candidate=root_letters,
            candidate_letters=list(re.sub(r"[^؀-ۿ]", "", root_letters)),
            root_length_candidate=letter_count,
            source_bab_letter=bab_letter,
            heading_type=heading_type,
            # Hokom interface (left None; Hokom fills after pipeline handoff)
            hokom_canonical_root_ref=None,
            root_identity_match=root_identity_match,
            match_confidence=match_confidence,
            # Bab-letter correction record
            original_bab_letter=entry.get("original_bab_letter") or bab_letter,
            corrected_bab_letter=entry.get("corrected_bab_letter") or bab_letter,
            correction_reason=entry.get("correction_reason"),
            correction_version=entry.get("correction_version"),
            correction_review_state=ReviewState.MACHINE_CANDIDATE,
            # Constitutional: never IDENTITY_VERIFIED from machine
        )

    # ── SourceClaimRecord construction ───────────────────────────────────────

    def build_source_claim_record(
        self,
        entry: dict,
        claim_kind: ClaimKind,
    ) -> SourceClaimRecord:
        """
        Build SourceClaimRecord from the entry's origin claim fields.

        This covers the lexical claim the author makes about the root:
          - claim_kind (entry-level, maps to the overall nature of the claim)
          - origin_type (how many semantic origins the root has)
          - assertion_strength (how strongly the claim is asserted)
          - attribution (who makes the claim — Ibn Faris by default)
          - polarity (positive / negative / uncertain)
        """
        semantic_origin_type = entry.get("semantic_origin_type") or "NONE"
        origin_text = entry.get("semantic_origin_text") or ""
        origin_count = entry.get("origin_count")

        origin_type = _map_origin_type(semantic_origin_type)
        assertion_strength = _assert_strength_from_text(origin_text)

        # Attribution: default Ibn Faris; CROSS_REFERENCE may cite another scholar
        attribution = ClaimAttribution.IBN_FARIS

        # Polarity
        if claim_kind == ClaimKind.NEGATIVE_CLAIM:
            polarity = Polarity.NEGATIVE
        elif claim_kind == ClaimKind.CROSS_REFERENCE:
            polarity = Polarity.UNCERTAIN
        else:
            polarity = Polarity.POSITIVE

        # Author position
        if claim_kind == ClaimKind.DISPUTED_CLAIM:
            author_position = AuthorPosition.UNRESOLVED
        elif claim_kind == ClaimKind.NEGATIVE_CLAIM:
            author_position = AuthorPosition.REJECTED
        else:
            author_position = AuthorPosition.ADOPTED

        # Span: none yet — span extraction happens in claim extractor
        return SourceClaimRecord(
            claim_kind=claim_kind,
            origin_type=origin_type,
            declared_origin_count=origin_count,
            origin_count_explicit=(origin_count is not None),
            origin_count_expression=None,
            raw_claim_text=origin_text or None,
            normalized_claim_text=origin_text or None,
            claim_span_start=None,
            claim_span_end=None,
            assertion_strength=assertion_strength,
            claim_attribution=attribution,
            attributed_name=None,
            author_position=author_position,
            claim_scope_language="ar",
            claim_scope_lexical="ROOT_ENTRY",
            polarity=polarity,
        )

    # ── ExtractionMetadata construction ──────────────────────────────────────

    def build_extraction_metadata(
        self,
        entry: dict,
        root_id: RootIdentityCandidate,
        entry_kind: EntryKind,
        body_text: str,
        ocr_confidence: float,
    ) -> ExtractionMetadata:
        """
        Build ExtractionMetadata and add appropriate blocking residuals.

        Blocking residual logic (all four cases):
          ROOT_IDENTITY_UNRESOLVED  → root_identity_match == UNRESOLVED
          ROOT_IDENTITY_CONFLICT    → root_identity_match == CONFLICT
          MISSING_SOURCE_PASSAGE    → body_text is empty for ROOT_ENTRY
          TEXT_VERIFICATION_FAILED  → ocr_confidence < threshold AND no human text
        """
        meta = ExtractionMetadata(
            extraction_method=ExtractionMethod.RULE_BASED,
            explicitness=None,
            extraction_confidence=ocr_confidence,
            review_state=ReviewState.MACHINE_CANDIDATE,
            evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
            residuals=[],
            counterevidence_ids=[],
            version=SCHEMA_VERSION,
            supersedes_id=None,
        )

        # ROOT_IDENTITY_UNRESOLVED
        if root_id.root_identity_match == RootIdentityMatch.UNRESOLVED:
            meta.add_residual(ResidualType.ROOT_IDENTITY_UNRESOLVED)

        # ROOT_IDENTITY_CONFLICT
        if root_id.root_identity_match == RootIdentityMatch.CONFLICT:
            meta.add_residual(ResidualType.ROOT_IDENTITY_CONFLICT)

        # MISSING_SOURCE_PASSAGE — only for entries that should have body text
        if entry_kind in (EntryKind.ROOT_ENTRY, EntryKind.NEGATIVE_ENTRY):
            if not body_text or not body_text.strip():
                meta.add_residual(ResidualType.MISSING_SOURCE_PASSAGE)

        # TEXT_VERIFICATION_FAILED
        human_texts = [
            lo.get("human_text") or ""
            for lo in self._lines.get_many(entry.get("body_line_ids") or [])
        ]
        has_human_text = any(human_texts)
        if not has_human_text and ocr_confidence < OCR_CONF_THRESHOLD:
            meta.add_residual(ResidualType.TEXT_VERIFICATION_FAILED)

        return meta

    # ── Top-level bundle construction ─────────────────────────────────────────

    def build_bundle(self, entry: dict) -> MaqayisSourceBundle:
        """
        Build a complete MaqayisSourceBundle (Layer 1 populated; Layers 2-4 stubbed).

        Layers 2 (LexicalClaimGraph), 3 (SemanticOriginGraph), and 4
        (OntologyCandidateProfile) are set to None here and filled by downstream
        builders (maqayis_claim_extractor, maqayis_semantic_origin_graph_builder,
        maqayis_ontology_candidate_builder).
        """
        entry_id = entry.get("entry_id") or ""
        semantic_origin_type = entry.get("semantic_origin_type") or "NONE"
        heading_text = entry.get("root_heading_text") or ""
        body_line_ids: List[str] = entry.get("body_line_ids") or []
        poetry_ids: set = set(entry.get("poetry_line_ids") or [])

        # Resolve body text via body loader (poetry excluded per constitution)
        body_line_objs = self._lines.get_many(
            [lid for lid in body_line_ids if lid not in poetry_ids]
        )
        body_text = " ".join(
            _best_line_text(lo) for lo in body_line_objs
            if _best_line_text(lo).strip()
        )

        # Build components
        heading_type = _map_heading_type(semantic_origin_type, heading_text)
        claim_kind = _map_claim_kind(semantic_origin_type, heading_text)
        entry_kind = _map_entry_kind(heading_type, claim_kind, body_text)

        source_evidence = self.build_source_evidence(entry, body_text, body_line_objs)
        root_identity = self.build_root_identity_candidate(entry)
        ocr_conf = source_evidence.ocr_confidence

        # Source claim: only for entries that carry a claim
        if entry_kind in (
            EntryKind.ROOT_ENTRY,
            EntryKind.CROSS_REFERENCE,
            EntryKind.NEGATIVE_ENTRY,
            EntryKind.DISPUTED_ENTRY,
        ):
            source_claim: Optional[SourceClaimRecord] = self.build_source_claim_record(
                entry, claim_kind
            )
        else:
            source_claim = None

        extraction_meta = self.build_extraction_metadata(
            entry, root_identity, entry_kind, body_text, ocr_conf
        )

        return MaqayisSourceBundle(
            bundle_id=_new_id("BUNDLE"),
            entry_id=entry_id,
            # Layer 1
            source_evidence=source_evidence,
            root_identity=root_identity,
            source_claim=source_claim,
            entry_kind=entry_kind,
            # Layers 2-4: filled by downstream builders
            origins=[],
            branches=[],
            usage_evidence=[],
            lexical_claim_graph=None,
            semantic_origin_graph=None,
            ontology_candidate_profile=None,
            extraction_meta=extraction_meta,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def iter_bundles(self) -> Iterator[MaqayisSourceBundle]:
        """Yield one MaqayisSourceBundle per entry in entries_jsonl."""
        for entry in self._iter_entries():
            yield self.build_bundle(entry)

    def build_all_bundles(self) -> List[MaqayisSourceBundle]:
        """Return all bundles as a list (loads everything into memory)."""
        return list(self.iter_bundles())


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def iter_source_bundles(
    entries_jsonl: "pathlib.Path | str | None" = None,
    lines_jsonl: "pathlib.Path | str | None" = None,
    *,
    prefer_corrected: bool = True,
) -> Iterator[MaqayisSourceBundle]:
    """
    Convenience iterator over all MaqayisSourceBundle records.

    Auto-discovers data paths relative to the package root when not supplied.
    When prefer_corrected is True (default), uses root_entries_corrected.jsonl
    if it exists alongside root_entries.jsonl.

    ::

        from pipeline.taaqol_integration.maqayis_source_evidence_builder import (
            iter_source_bundles
        )
        for bundle in iter_source_bundles():
            if bundle.is_ontology_buildable():
                ...
    """
    if lines_jsonl is None or entries_jsonl is None:
        # Auto-discover: walk up from this file to find data/ directory
        here = pathlib.Path(__file__).resolve().parent
        for parent in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
            candidate_lines = parent / "data" / "maqaees" / "full" / "lines.jsonl"
            candidate_entries = parent / "data" / "maqaees" / "full" / "root_entries.jsonl"
            if candidate_lines.exists() and candidate_entries.exists():
                if lines_jsonl is None:
                    lines_jsonl = candidate_lines
                if entries_jsonl is None:
                    corrected = candidate_entries.parent / "root_entries_corrected.jsonl"
                    entries_jsonl = (
                        corrected if (prefer_corrected and corrected.exists())
                        else candidate_entries
                    )
                break
        if lines_jsonl is None or entries_jsonl is None:
            raise FileNotFoundError(
                "Could not auto-discover lines.jsonl and root_entries.jsonl. "
                "Pass explicit paths to iter_source_bundles()."
            )

    builder = SourceEvidenceBuilder(
        lines_jsonl=lines_jsonl,
        entries_jsonl=entries_jsonl,
    )
    yield from builder.iter_bundles()


def build_root_knowledge_bundle_map(
    entries_jsonl: "pathlib.Path | str | None" = None,
    lines_jsonl: "pathlib.Path | str | None" = None,
) -> dict:
    """
    Build a mapping from source_root_candidate → list[MaqayisSourceBundle].

    Used by the aggregation layer to collect all entries sharing a root before
    constructing RootKnowledgeBundle. Conflicts between entries for the same root
    are detected here and logged as INTER_ENTRY_CONFLICT residuals.

    Returns:
        {root_letters: [MaqayisSourceBundle, ...], ...}
    """
    from .maqayis_source_schema import RootKnowledgeBundle

    root_map: Dict[str, RootKnowledgeBundle] = {}

    for bundle in iter_source_bundles(entries_jsonl, lines_jsonl):
        root_candidate = bundle.root_identity.source_root_candidate or "UNKNOWN"
        if root_candidate not in root_map:
            root_map[root_candidate] = RootKnowledgeBundle(
                bundle_id=_new_id("RKB"),
                hokom_canonical_root_ref=None,  # Hokom fills later
                primary_entry_id=bundle.entry_id,
                secondary_entry_ids=[],
                source_bundles=[bundle],
                conflict_log=[],
                aggregation_state=AggregationState.SINGLE_SOURCE,
            )
        else:
            root_map[root_candidate].register(bundle)

    return root_map
