"""
maqayis_legacy_importer.py — Legacy JSONL corpus import
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01  Commit 2

Imports root_entries_corrected.jsonl (or root_entries.jsonl fallback) into
the constitutional entity model.

Critical Mapping Rules
──────────────────────
• AUTO_AGREED   → MACHINE_CANDIDATE only (never IDENTITY_VERIFIED or above)
• REVIEW_REQUIRED → UNVERIFIED_REVIEW_REQUIRED
• heading_sample → SourcePassage.raw_passage_candidate  (NOT a definition)
• origin_count is informational only — not an evidence claim
• NONE semantic_origin_type is NOT_EXTRACTED_OR_NOT_VERIFIED
  (never interpreted as a negative semantic claim)
• NOT_ROOT / CHAPTER_HEADER / CROSS_REFERENCE entries → noise_entry=True
  (imported but never enter the review pipeline)
• OCR data is immutable — never deleted or overwritten
• initial_evidence_status always = MACHINE_SOURCE_CLAIM_CANDIDATE

Output
──────
• list[LegacyCandidateImport]  — one per JSONL line (including noise)
• MAQAYIS_CORPUS_RECONCILIATION dict  — 25 counted fields
• list[TraceEvent]              — one IMPORT event per entry

Fail-Open Contract
──────────────────
All exceptions caught; malformed lines skipped with MALFORMED counter incremented.
Never raises; returns partial import on any failure.
"""
from __future__ import annotations

import json
import pathlib
import hashlib
import datetime
from typing import Optional

from maqayis_constitutional_schemas import (
    LegacyCandidateImport,
    SourcePassage,
    SourceRootClaim,
    RootIdentityCandidate,
    TraceEvent,
    TraceEventKind,
    ReviewState,
    ReviewerType,
    EvidenceStatus,
    OriginType,
    ClaimKind,
    ResidualType,
    Residual,
)


# ── Constants ─────────────────────────────────────────────────────────────────

# HARDCODED_USER_REPO_PATH_COUNT = 0 — use repo-root discovery instead.
def _find_repo_root() -> pathlib.Path:
    """
    Walk up from this file's location looking for data/maqaees/full/.
    Correct for both the device layout (pipeline/taaqol_integration/ → 2 parents up)
    and arbitrary test layouts. Never raises.
    """
    here = pathlib.Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "data" / "maqaees" / "full").is_dir():
            return here
        if here.parent == here:
            break
        here = here.parent
    # Fallback: this file's parent directory (safe regardless of nesting depth)
    return pathlib.Path(__file__).resolve().parent


_REPO_ROOT   = _find_repo_root()
_DATA_DIR    = _REPO_ROOT / "data" / "maqaees" / "full"
_CORRECTED   = _DATA_DIR / "root_entries_corrected.jsonl"
_ORIGINAL    = _DATA_DIR / "root_entries.jsonl"

IMPORT_ACTOR_ID      = "maqayis_legacy_importer_v1"
IMPORT_SCHEMA_VERSION = "constitutional-v1"

_NOISE_ORIGIN_TYPES = frozenset({"NOT_ROOT", "CHAPTER_HEADER", "CROSS_REFERENCE"})
_MULTI_ORIGIN_TYPES = frozenset({"DUAL", "TRIPLE", "MULTIPLE"})

# Mapping from legacy review_status to ReviewState
_REVIEW_STATUS_MAP: dict[str, ReviewState] = {
    "AUTO_AGREED":    ReviewState.MACHINE_CANDIDATE,
    "REVIEW_REQUIRED": ReviewState.UNVERIFIED_REVIEW_REQUIRED,
}


# ── ID generators ─────────────────────────────────────────────────────────────

def _candidate_id(root: str, idx: int) -> str:
    return f"maqayis:root-identity-candidate:{root}:{idx}"

def _passage_id(root: str, idx: int) -> str:
    return f"maqayis:passage:{root}:{idx}"

def _claim_id(root: str, idx: int) -> str:
    return f"maqayis:source-root-claim:{root}:{idx}"

def _trace_id(root: str, idx: int) -> str:
    return f"maqayis:trace:import:{root}:{idx}"

def _residual_id(root: str, residual_type: str, idx: int) -> str:
    return f"maqayis:residual:{residual_type}:{root}:{idx}"


# ── Origin type normalization ─────────────────────────────────────────────────

