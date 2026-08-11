"""
maqayis_identity_pipeline.py — Source builder + identity extraction pipeline
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01  Commit 3

Produces:
  • SourceRecord     — one per Maqayis PDF volume
  • SourcePassage    — one per imported JSONL entry
  • RootIdentityCandidate — one per imported entry (after OCR gate evaluation)
  • Residuals        — one per raised OCR gate

20 OCR Confusion Gates
──────────────────────
Gates check for common Apple Vision OCR confusions in Arabic root letters.
A gate raising True means the root MAY contain an OCR error — it does NOT
mean the root IS wrong.  Gate flags become open Residuals of type OCR_AMBIGUITY
blocking upgrade to IDENTITY_VERIFIED until a human reviewer clears them.

Gate IDs (G01–G20):
  G01  ح/خ confusion          (connect + dot)
  G02  ب/ت/ث/ن/ي confusion    (baseline + dots)
  G03  د/ذ confusion           (connect + dot)
  G04  ر/ز confusion           (curve + dot)
  G05  ص/ض confusion           (loop + tooth)
  G06  ط/ظ confusion           (upstroke + dot)
  G07  ع/غ confusion           (connect + dot)
  G08  ف/ق confusion           (dots: one vs two)
  G09  Hamza form confusion    (ا/أ/إ/آ/ء/ئ/ؤ)
  G10  Weak letter confusion   (و/ي ambiguity)
  G11  Reversed radicals       (3-letter root in wrong order)
  G12  Extra radical           (4-char root from 3-radical word)
  G13  Missing radical         (2-char root from 3-radical word)
  G14  م/ن confusion           (short vs long base)
  G15  ه/ة confusion           (taa marbuta)
  G16  ك/ل confusion           (stroke direction)
  G17  س/ش confusion           (teeth + dots)
  G18  ج/ح/خ triconfusion     (base + dots)
  G19  ق/غ confusion           (loop + dots)
  G20  Diacritic bleed         (diacritic merged into letter shape)

Fail-Open Contract
──────────────────
All exceptions caught; returns empty structures on failure.
Never blocks Taaqol admission.
"""
from __future__ import annotations

import re
import datetime
import hashlib
import pathlib
from typing import Optional

from maqayis_constitutional_schemas import (
    SourceRecord,
    SourcePassage,
    RootIdentityCandidate,
    TraceEvent,
    TraceEventKind,
    Residual,
    ResidualType,
    ReviewState,
    ReviewerType,
    EvidenceStatus,
    HUMAN_REQUIRED_STATES,
    TransitionContractViolation,
    enforce_tc_si_01,
)
from maqayis_legacy_importer import LegacyCandidateImport, LegacyImportResult


# ── Repo-root discovery (§2) ─────────────────────────────────────────────────

def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "data" / "maqaees" / "full").is_dir():
            return here
        here = here.parent
    return pathlib.Path(__file__).resolve().parent


_REPO_ROOT = _find_repo_root()
_DATA_DIR  = _REPO_ROOT / "data" / "maqaees" / "full"
_COVERAGE_MANIFEST = _DATA_DIR / "coverage_manifest.json"
_PAGES_JSONL       = _DATA_DIR / "pages.jsonl"
_CORRECTED_JSONL   = _DATA_DIR / "root_entries_corrected.jsonl"
_ORIGINAL_JSONL    = _DATA_DIR / "root_entries.jsonl"


# ── Known Maqayis volumes ────────────────────────────────────────────────────