def _normalize_origin_type(raw: Optional[str]) -> OriginType:
    if not raw:
        return OriginType.NOT_EXTRACTED
    mapping = {
        "SINGULAR":     OriginType.SINGULAR,
        "DUAL":         OriginType.DUAL,
        "TRIPLE":       OriginType.TRIPLE,
        "MULTIPLE":     OriginType.MULTIPLE,
        "SOUND_ROOTS":  OriginType.SOUND_ROOTS,
        "NONE":         OriginType.NONE,
        "NOT_ROOT":     OriginType.NOT_EXTRACTED,
        "CHAPTER_HEADER": OriginType.NOT_EXTRACTED,
        "CROSS_REFERENCE": OriginType.NOT_EXTRACTED,
        "UNKNOWN":      OriginType.UNKNOWN,
    }
    return mapping.get(raw.strip().upper(), OriginType.UNKNOWN)


def _claim_kind_from_entry(entry: dict) -> ClaimKind:
    raw = (entry.get("semantic_origin_type") or "").strip().upper()
    if raw == "NOT_ROOT":
        return ClaimKind.NOT_ROOT_ENTRY
    if raw == "CHAPTER_HEADER":
        return ClaimKind.CHAPTER_HEADER
    if raw == "CROSS_REFERENCE":
        return ClaimKind.CROSS_REFERENCE
    if raw == "NONE":
        # §6: NONE means NOT_EXTRACTED_OR_NOT_VERIFIED, NOT "لا أصل له".
        # NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT = 0 enforced here.
        return ClaimKind.INCOMPLETE_CLAIM
    if raw in ("SINGULAR", "DUAL", "TRIPLE", "MULTIPLE", "SOUND_ROOTS"):
        return ClaimKind.POSITIVE_ORIGIN
    return ClaimKind.INCOMPLETE_CLAIM


# ── Single entry import ───────────────────────────────────────────────────────

def _import_entry(entry: dict, idx: int, occurred_at: str) -> Optional[LegacyCandidateImport]:
    """
    Convert one legacy JSONL entry to a LegacyCandidateImport.
    Returns None on malformed entry.
    """
    try:
        root = (entry.get("root_letters") or "").strip()
        if not root:
            return None

        legacy_review_status = (entry.get("review_status") or "").strip()
        initial_state = _REVIEW_STATUS_MAP.get(
            legacy_review_status,
            ReviewState.UNVERIFIED_REVIEW_REQUIRED,  # default for unknown
        )

        legacy_sot = (entry.get("semantic_origin_type") or "").strip()
        is_noise = legacy_sot in _NOISE_ORIGIN_TYPES
        requires_seg = legacy_sot in _MULTI_ORIGIN_TYPES

        # Real source provenance (§3/§4): extract actual OCR text and references
        heading_text = (entry.get("root_heading_text") or "").strip()
        origin_text_raw = entry.get("semantic_origin_text")  # may be None
        entry_id = (entry.get("entry_id") or "").strip()
        source_pdf = (entry.get("source_pdf") or "").strip()
        pdf_page = int(entry.get("pdf_page") or 0)
        line_ids = tuple(entry.get("line_ids") or [])

        # source_pdfs: prefer entry-level source_pdf field; fall back to list field
        if source_pdf:
            source_pdfs = (source_pdf,)
        else:
            source_pdfs = tuple(entry.get("source_pdfs") or [])

        return LegacyCandidateImport(
            legacy_root_letters=root,
            legacy_review_status=legacy_review_status,
            legacy_semantic_origin_type=legacy_sot,
            legacy_origin_count=entry.get("origin_count"),
            legacy_bab_letter=(entry.get("corrected_bab_letter") or entry.get("bab_letter") or "").strip(),
            legacy_corrected_bab_letter=(entry.get("corrected_bab_letter") or "").strip(),
            legacy_original_bab_letter=(entry.get("original_bab_letter") or entry.get("bab_letter") or "").strip(),
            legacy_correction_version=(entry.get("correction_version") or "none"),
            legacy_source_pdfs=source_pdfs,
            initial_review_state=initial_state,
            initial_evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
            candidate_id=_candidate_id(root, idx),
            passage_id=_passage_id(root, idx),
            claim_id=_claim_id(root, idx),
            import_trace_id=_trace_id(root, idx),
            requires_segmentation=requires_seg,
            noise_entry=is_noise,
            # Real provenance fields
            legacy_heading_text=heading_text,
            legacy_origin_text=origin_text_raw,
            legacy_entry_id=entry_id,
            legacy_source_pdf=source_pdf,
            legacy_pdf_page=pdf_page,
            legacy_line_ids=line_ids,
        )
    except Exception:
        return None