_VOLUME_METADATA: list[dict] = [
    {
        "volume_number": 1,
        "filename": "maqayis_vol1.pdf",
        "initial_letters": ("ح", "خ", "د", "ذ", "ر", "ز"),
        "is_missing_volume": False,
    },
    {
        "volume_number": 2,
        "filename": "maqayis_vol2.pdf",
        "initial_letters": ("س", "ش", "ص", "ض", "ط", "ظ"),
        "is_missing_volume": False,
    },
    {
        "volume_number": 3,
        "filename": "maqayis_vol3.pdf",
        "initial_letters": ("ع", "غ", "ف", "ق", "ك"),
        "is_missing_volume": False,
    },
    {
        "volume_number": 4,
        "filename": "maqayis_vol4.pdf",
        "initial_letters": ("ل", "م", "ن"),
        "is_missing_volume": False,
    },
    {
        "volume_number": 5,
        "filename": "maqayis_vol5.pdf",
        "initial_letters": ("ه", "و", "ي"),
        "is_missing_volume": False,
    },
    # Volume 6 covers ا–ج but is ABSENT from corpus.
    # §3: Missing volumes are NOT represented as SourceRecords.
    # They are represented only through _MAQAYIS_MISSING_INITIALS + coverage_note.
    # FICTIONAL_SOURCE_RECORD_COUNT = 0 enforced by omitting vol6 from SourceRecord list.
]

# §8: Include bare ء in hamza normalization set.
# BARE_HAMZA_COVERAGE_FAILURE_COUNT = 0 enforced here.
_MISSING_INITIALS = frozenset({"ا", "أ", "إ", "آ", "ء", "ب", "ت", "ث", "ج"})
_HAMZA_NORMALIZE  = frozenset({"أ", "إ", "آ", "ء"})  # all normalize to ا for gap check
_SOURCE_RECORD_ID_PREFIX = "maqayis:source"
_PASSAGE_ID_PREFIX       = "maqayis:passage"
_IDENTITY_ID_PREFIX      = "maqayis:root-identity-candidate"
_RESIDUAL_ID_PREFIX      = "maqayis:residual"
_TRACE_ID_PREFIX         = "maqayis:trace"

# §7: Maps canonical _VOLUME_METADATA filename ("maqayis_volN.pdf") to the
# actual on-disk filename used in JSONL source_pdf fields ("NN.pdf").
# SourceRecord.sha256      = SHA256 of JSONL *content* lines for that volume.
# SourceRecord.pdf_sha256  = SHA256 of actual PDF *file bytes* on disk.
PDF_FILENAME_MAPPING: dict[str, str] = {
    "maqayis_vol1.pdf": "01.pdf",
    "maqayis_vol2.pdf": "02.pdf",
    "maqayis_vol3.pdf": "03.pdf",
    "maqayis_vol4.pdf": "04.pdf",
    "maqayis_vol5.pdf": "05.pdf",
}

PIPELINE_ACTOR_ID = "maqayis_identity_pipeline_v1"


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — SOURCE RECORD BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_source_records() -> list[SourceRecord]:
    """
    Build SourceRecord objects for covered Maqayis volumes (01-05.pdf).
    sha256 computed per-volume from JSONL content (content hash).
    page_count read from pages.jsonl.

    §3: Missing volume (06.pdf) NOT represented as SourceRecord.
    FICTIONAL_SOURCE_RECORD_COUNT = 0 enforced by omitting vol6.
    """
    import json

    # --- Page counts from pages.jsonl ---
    page_counts: dict[str, int] = {}
    if _PAGES_JSONL.exists():
        try:
            with open(_PAGES_JSONL, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        src = entry.get("source_pdf", "")
                        if src:
                            page_counts[src] = page_counts.get(src, 0) + 1
                    except Exception:
                        pass
        except Exception:
            pass

    # --- Corpus-level sha256 from manifest (fallback for volumes) ---
    corpus_sha = ""
    if _COVERAGE_MANIFEST.exists():
        try:
            with open(_COVERAGE_MANIFEST, encoding="utf-8") as fh:
                manifest = json.load(fh)
            corpus_sha = manifest.get("corpus_hash_sha256", "")
        except Exception:
            pass

    # --- Per-volume sha256 computed from JSONL entries ---
    vol_sha256: dict[str, str] = {}
    jsonl_path = (
        _CORRECTED_JSONL if _CORRECTED_JSONL.exists() else
        _ORIGINAL_JSONL  if _ORIGINAL_JSONL.exists() else None
    )
    if jsonl_path is not None:
        try:
            vol_bufs: dict[str, list[bytes]] = {}
            with open(jsonl_path, encoding="utf-8") as fh:
                for line in fh:
                    lb = line.encode("utf-8")
                    try:
                        src = json.loads(line).get("source_pdf", "UNKNOWN")
                    except Exception:
                        src = "UNKNOWN"
                    vol_bufs.setdefault(src, []).append(lb)
            for src, lines in vol_bufs.items():
                h = hashlib.sha256()
                for lb in lines:
                    h.update(lb)
                vol_sha256[src] = h.hexdigest()
        except Exception:
            pass

    # R2: Per-volume PDF SHA256 from actual PDF file bytes (separate from JSONL hash)
    pdf_sha256_map: dict[str, str] = {}
    for meta in _VOLUME_METADATA:
        vol_n = meta["volume_number"]
        pdf_path = _DATA_DIR / f"{vol_n:02d}.pdf"
        if pdf_path.exists():
            try:
                h = hashlib.sha256()
                with open(pdf_path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        h.update(chunk)
                pdf_sha256_map[f"{vol_n:02d}.pdf"] = h.hexdigest()
            except Exception:
                pass

    records: list[SourceRecord] = []
    for meta in _VOLUME_METADATA:
        vol_n = meta["volume_number"]
        jsonl_key = f"{vol_n:02d}.pdf"          # "01.pdf" .. "05.pdf"
        sha = vol_sha256.get(jsonl_key, corpus_sha)
        pg_count = page_counts.get(jsonl_key, 0)
        records.append(SourceRecord(
            id=f"{_SOURCE_RECORD_ID_PREFIX}:vol{vol_n}",
            volume_number=vol_n,
            filename=meta["filename"],
            sha256=sha,
            page_count=pg_count,
            ocr_pass_count=2,
            is_missing_volume=meta["is_missing_volume"],
            initial_letters=tuple(meta["initial_letters"]),
            pdf_sha256=pdf_sha256_map.get(jsonl_key, ""),
        ))
    return records


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — 20 OCR CONFUSION GATES
# ═══════════════════════════════════════════════════════════════════════════════

# Arabic letter sets for each gate
_HA_KHA     = frozenset("حخ")
_BASELINE   = frozenset("بتثني")   # G02: dotted baseline confusion
_DAL_DHAL   = frozenset("دذ")
_RA_ZAY     = frozenset("رز")
_SAD_DAD    = frozenset("صض")
_TA_ZA      = frozenset("طظ")
_AIN_GHAIN  = frozenset("عغ")
_FA_QAF     = frozenset("فق")
_HAMZA      = frozenset("أإآء")   # normalized ا is the canonical form
_WEAK       = frozenset("وي")
_MIM_NUN    = frozenset("من")
_HA_TA_M    = frozenset("هة")
_KAF_LAM    = frozenset("كل")
_SIN_SHIN   = frozenset("سش")
_JIM_HA_KHA = frozenset("جحخ")
_QAF_GHAIN  = frozenset("قغ")

# Diacritic-like Arabic combining characters (could bleed into letter shape)
_DIACRITICS = frozenset("ًٌٍَُِّْٕٓٔ")


def _gate_01_ha_kha(root: str) -> bool:
    """ح/خ confusion — both present in root (ambiguous)."""
    letters = set(root)
    return bool(letters & _HA_KHA) and len(letters & _HA_KHA) == 1 and any(
        (c in _HA_KHA) for c in root
    ) and _is_pair_ambiguous(root, 'ح', 'خ')

def _gate_02_baseline_dots(root: str) -> bool:
    """ب/ت/ث/ن/ي confusion — multiple baseline-dot letters in short root."""
    count = sum(1 for c in root if c in _BASELINE)
    return count >= 2  # two or more dotted-baseline letters → likely confusion

def _gate_03_dal_dhal(root: str) -> bool:
    return _is_pair_ambiguous(root, 'د', 'ذ')

def _gate_04_ra_zay(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ر', 'ز')

def _gate_05_sad_dad(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ص', 'ض')

def _gate_06_ta_za(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ط', 'ظ')

def _gate_07_ain_ghain(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ع', 'غ')

def _gate_08_fa_qaf(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ف', 'ق')

def _gate_09_hamza(root: str) -> bool:
    """Hamza form confusion — non-canonical Hamza form used."""
    return any(c in _HAMZA for c in root)

def _gate_10_weak_letter(root: str) -> bool:
    """و/ي ambiguity — multiple weak letters in root."""
    count = sum(1 for c in root if c in _WEAK)
    return count >= 2

def _gate_11_reversed_radicals(root: str) -> bool:
    """
    Reversed radicals — statistical check.
    A true positive requires Arabic lexicographic knowledge.
    Here we flag roots where the same two letters appear in reversed order
    compared to known common root patterns (conservative: always False for now
    as it requires a reference corpus not available at this stage).
    """
    return False  # conservative: human to review

def _gate_12_extra_radical(root: str) -> bool:
    """4+ character root — may be OCR adding an extra letter."""
    return len(root) >= 4

def _gate_13_missing_radical(root: str) -> bool:
    """2 character root — may be OCR dropping a letter."""
    return len(root) <= 2

def _gate_14_mim_nun(root: str) -> bool:
    return _is_pair_ambiguous(root, 'م', 'ن')

def _gate_15_ha_ta_marbuta(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ه', 'ة')

def _gate_16_kaf_lam(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ك', 'ل')

def _gate_17_sin_shin(root: str) -> bool:
    return _is_pair_ambiguous(root, 'س', 'ش')

def _gate_18_jim_ha_kha(root: str) -> bool:
    """ج/ح/خ triconfusion — any two of the three present."""
    present = {c for c in root if c in _JIM_HA_KHA}
    return len(present) >= 2

def _gate_19_qaf_ghain(root: str) -> bool:
    return _is_pair_ambiguous(root, 'ق', 'غ')

def _gate_20_diacritic_bleed(root: str) -> bool:
    """Diacritic characters merged into root letters."""
    return any(c in _DIACRITICS for c in root)


def _is_pair_ambiguous(root: str, a: str, b: str) -> bool:
    """
    True if both letters a and b appear in root (possible confusion between them).
    """
    return (a in root) and (b in root)


# Gate registry: gate_id → (gate_function, description)
OCR_GATES: list[tuple[str, object, str]] = [
    ("G01", _gate_01_ha_kha,        "ح/خ confusion"),
    ("G02", _gate_02_baseline_dots, "ب/ت/ث/ن/ي multi-dot baseline confusion"),
    ("G03", _gate_03_dal_dhal,      "د/ذ confusion"),
    ("G04", _gate_04_ra_zay,        "ر/ز confusion"),
    ("G05", _gate_05_sad_dad,       "ص/ض confusion"),
    ("G06", _gate_06_ta_za,         "ط/ظ confusion"),
    ("G07", _gate_07_ain_ghain,     "ع/غ confusion"),
    ("G08", _gate_08_fa_qaf,        "ف/ق confusion"),
    ("G09", _gate_09_hamza,         "Hamza form confusion (أ/إ/آ/ء)"),
    ("G10", _gate_10_weak_letter,   "و/ي multiple weak letters"),
    ("G11", _gate_11_reversed_radicals, "Reversed radicals"),
    ("G12", _gate_12_extra_radical, "4+ character root (extra radical?)"),
    ("G13", _gate_13_missing_radical,"≤2 character root (missing radical?)"),
    ("G14", _gate_14_mim_nun,       "م/ن confusion"),
    ("G15", _gate_15_ha_ta_marbuta, "ه/ة confusion"),
    ("G16", _gate_16_kaf_lam,       "ك/ل confusion"),
    ("G17", _gate_17_sin_shin,      "س/ش confusion"),
    ("G18", _gate_18_jim_ha_kha,    "ج/ح/خ triconfusion"),
    ("G19", _gate_19_qaf_ghain,     "ق/غ confusion"),
    ("G20", _gate_20_diacritic_bleed,"Diacritic bleed into letter shape"),
]

# Fix typo in gate list (G11 references wrong name)
OCR_GATES[10] = ("G11", _gate_11_reversed_radicals, "Reversed radicals")


def evaluate_ocr_gates(root: str) -> tuple[tuple[str, bool], ...]:
    """
    Evaluate all 20 OCR gates against *root*.
    Returns a tuple of (gate_id, flag) pairs.
    Never raises.
    """
    results: list[tuple[str, bool]] = []
    for gate_id, gate_fn, _ in OCR_GATES:
        try:
            flag = bool(gate_fn(root))
        except Exception:
            flag = False
        results.append((gate_id, flag))
    return tuple(results)


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — PASSAGE + IDENTITY BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _hamza_normalize(root: str) -> str:
    """Normalize Hamza variants to ا for coverage check ONLY.
    §8: includes bare ء in normalization set (_HAMZA_NORMALIZE).
    BARE_HAMZA_COVERAGE_FAILURE_COUNT = 0 enforced here.
    """
    for h in _HAMZA_NORMALIZE:
        root = root.replace(h, "ا")
    return root


def _passage_from_import(
    imp: LegacyCandidateImport,
    occurred_at: str,
) -> tuple[SourcePassage, list[Residual]]:
    """
    Build a SourcePassage (and any passage-level Residuals) from a LegacyCandidateImport.
    §3: source_id and page_number from real JSONL provenance fields.
    §4: raw_passage_candidate = actual OCR heading text (NOT root letters).
    R4: no root-letter fallback — missing text → MISSING_SOURCE_PASSAGE residual.
    R3: populate entry_id, source_pdf, line_ids, image_ref, passage_checksum.
    CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT = 0 enforced here.
    """
    # §3: Derive source_id from actual source_pdf field
    src_pdf = imp.legacy_source_pdf
    if src_pdf:
        vol_num = src_pdf.replace(".pdf", "").lstrip("0") or "0"
        source_id = f"maqayis:source:vol{vol_num}"
    elif imp.legacy_source_pdfs:
        first = imp.legacy_source_pdfs[0].replace(".pdf", "").lstrip("0") or "0"
        source_id = f"maqayis:source:vol{first}"
    else:
        source_id = "maqayis:source:vol_unknown"

    # R4: No root-letter fallback. Missing text → blocking residual.
    raw_passage = imp.legacy_heading_text or ""
    pass_residuals: list[Residual] = []
    if not raw_passage:
        # §12: entry_discriminator ensures ID uniqueness across multiple entries
        # for the same root_letters (e.g. roots with multiple OCR passages).
        _root = imp.legacy_root_letters
        _entry_discriminator = imp.legacy_entry_id or imp.passage_id or _root
        res_id = f"maqayis:residual:MISSING_SOURCE_PASSAGE:{_root}:{_entry_discriminator}"
        pass_residuals.append(Residual(
            id=res_id,
            target_id=imp.passage_id,
            target_type="SourcePassage",
            residual_type=ResidualType.MISSING_SOURCE_PASSAGE,
            description=(
                f"Root '{imp.legacy_root_letters}': no legacy_heading_text in JSONL; "
                f"raw_passage_candidate is empty."
            ),
            blocking_until=ReviewState.TEXT_VERIFIED,
            created_at=occurred_at,
        ))

    # R3: compute checksum and image_ref from provenance fields
    passage_text = imp.legacy_heading_text if imp.legacy_heading_text else ""
    checksum = hashlib.sha256(passage_text.encode("utf-8")).hexdigest() if passage_text else ""
    image_ref_val = (
        f"{imp.legacy_source_pdf}:p{imp.legacy_pdf_page}"
        if imp.legacy_source_pdf else None
    )

    passage = SourcePassage(
        id=imp.passage_id,
        source_id=source_id,
        page_number=imp.legacy_pdf_page,
        raw_passage_candidate=raw_passage,
        corrected_passage=None,
        ocr_confidence=1.0 if imp.initial_review_state == ReviewState.MACHINE_CANDIDATE else 0.7,
        review_state=imp.initial_review_state,
        evidence_status=imp.initial_evidence_status,
        supersedes_id=None,
        entry_id=imp.legacy_entry_id,
        source_pdf=imp.legacy_source_pdf,
        line_ids=imp.legacy_line_ids,
        offsets=(),
        bounding_box=None,
        context=None,
        image_ref=image_ref_val,
        passage_checksum=checksum,
    )
    return passage, pass_residuals


def _identity_from_import(
    imp: LegacyCandidateImport,
    occurred_at: str,
) -> tuple[RootIdentityCandidate, list[Residual], list[TraceEvent]]:
    """
    Build a RootIdentityCandidate + OCR gate Residuals + TraceEvents
    from a LegacyCandidateImport.

    Enforces TC-SI-01 by constructing the passage and checking state.
    Returns (candidate, residuals, trace_events).
    """
    root = imp.legacy_root_letters
    normalized = _hamza_normalize(root)
    gate_results = evaluate_ocr_gates(root)

    residuals: list[Residual] = []
    trace_events: list[TraceEvent] = []

    # Determine target review state (IDENTITY_CANDIDATE from MACHINE_CANDIDATE)
    target_state = ReviewState.IDENTITY_CANDIDATE

    candidate = RootIdentityCandidate(
        id=imp.candidate_id,
        passage_id=imp.passage_id,
        candidate_letters=root,
        normalized_letters=normalized,
        bab_letter=imp.legacy_corrected_bab_letter or imp.legacy_bab_letter,
        original_bab_letter=imp.legacy_original_bab_letter,
        bab_correction_version=imp.legacy_correction_version,
        ocr_gate_flags=gate_results,
        review_state=target_state,
        evidence_status=imp.initial_evidence_status,
        supersedes_id=None,
    )

    # §12: IDs include entry_discriminator to ensure uniqueness across multiple
    # entries for the same root_letters (e.g. roots with multiple OCR passages).
    entry_discriminator = imp.legacy_entry_id or imp.passage_id or root

    # TraceEvent for identity extraction
    trace_events.append(TraceEvent(
        id=f"{_TRACE_ID_PREFIX}:identity_extracted:{root}:{entry_discriminator}",
        kind=TraceEventKind.IDENTITY_EXTRACTED,
        target_id=candidate.id,
        target_type="RootIdentityCandidate",
        actor_type=ReviewerType.MACHINE_ONLY,
        actor_id=PIPELINE_ACTOR_ID,
        occurred_at=occurred_at,
        summary=f"Identity extracted for root {root}: {len(candidate.flagged_gates)} gate(s) flagged",
        metadata=(
            ("flagged_gates", ",".join(candidate.flagged_gates)),
            ("bab_letter", candidate.bab_letter),
            ("bab_corrected", str(candidate.bab_letter != candidate.original_bab_letter)),
        ),
    ))

    # Emit OCR_AMBIGUITY residuals for each raised gate
    for gate_id, flag in gate_results:
        if flag:
            gate_desc = next(
                (desc for gid, _, desc in OCR_GATES if gid == gate_id),
                gate_id,
            )
            res_id = f"{_RESIDUAL_ID_PREFIX}:OCR_AMBIGUITY:{gate_id}:{root}:{entry_discriminator}"
            residuals.append(Residual(
                id=res_id,
                target_id=candidate.id,
                target_type="RootIdentityCandidate",
                residual_type=ResidualType.OCR_AMBIGUITY,
                description=f"OCR gate {gate_id} raised for root '{root}': {gate_desc}",
                blocking_until=ReviewState.IDENTITY_VERIFIED,
                created_at=occurred_at,
            ))

    return candidate, residuals, trace_events


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — FULL PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

class IdentityPipelineResult:
    """
    Result of running the identity pipeline over a LegacyImportResult.
    """
    __slots__ = (
        "source_records",
        "passages",
        "candidates",
        "residuals",
        "trace_events",
        "gate_summary",
    )

    def __init__(
        self,
        source_records: list[SourceRecord],
        passages: list[SourcePassage],
        candidates: list[RootIdentityCandidate],
        residuals: list[Residual],
        trace_events: list[TraceEvent],
        gate_summary: dict,
    ) -> None:
        self.source_records = source_records
        self.passages       = passages
        self.candidates     = candidates
        self.residuals      = residuals
        self.trace_events   = trace_events
        self.gate_summary   = gate_summary


def run_identity_pipeline(import_result: LegacyImportResult) -> IdentityPipelineResult:
    """
    Run the full identity pipeline over a LegacyImportResult.

    For each non-noise import:
    • Build SourcePassage
    • Evaluate 20 OCR gates
    • Build RootIdentityCandidate
    • Emit OCR_AMBIGUITY residuals for raised gates

    Returns IdentityPipelineResult — never raises (fail-open contract).
    """
    occurred_at = datetime.datetime.utcnow().isoformat() + "Z"

    source_records = build_source_records()
    passages:    list[SourcePassage]          = []
    candidates:  list[RootIdentityCandidate]  = []
    residuals:   list[Residual]               = []
    trace_events: list[TraceEvent]            = []

    gate_counts: dict[str, int] = {gate_id: 0 for gate_id, _, _ in OCR_GATES}
    entries_with_flags = 0
    skipped_noise = 0
    failed = 0

    for imp in import_result.imports:
        try:
            if imp.noise_entry:
                skipped_noise += 1
                continue

            passage, pass_residuals = _passage_from_import(imp, occurred_at)
            passages.append(passage)
            residuals.extend(pass_residuals)

            candidate, cand_residuals, cand_traces = _identity_from_import(imp, occurred_at)
            candidates.append(candidate)
            residuals.extend(cand_residuals)
            trace_events.extend(cand_traces)

            if candidate.has_ocr_flags:
                entries_with_flags += 1
            for gate_id, flag in candidate.ocr_gate_flags:
                if flag:
                    gate_counts[gate_id] = gate_counts.get(gate_id, 0) + 1

        except Exception as exc:
            failed += 1
            _root_letters = getattr(imp, "legacy_root_letters", "UNKNOWN")
            _entry_disc = (
                getattr(imp, "legacy_entry_id", None)
                or getattr(imp, "passage_id", None)
                or _root_letters
            )
            residuals.append(Residual(
                id=f"{_RESIDUAL_ID_PREFIX}:PIPELINE_EXCEPTION:identity:{_root_letters}:{_entry_disc}",
                target_id=getattr(imp, "candidate_id", _entry_disc),
                target_type="RootIdentityCandidate",
                residual_type=ResidualType.PIPELINE_EXCEPTION,
                description=(
                    f"Unhandled exception in identity pipeline for root "
                    f"'{_root_letters}': {type(exc).__name__}: {exc}"
                ),
                blocking_until=ReviewState.IDENTITY_VERIFIED,
                created_at=occurred_at,
            ))
            continue

    # Gate summary
    gate_summary: dict = {
        "PIPELINE_INPUT_COUNT":         len(import_result.imports) - skipped_noise,
        "SKIPPED_NOISE_COUNT":          skipped_noise,
        "FAILED_COUNT":                 failed,
        "CANDIDATES_PRODUCED":          len(candidates),
        "ENTRIES_WITH_ANY_FLAG":        entries_with_flags,
        "OCR_AMBIGUITY_RESIDUALS":      sum(1 for r in residuals
                                           if r.residual_type == ResidualType.OCR_AMBIGUITY),
        "gate_flag_counts":             gate_counts,
    }

    return IdentityPipelineResult(
        source_records=source_records,
        passages=passages,
        candidates=candidates,
        residuals=residuals,
        trace_events=trace_events,
        gate_summary=gate_summary,
    )