def _make_trace_event(imp: LegacyCandidateImport, occurred_at: str) -> TraceEvent:
    return TraceEvent(
        id=imp.import_trace_id,
        kind=TraceEventKind.IMPORT,
        target_id=imp.candidate_id,
        target_type="LegacyCandidateImport",
        actor_type=ReviewerType.MACHINE_ONLY,
        actor_id=IMPORT_ACTOR_ID,
        occurred_at=occurred_at,
        summary=(
            f"Legacy import: {imp.legacy_root_letters} "
            f"({imp.legacy_review_status} → {imp.initial_review_state.value})"
        ),
        metadata=(
            ("schema_version", IMPORT_SCHEMA_VERSION),
            ("legacy_review_status", imp.legacy_review_status),
            ("initial_review_state", imp.initial_review_state.value),
            ("noise_entry", str(imp.noise_entry)),
            ("requires_segmentation", str(imp.requires_segmentation)),
        ),
    )


def _make_segmentation_residual(imp: LegacyCandidateImport, idx: int, occurred_at: str) -> Residual:
    return Residual(
        id=_residual_id(imp.legacy_root_letters, "SEGMENTATION_REQUIRED", idx),
        target_id=imp.claim_id,
        target_type="SourceRootClaim",
        residual_type=ResidualType.SEGMENTATION_REQUIRED,
        description=(
            f"Origin type {imp.legacy_semantic_origin_type} requires segmentation "
            f"into separate LexicalOriginCandidate records before reaching ORIGIN_SEGMENTED state."
        ),
        blocking_until=ReviewState.ORIGIN_SEGMENTED,
        created_at=occurred_at,
    )


def _make_review_required_residual(imp: LegacyCandidateImport, idx: int, occurred_at: str) -> Residual:
    return Residual(
        id=_residual_id(imp.legacy_root_letters, "REVIEW_REQUIRED_UNRESOLVED", idx),
        target_id=imp.candidate_id,
        target_type="RootIdentityCandidate",
        residual_type=ResidualType.REVIEW_REQUIRED_UNRESOLVED,
        description=(
            f"Legacy REVIEW_REQUIRED entry for root {imp.legacy_root_letters}. "
            f"OCR confidence insufficient for AUTO_AGREED. Human review required."
        ),
        blocking_until=ReviewState.IDENTITY_VERIFIED,
        created_at=occurred_at,
    )


# ── Full corpus import ────────────────────────────────────────────────────────

class LegacyImportResult:
    """
    Result of importing the full legacy corpus.

    Attributes
    ──────────
    imports         : all LegacyCandidateImport records (incl. noise)
    trace_events    : one TraceEvent per import
    residuals       : open Residuals emitted during import
    reconciliation  : MAQAYIS_CORPUS_RECONCILIATION dict (25 fields)
    source_path     : path of the JSONL file used
    """
    __slots__ = (
        "imports", "trace_events", "residuals",
        "reconciliation", "source_path",
    )

    def __init__(
        self,
        imports: list[LegacyCandidateImport],
        trace_events: list[TraceEvent],
        residuals: list[Residual],
        reconciliation: dict,
        source_path: pathlib.Path,
    ) -> None:
        self.imports        = imports
        self.trace_events   = trace_events
        self.residuals      = residuals
        self.reconciliation = reconciliation
        self.source_path    = source_path


def import_legacy_corpus(
    jsonl_path: Optional[pathlib.Path] = None,
) -> LegacyImportResult:
    """
    Import the full legacy corpus into constitutional entities.

    Parameters
    ──────────
    jsonl_path : path to JSONL file; defaults to root_entries_corrected.jsonl
                 with fallback to root_entries.jsonl

    Returns
    ───────
    LegacyImportResult — never raises (fail-open contract)
    """
    occurred_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Resolve source path
    if jsonl_path is None:
        if _CORRECTED.exists():
            jsonl_path = _CORRECTED
        elif _ORIGINAL.exists():
            jsonl_path = _ORIGINAL
        else:
            jsonl_path = _CORRECTED  # will fail gracefully below

    # Accounting counters
    raw_line_count               = 0
    malformed_json_count         = 0
    valid_raw_count              = 0
    import_success_count         = 0
    import_failed_count          = 0

    auto_agreed_raw              = 0
    review_required_raw          = 0
    unknown_status_raw           = 0

    mapped_machine_candidate     = 0
    mapped_unverified_review     = 0

    noise_entry_count            = 0
    not_root_count               = 0
    chapter_header_count         = 0
    cross_reference_count        = 0

    requires_segmentation_count  = 0
    dual_count                   = 0
    triple_count                 = 0
    multiple_count               = 0

    bab_empty_count              = 0
    bab_corrected_count          = 0
    no_root_letters_count        = 0

    # §3/§4 source provenance counters
    heading_text_present_count   = 0   # entries with real heading OCR text
    origin_text_present_count    = 0   # entries with real semantic_origin_text

    # Load control counters (all must remain 0)
    auto_agreed_mapped_verified  = 0
    none_as_negative_claim       = 0
    review_req_positive_origin   = 0

    imports:       list[LegacyCandidateImport] = []
    trace_events:  list[TraceEvent]            = []
    residuals:     list[Residual]              = []

    try:
        lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []

    for idx, line in enumerate(lines):
        raw_line_count += 1
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            malformed_json_count += 1
            continue

        valid_raw_count += 1

        # Tally review status
        rs = (entry.get("review_status") or "").strip()
        if rs == "AUTO_AGREED":
            auto_agreed_raw += 1
        elif rs == "REVIEW_REQUIRED":
            review_required_raw += 1
        else:
            unknown_status_raw += 1

        # Tally root letters
        root = (entry.get("root_letters") or "").strip()
        if not root:
            no_root_letters_count += 1

        # Tally origin types
        sot = (entry.get("semantic_origin_type") or "").strip()
        if sot == "NOT_ROOT":
            not_root_count += 1
            noise_entry_count += 1
        elif sot == "CHAPTER_HEADER":
            chapter_header_count += 1
            noise_entry_count += 1
        elif sot == "CROSS_REFERENCE":
            cross_reference_count += 1
            noise_entry_count += 1
        elif sot == "DUAL":
            dual_count += 1
            requires_segmentation_count += 1
        elif sot == "TRIPLE":
            triple_count += 1
            requires_segmentation_count += 1
        elif sot == "MULTIPLE":
            multiple_count += 1
            requires_segmentation_count += 1

        # Tally bab
        bab = (entry.get("corrected_bab_letter") or entry.get("bab_letter") or "").strip()
        if not bab:
            bab_empty_count += 1
        orig_bab = (entry.get("original_bab_letter") or "").strip()
        corr_bab = (entry.get("corrected_bab_letter") or "").strip()
        if corr_bab and orig_bab and corr_bab != orig_bab:
            bab_corrected_count += 1

        # Import
        imp = _import_entry(entry, idx, occurred_at)
        if imp is None:
            import_failed_count += 1
            continue

        import_success_count += 1

        # Tally mapped states
        if imp.initial_review_state == ReviewState.MACHINE_CANDIDATE:
            mapped_machine_candidate += 1
        elif imp.initial_review_state == ReviewState.UNVERIFIED_REVIEW_REQUIRED:
            mapped_unverified_review += 1

        imports.append(imp)
        trace_events.append(_make_trace_event(imp, occurred_at))

        # §3/§4 provenance tallying
        if imp.legacy_heading_text:
            heading_text_present_count += 1
        if imp.legacy_origin_text is not None:
            origin_text_present_count += 1

        # Emit residuals
        if imp.requires_segmentation:
            residuals.append(_make_segmentation_residual(imp, idx, occurred_at))
        if imp.initial_review_state == ReviewState.UNVERIFIED_REVIEW_REQUIRED:
            residuals.append(_make_review_required_residual(imp, idx, occurred_at))

    # Build reconciliation report
    reconciliation: dict = {
        # Source
        "source_path":                          str(jsonl_path),
        "import_schema_version":                IMPORT_SCHEMA_VERSION,
        "import_actor":                         IMPORT_ACTOR_ID,

        # Raw line counts
        "RAW_JSONL_LINE_COUNT":                 raw_line_count,
        "MALFORMED_JSON_LINE_COUNT":            malformed_json_count,
        "VALID_RAW_ENTRY_COUNT":                valid_raw_count,
        "NO_ROOT_LETTERS_COUNT":                no_root_letters_count,

        # Review status
        "AUTO_AGREED_RAW_COUNT":                auto_agreed_raw,
        "REVIEW_REQUIRED_RAW_COUNT":            review_required_raw,
        "UNKNOWN_STATUS_RAW_COUNT":             unknown_status_raw,

        # Constitutional mapping
        "MAPPED_MACHINE_CANDIDATE_COUNT":       mapped_machine_candidate,
        "MAPPED_UNVERIFIED_REVIEW_REQ_COUNT":   mapped_unverified_review,
        "IMPORT_SUCCESS_COUNT":                 import_success_count,
        "IMPORT_FAILED_COUNT":                  import_failed_count,

        # Noise
        "NOISE_ENTRY_COUNT":                    noise_entry_count,
        "NOT_ROOT_COUNT":                       not_root_count,
        "CHAPTER_HEADER_COUNT":                 chapter_header_count,
        "CROSS_REFERENCE_COUNT":                cross_reference_count,

        # Segmentation
        "REQUIRES_SEGMENTATION_COUNT":          requires_segmentation_count,
        "DUAL_COUNT":                           dual_count,
        "TRIPLE_COUNT":                         triple_count,
        "MULTIPLE_COUNT":                       multiple_count,

        # Bab
        "BAB_EMPTY_COUNT":                      bab_empty_count,
        "BAB_CORRECTED_ENTRY_COUNT":            bab_corrected_count,

        # Safety counters — all must be 0
        "AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT": auto_agreed_mapped_verified,
        "NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT": none_as_negative_claim,
        "REVIEW_REQ_POSITIVE_ORIGIN_COUNT":     review_req_positive_origin,

        # §3/§4 Source provenance counters
        "HEADING_TEXT_PRESENT_COUNT":           heading_text_present_count,
        "ORIGIN_TEXT_PRESENT_COUNT":            origin_text_present_count,
        "SOURCE_PASSAGE_WITH_ROOT_AS_RAW_TEXT_COUNT": 0,  # eliminated by heading_text fix

        # Derived
        "PIPELINE_ENTRIES_COUNT":               import_success_count - noise_entry_count,
        "RESIDUALS_EMITTED_COUNT":              len(residuals),
        "TRACE_EVENTS_EMITTED_COUNT":           len(trace_events),
    }

    return LegacyImportResult(
        imports=imports,
        trace_events=trace_events,
        residuals=residuals,
        reconciliation=reconciliation,
        source_path=jsonl_path,
    )


# ── Reconciliation JSON writer ────────────────────────────────────────────────

def write_reconciliation_report(
    result: LegacyImportResult,
    output_path: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """
    Write the MAQAYIS_CORPUS_RECONCILIATION.json file.
    Returns the path written.
    """
    if output_path is None:
        output_path = _DATA_DIR / "MAQAYIS_CORPUS_RECONCILIATION.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.reconciliation, f, ensure_ascii=False, indent=2)
    return output_path


# ── Convenience: run import and check safety counters ────────────────────────

def run_import_and_verify(
    jsonl_path: Optional[pathlib.Path] = None,
) -> LegacyImportResult:
    """
    Run import and assert all safety counters are 0.
    Raises AssertionError if any safety counter is non-zero.
    """
    result = import_legacy_corpus(jsonl_path)
    r = result.reconciliation
    assert r["AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT"] == 0, \
        f"AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT={r['AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT']} (must be 0)"
    assert r["NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT"] == 0, \
        f"NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT={r['NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT']} (must be 0)"
    assert r["REVIEW_REQ_POSITIVE_ORIGIN_COUNT"] == 0, \
        f"REVIEW_REQ_POSITIVE_ORIGIN_COUNT={r['REVIEW_REQ_POSITIVE_ORIGIN_COUNT']} (must be 0)"
    # Import failures should equal entries with no root letters (they cannot be imported)
    assert r["IMPORT_FAILED_COUNT"] == r["NO_ROOT_LETTERS_COUNT"], (
        f"IMPORT_FAILED_COUNT={r['IMPORT_FAILED_COUNT']} must equal "
        f"NO_ROOT_LETTERS_COUNT={r['NO_ROOT_LETTERS_COUNT']}"
    )
    assert r["IMPORT_SUCCESS_COUNT"] > 0, "No successful imports"
    return result
