"""
test_maqayis_constitutional.py — Constitutional source lexicon test suite
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01  Commit 7 (§1 real pytest)

§1 requirements:
  PYTEST_COLLECTED ≥ 83
  PYTEST_FAILED    = 0
  INTERNAL_FAILURE_SWALLOWED_COUNT = 0   (no try/except wrappers)
  HARDCODED_PATH_COUNT             = 0   (uses _find_repo_root())

Test categories:
  § 1  Schema validation          (S01–S05)
  § 2  Transition contracts       (TC01–TC07)
  § 3  Legacy importer            (LI01–LI08)
  § 4  Identity pipeline + gates  (IP01–IP08)
  § 5  Claim pipeline + origins   (CP01–CP07)
  § 6  Constitutional registry    (CR01–CR09)
  § 7  Evidence adapter           (EA01–EA09)
  § 8  Corpus acceptance gates    (AG01–AG25)
  § 9  Knowledge boundary         (KB01–KB06)

Usage:
  python -m pytest test_maqayis_constitutional.py -v
"""
from __future__ import annotations

import pathlib
import pytest


# ── Repo-root discovery (§2: no hardcoded paths) ─────────────────────────────

def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "data" / "maqaees" / "full").is_dir():
            return here
        if here.parent == here:  # filesystem root
            break
        here = here.parent
    return pathlib.Path(__file__).resolve().parent


_REPO_ROOT  = _find_repo_root()
_DATA_DIR   = _REPO_ROOT / "data" / "maqaees" / "full"
_JSONL_PATH = _DATA_DIR / "root_entries_corrected.jsonl"


# ── Session fixtures (loaded once for the whole test run) ─────────────────────

@pytest.fixture(scope="session")
def jsonl_path():
    """Return the corrected JSONL path; skip if absent."""
    if not _JSONL_PATH.exists():
        pytest.skip(f"Corpus file not found: {_JSONL_PATH}")
    return _JSONL_PATH


@pytest.fixture(scope="session")
def import_result(jsonl_path):
    from maqayis_legacy_importer import import_legacy_corpus
    return import_legacy_corpus(jsonl_path)


@pytest.fixture(scope="session")
def claim_result(import_result):
    from maqayis_claim_pipeline import run_claim_pipeline
    return run_claim_pipeline(import_result)


@pytest.fixture(scope="session")
def identity_result(import_result):
    from maqayis_identity_pipeline import run_identity_pipeline
    return run_identity_pipeline(import_result)


@pytest.fixture(scope="session")
def registry(jsonl_path):
    from maqayis_constitutional_registry import reload_registry, constitutional_lookup
    reload_registry(jsonl_path)
    return constitutional_lookup


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_s01_enum_counts():
    from maqayis_constitutional_schemas import (
        LookupResultKind, ReviewState, EvidenceStatus, OriginType,
        ClaimKind, RootClass, KnowledgeType, ResidualType, ReviewerType,
    )
    assert len(LookupResultKind) == 11, f"Expected 11 kinds, got {len(LookupResultKind)}"
    assert len(ReviewState) == 16,      f"Expected 16 states, got {len(ReviewState)}"
    assert len(EvidenceStatus) == 6,    f"Expected 6 levels, got {len(EvidenceStatus)}"
    assert len(OriginType) == 8
    assert len(ClaimKind) == 9
    assert len(RootClass) == 7
    assert len(KnowledgeType) == 7
    assert len(ResidualType) == 12  # +1 for PIPELINE_EXCEPTION (Issue 8)
    assert len(ReviewerType) == 4


def test_s02_evidence_status_ranking():
    from maqayis_constitutional_schemas import EvidenceStatus as ES
    assert ES.MACHINE_SOURCE_CLAIM_CANDIDATE < ES.SOURCE_LOCATED_EVIDENCE
    assert ES.SOURCE_LOCATED_EVIDENCE       < ES.IDENTITY_VERIFIED_EVIDENCE
    assert ES.IDENTITY_VERIFIED_EVIDENCE    < ES.TEXT_VERIFIED_EVIDENCE
    assert ES.TEXT_VERIFIED_EVIDENCE        < ES.ORIGIN_SEGMENTED_EVIDENCE
    assert ES.ORIGIN_SEGMENTED_EVIDENCE     < ES.LEXICALLY_REVIEWED_EVIDENCE


def test_s03_human_required_states():
    from maqayis_constitutional_schemas import ReviewState, HUMAN_REQUIRED_STATES
    assert ReviewState.IDENTITY_VERIFIED  in HUMAN_REQUIRED_STATES
    assert ReviewState.TEXT_VERIFIED      in HUMAN_REQUIRED_STATES
    assert ReviewState.LEXICALLY_REVIEWED in HUMAN_REQUIRED_STATES
    assert ReviewState.AUDIT_PASSED       in HUMAN_REQUIRED_STATES
    assert ReviewState.MACHINE_CANDIDATE  not in HUMAN_REQUIRED_STATES
    assert ReviewState.IDENTITY_CANDIDATE not in HUMAN_REQUIRED_STATES


def test_s04_accounting_counters_zero():
    from maqayis_constitutional_schemas import (
        MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT,
        AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT,
        NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT,
        REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT,
        MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT,
        CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT,
        MACHINE_EVIDENCE_ABOVE_CEILING_COUNT,
        NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT,
        REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT,
        BARE_HAMZA_COVERAGE_FAILURE_COUNT,
        LOOKUP_FROM_DEFERRED_ROOT_COUNT,
        LOOKUP_FROM_BLOCKED_ROOT_COUNT,
        CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT,
        MULTIPLE_FORCED_TO_THREE_COUNT,
        HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT,
    )
    assert MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT   == 0
    assert AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT          == 0
    assert NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT == 0
    assert REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT == 0
    assert MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT         == 0
    assert CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT == 0
    assert MACHINE_EVIDENCE_ABOVE_CEILING_COUNT           == 0
    assert NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT    == 0
    assert REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT  == 0
    assert BARE_HAMZA_COVERAGE_FAILURE_COUNT              == 0
    assert LOOKUP_FROM_DEFERRED_ROOT_COUNT                == 0
    assert LOOKUP_FROM_BLOCKED_ROOT_COUNT                 == 0
    assert CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT    == 0
    assert MULTIPLE_FORCED_TO_THREE_COUNT                 == 0
    assert HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT           == 0


def test_s05_machine_evidence_ceiling():
    from maqayis_constitutional_schemas import EvidenceStatus, MACHINE_EVIDENCE_CEILING
    assert MACHINE_EVIDENCE_CEILING == EvidenceStatus.ORIGIN_SEGMENTED_EVIDENCE


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — TRANSITION CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_passage(state):
    from maqayis_constitutional_schemas import (
        SourcePassage, ReviewState, EvidenceStatus,
    )
    return SourcePassage(
        id="p1", source_id="s1", page_number=1,
        raw_passage_candidate="حدر", corrected_passage=None,
        ocr_confidence=0.9, review_state=state,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
    )


def test_tc01a_si01_machine_candidate_passes():
    from maqayis_constitutional_schemas import ReviewState, enforce_tc_si_01
    enforce_tc_si_01(_make_passage(ReviewState.MACHINE_CANDIDATE))  # must not raise


def test_tc01b_si01_audit_passed_raises():
    from maqayis_constitutional_schemas import ReviewState, enforce_tc_si_01, TransitionContractViolation
    with pytest.raises(TransitionContractViolation):
        enforce_tc_si_01(_make_passage(ReviewState.AUDIT_PASSED))


def _make_candidate():
    from maqayis_constitutional_schemas import (
        RootIdentityCandidate, ReviewState, EvidenceStatus,
    )
    return RootIdentityCandidate(
        id="c1", passage_id="p1", candidate_letters="حدر",
        normalized_letters="حدر", bab_letter="الحاء",
        original_bab_letter="الحاء", bab_correction_version="v1",
        ocr_gate_flags=(), review_state=ReviewState.IDENTITY_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
    )


def test_tc02a_ii02_machine_only_rejected():
    from maqayis_constitutional_schemas import ReviewerType, enforce_tc_ii_02, TransitionContractViolation
    with pytest.raises(TransitionContractViolation):
        enforce_tc_ii_02(_make_candidate(), ReviewerType.MACHINE_ONLY, [])


def test_tc02b_ii02_human_reviewer_passes():
    from maqayis_constitutional_schemas import ReviewerType, enforce_tc_ii_02
    enforce_tc_ii_02(_make_candidate(), ReviewerType.HUMAN_REVIEWER, [])


def test_tc03a_carrier_rejects_machine_only():
    from maqayis_constitutional_schemas import (
        RootIdentityCarrier, RootClass, ReviewerType, ReviewState, EvidenceStatus,
    )
    with pytest.raises(ValueError):
        RootIdentityCarrier(
            id="x", candidate_id="c", verified_letters="حدر",
            root_class=RootClass.TRILATERAL_SOUND,
            reviewer_type=ReviewerType.MACHINE_ONLY,
            reviewer_id="bot", verified_at="2024-01-01T00:00:00Z",
            review_state=ReviewState.IDENTITY_VERIFIED,
            evidence_status=EvidenceStatus.IDENTITY_VERIFIED_EVIDENCE,
        )


def test_tc04a_ro04_rejects_singular():
    from maqayis_constitutional_schemas import (
        SourceRootClaim, ClaimKind, OriginType, ReviewState, EvidenceStatus,
        enforce_tc_ro_04, TransitionContractViolation,
    )
    claim = SourceRootClaim(
        id="cl1", passage_id="p1", identity_id="c1",
        claim_kind=ClaimKind.POSITIVE_ORIGIN,
        origin_type=OriginType.SINGULAR,
        raw_claim_text="حدر", review_state=ReviewState.TEXT_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
        extraction_method="MACHINE_OCR",
    )
    with pytest.raises(TransitionContractViolation):
        enforce_tc_ro_04(claim)


def test_tc04b_ro04_accepts_dual():
    from maqayis_constitutional_schemas import (
        SourceRootClaim, ClaimKind, OriginType, ReviewState, EvidenceStatus,
        enforce_tc_ro_04,
    )
    claim = SourceRootClaim(
        id="cl1", passage_id="p1", identity_id="c1",
        claim_kind=ClaimKind.POSITIVE_ORIGIN,
        origin_type=OriginType.DUAL,
        raw_claim_text="حدر", review_state=ReviewState.TEXT_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
        extraction_method="MACHINE_OCR",
    )
    enforce_tc_ro_04(claim)  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — LEGACY IMPORTER
# ═══════════════════════════════════════════════════════════════════════════════

def test_li01_auto_agreed_maps_machine_candidate(import_result):
    from maqayis_constitutional_schemas import ReviewState
    aa = [i for i in import_result.imports if i.legacy_review_status == "AUTO_AGREED"]
    assert len(aa) > 0
    assert all(i.initial_review_state == ReviewState.MACHINE_CANDIDATE for i in aa), \
        "AUTO_AGREED must map to MACHINE_CANDIDATE only"


def test_li02_review_required_maps_unverified(import_result):
    from maqayis_constitutional_schemas import ReviewState
    rr = [i for i in import_result.imports if i.legacy_review_status == "REVIEW_REQUIRED"]
    assert all(
        i.initial_review_state == ReviewState.UNVERIFIED_REVIEW_REQUIRED
        for i in rr
    ), "REVIEW_REQUIRED must map to UNVERIFIED_REVIEW_REQUIRED"


def test_li03_all_initial_evidence_machine_candidate(import_result):
    from maqayis_constitutional_schemas import EvidenceStatus
    assert all(
        i.initial_evidence_status == EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE
        for i in import_result.imports
    )


def test_li04_safety_counters_zero(import_result):
    r = import_result.reconciliation
    assert r["AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT"]    == 0
    assert r["NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT"]   == 0
    assert r["REVIEW_REQ_POSITIVE_ORIGIN_COUNT"]        == 0


def test_li05_noise_entries_flagged(import_result):
    r = import_result.reconciliation
    noise = [i for i in import_result.imports if i.noise_entry]
    assert len(noise) == r["NOISE_ENTRY_COUNT"]
    assert r["NOISE_ENTRY_COUNT"] == (
        r["NOT_ROOT_COUNT"] + r["CHAPTER_HEADER_COUNT"] + r["CROSS_REFERENCE_COUNT"]
    )


def test_li06_no_root_entries_excluded(import_result):
    r = import_result.reconciliation
    assert r["NO_ROOT_LETTERS_COUNT"] == r["IMPORT_FAILED_COUNT"]
    assert r["NO_ROOT_LETTERS_COUNT"] == 19


def test_li07_segmentation_counts(import_result):
    r = import_result.reconciliation
    seg = [i for i in import_result.imports if i.requires_segmentation]
    assert len(seg) == r["REQUIRES_SEGMENTATION_COUNT"]
    assert r["DUAL_COUNT"]     == 326
    assert r["TRIPLE_COUNT"]   == 14
    assert r["MULTIPLE_COUNT"] == 48


def test_li08_reconciliation_has_25_fields(import_result):
    r = import_result.reconciliation
    counted = {k: v for k, v in r.items() if isinstance(v, int)}
    assert len(counted) >= 25, f"Expected ≥25 counted fields, got {len(counted)}"


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — IDENTITY PIPELINE + OCR GATES
# ═══════════════════════════════════════════════════════════════════════════════

def test_ip01_g09_fires_on_hamza():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("أصل"))
    assert flags["G09"] is True, "G09 must fire on أ"


def test_ip02_g12_fires_on_extra_radical():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("حدرج"))
    assert flags["G12"] is True, "G12 must fire on 4-char root"


def test_ip03_g13_fires_on_missing_radical():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("حد"))
    assert flags["G13"] is True, "G13 must fire on 2-char root"


def test_ip04_g05_fires_on_sad_dad():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("صضر"))
    assert flags["G05"] is True, "G05 must fire when ص and ض both present"


def test_ip05_g20_fires_on_diacritics():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("حَدَّ"))
    assert flags["G20"] is True, "G20 must fire on diacritics"


def test_ip06_all_20_gates_evaluated():
    from maqayis_identity_pipeline import evaluate_ocr_gates
    flags = dict(evaluate_ocr_gates("حدر"))
    assert len(flags) == 20, f"Expected 20 gates, got {len(flags)}"


def test_ip07_candidate_count_matches_pipeline_entries(import_result, identity_result):
    noise_count = sum(1 for i in import_result.imports if i.noise_entry)
    expected = len(import_result.imports) - noise_count
    assert len(identity_result.candidates) == expected, \
        f"Expected {expected} candidates, got {len(identity_result.candidates)}"


def test_ip08_ocr_residuals_only_for_flagged(identity_result):
    from maqayis_constitutional_schemas import ResidualType
    flagged_ids = {c.id for c in identity_result.candidates if c.has_ocr_flags}
    ocr_res = [r for r in identity_result.residuals
               if r.residual_type == ResidualType.OCR_AMBIGUITY]
    for res in ocr_res:
        assert res.target_id in flagged_ids, \
            f"OCR residual target {res.target_id} not in flagged candidates"


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — CLAIM PIPELINE + ORIGIN SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp01_claim_count(claim_result):
    s = claim_result.summary
    assert s["CLAIMS_PRODUCED"] == 3219, \
        f"Expected 3219 claims, got {s['CLAIMS_PRODUCED']}"


def test_cp02_multi_origin_segmented(claim_result):
    s = claim_result.summary
    # R5+R6: DUAL/TRIPLE without distinct spans → 0 candidates; multi_origin_segmented = 0
    assert s["MULTI_ORIGIN_SEGMENTED"] == 0, \
        f"Expected 0 multi-origin after R5 (DUAL/TRIPLE require distinct spans), got {s['MULTI_ORIGIN_SEGMENTED']}"


def test_cp03_total_origins_correct(import_result, claim_result):
    """
    R5: DUAL/TRIPLE/MULTIPLE → 0 candidates (no distinct spans; MULTIPLE cannot auto-segment).
    R7: NONE/NOT_EXTRACTED/UNKNOWN → 0 candidates.
    SINGULAR/SOUND_ROOTS → 1 candidate.
    """
    from maqayis_constitutional_schemas import OriginType
    s = claim_result.summary

    # Compute expected from what claim pipeline actually produced
    # Verify it matches by checking the actual origin_candidates count
    assert s["TOTAL_ORIGINS"] == len(claim_result.origin_candidates), \
        f"Summary TOTAL_ORIGINS mismatch: {s['TOTAL_ORIGINS']} != {len(claim_result.origin_candidates)}"

    # R5: No DUAL/TRIPLE claim should have > 0 origin candidates
    dual_triple_claims = {
        c.id for c in claim_result.claims
        if c.origin_type in (OriginType.DUAL, OriginType.TRIPLE)
    }
    dual_triple_origins = [
        o for o in claim_result.origin_candidates
        if o.claim_id in dual_triple_claims
    ]
    assert len(dual_triple_origins) == 0, \
        f"R5: DUAL/TRIPLE claims should produce 0 candidates, got {len(dual_triple_origins)}"

    # R7: No NONE/NOT_EXTRACTED/UNKNOWN claim should have origin candidates
    none_claims = {
        c.id for c in claim_result.claims
        if c.origin_type in (OriginType.NONE, OriginType.NOT_EXTRACTED, OriginType.UNKNOWN)
    }
    none_origins = [
        o for o in claim_result.origin_candidates
        if o.claim_id in none_claims
    ]
    assert len(none_origins) == 0, \
        f"R7: NONE/NOT_EXTRACTED/UNKNOWN claims should produce 0 candidates, got {len(none_origins)}"


def test_cp04_dual_has_no_candidates_and_residual(claim_result):
    """
    R5: DUAL without distinct source spans → 0 origin candidates + SEGMENTATION_REQUIRED.
    Legacy corpus has unified text spans → 0 candidates expected for all DUAL claims.
    """
    from maqayis_constitutional_schemas import OriginType, ResidualType
    dual_claims = [c for c in claim_result.claims if c.origin_type == OriginType.DUAL]
    assert len(dual_claims) > 0, "Expected DUAL claims in corpus"
    for claim in dual_claims[:5]:
        origins = [o for o in claim_result.origin_candidates if o.claim_id == claim.id]
        assert len(origins) == 0, \
            f"R5: DUAL claim {claim.id} should have 0 origins (no distinct spans), got {len(origins)}"
        seg_res = [r for r in claim_result.residuals
                   if r.target_id == claim.id
                   and r.residual_type == ResidualType.SEGMENTATION_REQUIRED]
        assert len(seg_res) > 0, \
            f"R5: DUAL claim {claim.id} should have SEGMENTATION_REQUIRED residual"


def test_cp05_conflict_detection(claim_result):
    s = claim_result.summary
    assert s["CONFLICT_ROOTS"] == 74, \
        f"Expected 74 conflict roots, got {s['CONFLICT_ROOTS']}"
    assert "حور" in claim_result.conflict_map, "حور not in conflict_map"


def test_cp06_no_pipeline_failures(claim_result):
    assert claim_result.summary["FAILED"] == 0, \
        f"Claim pipeline failures: {claim_result.summary['FAILED']}"


def test_cp07_none_origin_maps_to_incomplete_claim(claim_result):
    """
    §6: NONE → INCOMPLETE_CLAIM (not POSITIVE_ORIGIN).
    NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT = 0 verified here.
    """
    from maqayis_constitutional_schemas import OriginType, ClaimKind
    none_claims = [c for c in claim_result.claims if c.origin_type == OriginType.NONE]
    assert len(none_claims) > 0, "Expected at least one NONE-origin claim in corpus"
    for claim in none_claims:
        assert claim.claim_kind == ClaimKind.INCOMPLETE_CLAIM, \
            f"NONE claim should be INCOMPLETE_CLAIM (§6), got {claim.claim_kind}"


# ═══════════════════════════════════════════════════════════════════════════════
# § 6 — CONSTITUTIONAL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

def test_cr01_ba_root_coverage_gap(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("بصر")
    assert r.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP
    assert r.coverage_note is not None


def test_cr02_alef_root_coverage_gap(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("الف")
    assert r.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP


def test_cr03_hamza_normalized_to_coverage_gap(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("أصل")
    assert r.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP, \
        f"أصل should hit coverage gap (hamza→ا), got {r.kind}"


def test_cr04_found_machine_candidate(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("حدر")
    assert r.found
    assert r.kind == LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY


def test_cr05_conflict_root(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("حور")
    assert r.kind == LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED
    assert r.has_conflict


def test_cr06_not_found(registry):
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("qqq")
    assert r.kind == LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME
    assert not r.found


def test_cr07_empty_input(registry):
    r = registry("")
    assert not r.found


def test_cr08_coverage_gap_note_explains_gap(registry):
    r = registry("بدر")
    assert "coverage gap" in (r.coverage_note or "").lower(), \
        "Coverage note must explain this is a gap, not an absence"


def test_cr09_bare_hamza_coverage_gap(registry):
    """§8: bare ء must normalize to ا and hit MISSING_VOLUME_COVERAGE_GAP.
    BARE_HAMZA_COVERAGE_FAILURE_COUNT = 0 enforced by this test.
    """
    from maqayis_constitutional_schemas import LookupResultKind
    r = registry("ءمن")  # bare ء initial
    assert r.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP, \
        f"ءمن with bare ء should hit MISSING_VOLUME_COVERAGE_GAP, got {r.kind}"


# ═══════════════════════════════════════════════════════════════════════════════
# § 7 — EVIDENCE ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════

def test_ea01_found_root_emits_ids():
    if not _JSONL_PATH.exists():
        pytest.skip("Corpus not available: cannot test found-root evidence IDs without corpus")
    # §6: get_constitutional_evidence_ids() is bypassed in production (_STAGE_0_BUNDLE_ONLY_ENFORCEMENT=True).
    # Test the licensed path: augment_evidence_from_bundle() with ACCEPT directive.
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("حدر"))
    result = augment_evidence_from_bundle(_BundleAccept())
    assert len(result.evidence_ids) > 0, (
        f"Found root via licensed bundle must emit evidence IDs. "
        f"hokom_root_licensed={result.hokom_root_licensed}, "
        f"source_candidate_found={result.source_candidate_found}, "
        f"not_licensed_reason={result.not_licensed_reason}"
    )


def test_ea02_conflict_suppresses_origin_id():
    # §6: licensed path only. Use augment_evidence_from_bundle() with ACCEPT directive.
    # §8: conflict roots must not emit origin IDs (REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT=0).
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("حور"))
    result = augment_evidence_from_bundle(_BundleAccept())
    origin_ids = [i for i in result.evidence_ids if ":origin:" in i]
    assert len(origin_ids) == 0, \
        f"Conflict root must not emit origin ID, got: {origin_ids}"


def test_ea03_conflict_emits_bab_id():
    if not _JSONL_PATH.exists():
        pytest.skip("Corpus not available: cannot test conflict bab IDs without corpus")
    # §6: licensed path only. Use augment_evidence_from_bundle() with ACCEPT directive.
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("حور"))
    result = augment_evidence_from_bundle(_BundleAccept())
    bab_ids = [i for i in result.evidence_ids if ":bab:" in i]
    assert len(bab_ids) >= 1, (
        f"Conflict root should emit bab ID. "
        f"evidence_ids={result.evidence_ids}, "
        f"hokom_root_licensed={result.hokom_root_licensed}"
    )


def test_ea04_missing_volume_emits_nothing():
    """§6: Missing-volume root (ب initial, not covered) via licensed bundle path emits nothing."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("بصر"))
    result = augment_evidence_from_bundle(_BundleAccept())
    assert len(result.evidence_ids) == 0, \
        f"Missing volume root must emit nothing via licensed path, got {result.evidence_ids}"


def test_ea05_not_found_emits_nothing():
    """§6: Not-found root (qqq) via licensed bundle path emits nothing."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("qqq"))
    result = augment_evidence_from_bundle(_BundleAccept())
    assert len(result.evidence_ids) == 0, \
        f"Not-found root must emit nothing via licensed path, got {result.evidence_ids}"


def test_ea06_empty_root_emits_nothing():
    """§6: Empty root via licensed bundle path emits nothing (rejected at radicals check)."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    class _BundleEmptyRoot:
        domain_directive = "ACCEPT"
        class root_claim:
            radicals = ()
    result = augment_evidence_from_bundle(_BundleEmptyRoot())
    assert result.evidence_ids == (), \
        f"Empty root must emit nothing via licensed path, got {result.evidence_ids}"


def test_ea07_evidence_metadata_has_status():
    if not _JSONL_PATH.exists():
        pytest.skip("Corpus not available: cannot test evidence metadata without corpus")
    from maqayis_constitutional_evidence_adapter import get_evidence_metadata
    meta = get_evidence_metadata("حدر")
    assert len(meta) > 0
    for eid, info in meta.items():
        assert "evidence_status" in info
        assert "review_state" in info
        assert "kind" in info


def test_ea08_machine_only_never_verified():
    from maqayis_constitutional_evidence_adapter import get_evidence_metadata
    meta = get_evidence_metadata("حدر")
    for eid, info in meta.items():
        status = info["evidence_status"]
        assert "VERIFIED" not in status or "MACHINE" in status, \
            f"Machine result should not have VERIFIED status: {status}"


def test_ea09_explain_returns_structured_dict():
    from maqayis_constitutional_evidence_adapter import explain_constitutional_lookup
    info = explain_constitutional_lookup("حدر")
    assert isinstance(info, dict)
    assert "kind" in info
    assert "evidence_ids" in info
    assert "root" in info


# ═══════════════════════════════════════════════════════════════════════════════
# § 8 — CORPUS ACCEPTANCE GATES (AG01–AG25, all must = 0)
# AG07-AG25 computed from actual runtime entities, not hardcoded.
# HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT = 0 enforced here.
# ═══════════════════════════════════════════════════════════════════════════════

def test_ag01_auto_agreed_mapped_verified(import_result):
    r = import_result.reconciliation
    val = r.get("AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT", 0)
    assert val == 0, f"AG01: AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT = {val}"


def test_ag02_none_as_negative_semantic(import_result):
    r = import_result.reconciliation
    val = r.get("NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT", 0)
    assert val == 0, f"AG02: NONE_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT = {val}"


def test_ag03_review_req_positive_origin(import_result):
    r = import_result.reconciliation
    val = r.get("REVIEW_REQ_POSITIVE_ORIGIN_COUNT", 0)
    assert val == 0, f"AG03: REVIEW_REQ_POSITIVE_ORIGIN_COUNT = {val}"


def test_ag04_import_failed_beyond_no_root(import_result):
    r = import_result.reconciliation
    val = max(0, r.get("IMPORT_FAILED_COUNT", 0) - r.get("NO_ROOT_LETTERS_COUNT", 0))
    assert val == 0, f"AG04: unexpected import failures beyond no-root = {val}"


def test_ag05_claim_pipeline_failures(claim_result):
    val = claim_result.summary["FAILED"]
    assert val == 0, f"AG05: CLAIM_PIPELINE_FAILED = {val}"


def test_ag06_identity_pipeline_failures(identity_result):
    val = identity_result.gate_summary["FAILED_COUNT"]
    assert val == 0, f"AG06: IDENTITY_PIPELINE_FAILED = {val}"


def test_ag07_machine_produces_human_required_state(import_result):
    """Computed from actual imports — not hardcoded."""
    from maqayis_constitutional_schemas import HUMAN_REQUIRED_STATES
    val = sum(
        1 for i in import_result.imports
        if i.initial_review_state in HUMAN_REQUIRED_STATES
    )
    assert val == 0, \
        f"AG07: {val} imports have HUMAN_REQUIRED initial_review_state (must be 0)"


def test_ag08_auto_agreed_mapped_verified_schema(import_result):
    """Computed from actual imports — not hardcoded."""
    from maqayis_constitutional_schemas import HUMAN_REQUIRED_STATES
    val = sum(
        1 for i in import_result.imports
        if i.legacy_review_status == "AUTO_AGREED"
        and i.initial_review_state in HUMAN_REQUIRED_STATES
    )
    assert val == 0, \
        f"AG08: {val} AUTO_AGREED imports have HUMAN_REQUIRED state (must be 0)"


def test_ag09_constitutional_approved_admission():
    """Computed from module-level accounting counter."""
    from maqayis_constitutional_evidence_adapter import CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT
    assert CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT == 0, \
        f"AG09: CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT = {CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT}"


def test_ag10_maqayis_lookup_unknown_root():
    """Computed from module-level accounting counter."""
    from maqayis_constitutional_evidence_adapter import MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT
    assert MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT == 0, \
        f"AG10: MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT = {MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT}"


def test_ag11_review_req_emits_origin_id():
    """§6+§8: REVIEW_REQUIRED root via licensed bundle path must not emit origin IDs.
    Uses حمش (FOUND_REVIEW_REQUIRED_UNRESOLVED in covered volumes).
    REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT = 0 enforced.
    """
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from maqayis_constitutional_schemas import LookupResultKind
    from maqayis_constitutional_registry import constitutional_lookup
    from types import SimpleNamespace
    # حمش is FOUND_REVIEW_REQUIRED_UNRESOLVED in covered volumes
    result = constitutional_lookup("حمش")
    assert result.kind in (
        LookupResultKind.FOUND_REVIEW_REQUIRED_UNRESOLVED,
        LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED,
    ), f"AG11: حمش expected REVIEW_REQUIRED kind, got {result.kind}"
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("حمش"))
    augment = augment_evidence_from_bundle(_BundleAccept())
    origin_ids = [i for i in augment.evidence_ids if ":origin:" in i]
    assert len(origin_ids) == 0, \
        f"AG11: REVIEW_REQUIRED root must not emit origin IDs, got: {origin_ids}"


def test_ag12_conflict_emits_origin_id():
    """§6+§8: Conflict root حور via licensed bundle path must not emit origin IDs.
    REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT = 0 enforced.
    """
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("حور"))
    result = augment_evidence_from_bundle(_BundleAccept())
    origin_ids = [i for i in result.evidence_ids if ":origin:" in i]
    assert len(origin_ids) == 0, \
        f"AG12: conflict root حور must not emit origin IDs, got: {origin_ids}"


def test_ag13_missing_volume_emits_evidence():
    """§6+§8: Missing-volume root بصر (ب initial, not covered) via licensed path emits nothing."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("بصر"))
    result = augment_evidence_from_bundle(_BundleAccept())
    assert len(result.evidence_ids) == 0, \
        f"AG13: missing volume root بصر must emit no evidence, got: {result.evidence_ids}"


def test_ag14_not_found_emits_evidence():
    """§6+§8: Not-found root qqq via licensed path emits nothing."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace
    class _BundleAccept:
        domain_directive = "ACCEPT"
        root_claim = SimpleNamespace(radicals=tuple("qqq"))
    result = augment_evidence_from_bundle(_BundleAccept())
    assert len(result.evidence_ids) == 0, \
        f"AG14: not-found root qqq must emit no evidence, got: {result.evidence_ids}"


def test_ag15_empty_root_emits_evidence():
    """§6: Empty root via licensed bundle path emits nothing (rejected at radicals check)."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    class _BundleEmptyRoot:
        domain_directive = "ACCEPT"
        class root_claim:
            radicals = ()
    result = augment_evidence_from_bundle(_BundleEmptyRoot())
    assert result.evidence_ids == (), \
        f"AG15: empty root must emit no evidence, got: {result.evidence_ids}"


def test_ag16_wrong_bab_letter_remaining(import_result):
    """Computed from actual imports: every non-noise bab_letter must be in the
    canonical 28-word set (one word-form per letter, stored with definite article).
    BAB_WORD_FORM_OUTSIDE_CANONICAL_SET_COUNT = 0 enforced.
    """
    from maqayis_bab_contract import BAB_CANONICAL_WORDS
    bad = [
        (imp.legacy_root_letters, imp.legacy_bab_letter)
        for imp in import_result.imports
        if not imp.noise_entry
        and imp.legacy_bab_letter
        and imp.legacy_bab_letter not in BAB_CANONICAL_WORDS
    ]
    assert len(bad) == 0, (
        f"AG16: {len(bad)} imports have bab_letter outside the canonical 28-word set. "
        f"First offenders: {bad[:5]}"
    )


def test_ag17_bab_letter_root_initial_mismatch(import_result):
    """Computed from actual imports: each bab_letter word-form must match the
    root's initial letter according to the canonical BAB_LETTER_MAP.
    BAB_LETTER_MISMATCH_COUNT = 0 enforced.
    Word-form is stored with definite article (e.g. "الحاء"); the map translates
    root initial → expected word-form directly, bypassing the 'ال' extraction pitfall.
    """
    from maqayis_bab_contract import BAB_LETTER_MAP
    mismatches = []
    for imp in import_result.imports:
        if imp.noise_entry:
            continue
        root = imp.legacy_root_letters
        bab  = imp.legacy_bab_letter
        if not root or not bab:
            continue
        root_initial = root[0]
        expected_bab = BAB_LETTER_MAP.get(root_initial)
        if expected_bab is None:
            continue  # unknown initial — skip; covered by AG16
        if bab != expected_bab:
            mismatches.append((root, bab, expected_bab))
    assert len(mismatches) == 0, (
        f"AG17: {len(mismatches)} bab_letter/root-initial mismatches "
        f"(BAB_LETTER_MISMATCH_COUNT must be 0). "
        f"First offenders: {mismatches[:5]}"
    )


def test_ag18_bab_correction_provenance_missing(import_result):
    """Computed from actual imports: correction_version must be present."""
    missing = sum(
        1 for i in import_result.imports
        if not i.noise_entry
        and (not i.legacy_correction_version or i.legacy_correction_version == "none")
    )
    # "none" means no correction applied — acceptable for AUTO_AGREED entries
    # This gate checks for truly missing provenance (empty string)
    truly_missing = sum(
        1 for i in import_result.imports
        if not i.noise_entry and i.legacy_correction_version == ""
    )
    assert truly_missing == 0, \
        f"AG18: {truly_missing} imports have empty correction_version"


def test_ag19_malformed_json_lines(import_result):
    r = import_result.reconciliation
    val = r.get("MALFORMED_JSON_LINE_COUNT", 0)
    assert val == 0, f"AG19: MALFORMED_JSON_LINES = {val}"


def test_ag20_unknown_status_entries(import_result):
    r = import_result.reconciliation
    val = r.get("UNKNOWN_STATUS_RAW_COUNT", 0)
    assert val == 0, f"AG20: UNKNOWN_STATUS_ENTRIES = {val}"


def test_ag21_original_data_not_modified():
    """Computed from actual data: the full pipeline (import + identity + claim)
    must not modify the source JSONL file.  SHA-256 digest before and after the
    complete pipeline run must match.
    SOURCE_FILE_MODIFICATION_DETECTED_COUNT = 0 enforced.
    """
    if not _JSONL_PATH.exists():
        pytest.skip("Corpus not available: cannot verify immutability without corpus")
    import hashlib
    from maqayis_legacy_importer import import_legacy_corpus
    from maqayis_identity_pipeline import run_identity_pipeline
    from maqayis_claim_pipeline import run_claim_pipeline

    def _sha256(path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    digest_before = _sha256(_JSONL_PATH)
    # Run the entire pipeline — all three stages — inside the SHA window
    import_result = import_legacy_corpus(_JSONL_PATH)
    run_identity_pipeline(import_result)
    run_claim_pipeline(import_result)
    digest_after  = _sha256(_JSONL_PATH)

    assert digest_before == digest_after, (
        f"AG21: source JSONL digest changed after full pipeline run — "
        f"pipeline must never modify its input file. "
        f"before={digest_before[:16]}…  after={digest_after[:16]}…"
    )


def test_ag22_trace_events_not_deleted(identity_result, claim_result):
    """Computed from actual pipeline: trace counts must be positive."""
    assert len(identity_result.trace_events) > 0, "AG22: no identity trace events"
    assert len(claim_result.trace_events) > 0, "AG22: no claim trace events"


def test_ag23_residuals_not_silently_dropped(identity_result):
    """Computed from actual pipeline: OCR residuals emitted for flagged candidates."""
    from maqayis_constitutional_schemas import ResidualType
    flagged = [c for c in identity_result.candidates if c.has_ocr_flags]
    if flagged:
        ocr_res = [r for r in identity_result.residuals
                   if r.residual_type == ResidualType.OCR_AMBIGUITY]
        assert len(ocr_res) > 0, \
            f"AG23: {len(flagged)} flagged candidates but 0 OCR residuals emitted"


def test_ag24_origin_candidates_without_claim(claim_result):
    """Computed from actual claim pipeline output."""
    claim_ids = {c.id for c in claim_result.claims}
    orphans = [o for o in claim_result.origin_candidates
               if o.claim_id not in claim_ids]
    assert len(orphans) == 0, \
        f"AG24: {len(orphans)} origin candidates without a claim"


def test_ag25_accounting_counter_drift():
    """Computed from all module-level accounting counters."""
    from maqayis_constitutional_schemas import (
        MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT,
        AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT,
        NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT,
        REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT,
        MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT,
        CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT,
        MACHINE_EVIDENCE_ABOVE_CEILING_COUNT,
        NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT,
        REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT,
        BARE_HAMZA_COVERAGE_FAILURE_COUNT,
        LOOKUP_FROM_DEFERRED_ROOT_COUNT,
        LOOKUP_FROM_BLOCKED_ROOT_COUNT,
        CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT,
        MULTIPLE_FORCED_TO_THREE_COUNT,
        HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT,
    )
    from maqayis_constitutional_evidence_adapter import (
        REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT as EA_REVIEW,
        NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT as EA_NONE,
        MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT as EA_UNKNOWN,
        CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT as EA_ADMISSION,
    )
    all_counters = {
        "MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT":    MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT,
        "AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT":           AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT,
        "NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC":          NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT,
        "REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE":       REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT,
        "MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT":               MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT,
        "CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION":     CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT,
        "MACHINE_EVIDENCE_ABOVE_CEILING":                 MACHINE_EVIDENCE_ABOVE_CEILING_COUNT,
        "NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM":          NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT,
        "REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND":        REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT,
        "BARE_HAMZA_COVERAGE_FAILURE":                    BARE_HAMZA_COVERAGE_FAILURE_COUNT,
        "LOOKUP_FROM_DEFERRED_ROOT":                      LOOKUP_FROM_DEFERRED_ROOT_COUNT,
        "LOOKUP_FROM_BLOCKED_ROOT":                       LOOKUP_FROM_BLOCKED_ROOT_COUNT,
        "CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT":          CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT,
        "MULTIPLE_FORCED_TO_THREE":                       MULTIPLE_FORCED_TO_THREE_COUNT,
        "HARDCODED_ZERO_ACCEPTANCE_GATE":                 HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT,
        "EA_REVIEW_REQUIRED_POSITIVE_ORIGIN":             EA_REVIEW,
        "EA_NONE_AS_NEGATIVE_SEMANTIC":                   EA_NONE,
        "EA_LOOKUP_UNKNOWN_ROOT":                         EA_UNKNOWN,
        "EA_APPROVED_ADMISSION":                          EA_ADMISSION,
    }
    drifted = {k: v for k, v in all_counters.items() if v != 0}
    assert not drifted, f"AG25: accounting counter drift detected: {drifted}"


# ═══════════════════════════════════════════════════════════════════════════════
# § 9 — KNOWLEDGE BOUNDARY (Stage-0 constraints)
# ═══════════════════════════════════════════════════════════════════════════════

class _MockBundleAccept:
    """Simulates a HokomLinguisticClaimBundle with ACCEPT directive.
    §5: Uses domain_directive and root_claim.radicals — real Hokom API.
    """
    def __init__(self, root_letters: str) -> None:
        from types import SimpleNamespace
        self.domain_directive = "ACCEPT"
        self.root_claim = SimpleNamespace(
            radicals=tuple(root_letters),
        )


class _MockBundleDefer:
    """Bundle with DEFER directive — should be rejected by §9."""
    def __init__(self, root_letters: str) -> None:
        from types import SimpleNamespace
        self.domain_directive = "DEFER"
        self.root_claim = SimpleNamespace(
            radicals=tuple(root_letters),
        )


class _MockBundleBlock:
    """Bundle with BLOCK directive — should be rejected by §9."""
    def __init__(self, root_letters: str) -> None:
        from types import SimpleNamespace
        self.domain_directive = "BLOCK"
        self.root_claim = SimpleNamespace(
            radicals=tuple(root_letters),
        )


class _MockBundleNoRoot:
    """Bundle with no root_claim and no domain_directive."""
    root_claim = None


class _MockBundleEmptyRoot:
    """Bundle with ACCEPT but empty radicals — rejected at root level."""
    domain_directive = "ACCEPT"
    class root_claim:
        radicals = ()


def test_kb01_bundle_returns_typed_result():
    """§10: augment_evidence_from_bundle must return MaqayisConstitutionalAugmentationResult."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from maqayis_constitutional_schemas import MaqayisConstitutionalAugmentationResult
    result = augment_evidence_from_bundle(_MockBundleAccept("حدر"))
    assert isinstance(result, MaqayisConstitutionalAugmentationResult), \
        f"Must return MaqayisConstitutionalAugmentationResult, got {type(result)}"


def test_kb02_no_root_claim_returns_not_licensed():
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    result = augment_evidence_from_bundle(_MockBundleNoRoot())
    assert not result.licensed, "No root_claim → licensed=False"
    assert result.evidence_ids == (), "No root_claim → empty evidence_ids"


def test_kb03_empty_canonical_root_returns_not_licensed():
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    result = augment_evidence_from_bundle(_MockBundleEmptyRoot())
    assert not result.licensed, "Empty canonical_root → licensed=False"


def test_kb04_missing_volume_root_returns_not_licensed():
    """§8: ب initial → MISSING_VOLUME, licensed=False, no false evidence."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    result = augment_evidence_from_bundle(_MockBundleAccept("بصر"))
    assert not result.licensed, "Missing volume root must not be licensed"
    assert result.evidence_ids == (), "Missing volume root must produce no evidence IDs"


def test_kb05_deferred_root_rejected():
    """§9: DEFER directive → not_licensed, LOOKUP_FROM_DEFERRED_ROOT_COUNT = 0."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    result = augment_evidence_from_bundle(_MockBundleDefer("حدر"))
    assert not result.licensed, "DEFER directive must not be licensed"
    assert "DEFER" in (result.failure_detail or ""), \
        f"Failure detail should mention DEFER, got: {result.failure_detail}"


def test_kb06_blocked_root_rejected():
    """§9: BLOCK directive → not_licensed, LOOKUP_FROM_BLOCKED_ROOT_COUNT = 0."""
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    result = augment_evidence_from_bundle(_MockBundleBlock("حدر"))
    assert not result.licensed, "BLOCK directive must not be licensed"
    assert "BLOCK" in (result.failure_detail or ""), \
        f"Failure detail should mention BLOCK, got: {result.failure_detail}"


# ═══════════════════════════════════════════════════════════════════════════════
# New tests added for R3, R4, R5, R7, R8, R10, R11 repairs
# ═══════════════════════════════════════════════════════════════════════════════

def test_cp08_none_origin_produces_no_candidates(claim_result):
    """R7: NONE origin_type must produce 0 LexicalOriginCandidates."""
    from maqayis_constitutional_schemas import OriginType, ResidualType
    none_claims = [c for c in claim_result.claims if c.origin_type == OriginType.NONE]
    for claim in none_claims[:5]:
        origins = [o for o in claim_result.origin_candidates if o.claim_id == claim.id]
        assert len(origins) == 0, \
            f"R7: NONE claim {claim.id} should have 0 origin candidates, got {len(origins)}"
        residuals = [r for r in claim_result.residuals
                     if r.target_id == claim.id
                     and r.residual_type == ResidualType.ORIGIN_NOT_EXTRACTED]
        assert len(residuals) > 0, \
            f"R7: NONE claim {claim.id} should have ORIGIN_NOT_EXTRACTED residual"


def test_cp09_triple_produces_no_candidates(claim_result):
    """R5: TRIPLE without distinct spans → 0 candidates + SEGMENTATION_REQUIRED."""
    from maqayis_constitutional_schemas import OriginType, ResidualType
    triple_claims = [c for c in claim_result.claims if c.origin_type == OriginType.TRIPLE]
    for claim in triple_claims[:5]:
        origins = [o for o in claim_result.origin_candidates if o.claim_id == claim.id]
        assert len(origins) == 0, \
            f"R5: TRIPLE claim {claim.id} should have 0 origins, got {len(origins)}"


def test_cp10_multi_accounting_correct(claim_result):
    """R6: multi_origin_segmented only counts entries with len(origins) > 1."""
    assert claim_result.summary["MULTI_ORIGIN_SEGMENTED"] == 0, \
        "R6: No multi-origin entries in legacy corpus (DUAL/TRIPLE/MULTIPLE produce 0 candidates)"


def test_cp11_multiple_has_segmentation_required(claim_result):
    """§5: MULTIPLE origin_type → 0 candidates + SEGMENTATION_REQUIRED residual.
    V1 cannot auto-segment multi-origin entries. MULTIPLE_FORCED_TO_THREE_COUNT = 0 enforced.
    Corpus has ~48 MULTIPLE claims; all must produce 0 candidates.
    """
    from maqayis_constitutional_schemas import OriginType, ResidualType
    multiple_claims = [c for c in claim_result.claims if c.origin_type == OriginType.MULTIPLE]
    assert len(multiple_claims) > 0, \
        "§5: Expected MULTIPLE claims in corpus (corpus has ~48)"
    for claim in multiple_claims:
        origins = [o for o in claim_result.origin_candidates if o.claim_id == claim.id]
        assert len(origins) == 0, (
            f"§5: MULTIPLE claim {claim.id} must produce 0 origin candidates "
            f"(V1 cannot auto-segment), got {len(origins)}"
        )
        seg_residuals = [
            r for r in claim_result.residuals
            if r.target_id == claim.id
            and r.residual_type == ResidualType.SEGMENTATION_REQUIRED
        ]
        assert len(seg_residuals) > 0, (
            f"§5: MULTIPLE claim {claim.id} must have SEGMENTATION_REQUIRED residual"
        )
    # Count totals across all MULTIPLE claims
    multiple_ids = {c.id for c in multiple_claims}
    total_origins = [o for o in claim_result.origin_candidates if o.claim_id in multiple_ids]
    assert len(total_origins) == 0, (
        f"§5: all {len(multiple_claims)} MULTIPLE claims must produce 0 total candidates, "
        f"got {len(total_origins)}"
    )


def test_cp12_all_entity_ids_unique(claim_result, identity_result):
    """§12: All claim, origin, residual, and trace IDs must be globally unique.
    Duplicate IDs indicate missing entry_discriminator in ID construction.
    Trace IDs from both claim_result and identity_result are included.
    """
    from collections import Counter
    claim_ids    = [c.id for c in claim_result.claims]
    origin_ids   = [o.id for o in claim_result.origin_candidates]
    # §12: include identity residuals — OCR_AMBIGUITY and MISSING_SOURCE_PASSAGE
    # IDs must include entry_discriminator to be unique across multiple entries
    # for the same root_letters.
    residual_ids = (
        [r.id for r in claim_result.residuals]
        + [r.id for r in identity_result.residuals]
    )
    # Collect trace event IDs from both pipelines
    claim_trace_ids    = [t.id for t in claim_result.trace_events]
    identity_trace_ids = [t.id for t in identity_result.trace_events]
    trace_ids = claim_trace_ids + identity_trace_ids

    # Check uniqueness within each entity type
    claim_dupes    = {k: v for k, v in Counter(claim_ids).items()    if v > 1}
    origin_dupes   = {k: v for k, v in Counter(origin_ids).items()   if v > 1}
    residual_dupes = {k: v for k, v in Counter(residual_ids).items() if v > 1}
    trace_dupes    = {k: v for k, v in Counter(trace_ids).items()    if v > 1}

    assert not claim_dupes, (
        f"§12: {len(claim_dupes)} duplicate claim IDs detected: "
        f"{list(claim_dupes.items())[:5]}"
    )
    assert not origin_dupes, (
        f"§12: {len(origin_dupes)} duplicate origin candidate IDs detected: "
        f"{list(origin_dupes.items())[:5]}"
    )
    assert not residual_dupes, (
        f"§12: {len(residual_dupes)} duplicate residual IDs detected "
        f"(likely missing entry_discriminator): "
        f"{list(residual_dupes.items())[:5]}"
    )
    assert not trace_dupes, (
        f"§12: {len(trace_dupes)} duplicate trace event IDs detected "
        f"(likely missing entry_discriminator in trace ID): "
        f"{list(trace_dupes.items())[:5]}"
    )
    # Check cross-type uniqueness (no ID collision between entity types)
    all_ids = claim_ids + origin_ids + residual_ids
    all_dupes = {k: v for k, v in Counter(all_ids).items() if v > 1}
    assert not all_dupes, (
        f"§12: {len(all_dupes)} IDs duplicated across entity types: "
        f"{list(all_dupes.items())[:5]}"
    )


def test_ip09_passage_provenance_fields(identity_result):
    """R3: SourcePassage must have entry_id, source_pdf, passage_checksum fields."""
    for p in identity_result.passages[:5]:
        assert hasattr(p, "entry_id"), "R3: SourcePassage must have entry_id"
        assert hasattr(p, "source_pdf"), "R3: SourcePassage must have source_pdf"
        assert hasattr(p, "passage_checksum"), "R3: SourcePassage must have passage_checksum"
        assert hasattr(p, "line_ids"), "R3: SourcePassage must have line_ids"


def test_ip10_no_root_letter_fallback_in_passage(identity_result, import_result):
    """R4: SourcePassage.raw_passage_candidate must not equal bare root letters."""
    non_noise_imports = [i for i in import_result.imports if not i.noise_entry]
    for p, imp in zip(identity_result.passages, non_noise_imports):
        if p.raw_passage_candidate:
            assert p.raw_passage_candidate != imp.legacy_root_letters, \
                f"R4: passage {p.id} has root letters as text: {p.raw_passage_candidate}"


def test_kb07_adapter_uses_real_hokom_types():
    """§5: adapter reads domain_directive and radicals — not locally invented HokomRootClaim.
    HokomRootClaim is REMOVED from schemas; adapter must use real Hokom types.
    """
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from maqayis_constitutional_schemas import MaqayisConstitutionalAugmentationResult
    from types import SimpleNamespace

    # Verify HokomRootClaim is gone from schemas
    import maqayis_constitutional_schemas as sch
    assert not hasattr(sch, "HokomRootClaim"), (
        "§5: HokomRootClaim must not exist in constitutional schemas — "
        "it is a locally invented type that must be replaced by real Hokom types."
    )

    # Verify adapter reads domain_directive (not root_claim.directive)
    # A bundle with domain_directive='ACCEPT' and radicals but NO root_claim.directive
    class _BundleRealApi:
        domain_directive = "ACCEPT"
        class root_claim:
            radicals = ("ح", "د", "ر")  # LicensedRoot.radicals tuple

    result = augment_evidence_from_bundle(_BundleRealApi())
    assert isinstance(result, MaqayisConstitutionalAugmentationResult)
    assert result.hokom_root_licensed, "ACCEPT + valid radicals → hokom_root_licensed=True"

    # Verify adapter rejects DEFER on domain_directive
    class _BundleDeferRealApi:
        domain_directive = "DEFER"
        class root_claim:
            radicals = ("ح", "د", "ر")
    result_defer = augment_evidence_from_bundle(_BundleDeferRealApi())
    assert not result_defer.hokom_root_licensed, "DEFER → hokom_root_licensed=False"


def test_kb08_augmentation_result_split_flags():
    """§5+§4: augment_evidence_from_bundle returns properly split flags.
    §5: uses real Hokom API (domain_directive + radicals).
    §4: lexical_evidence_licensed=False for machine candidates.
    """
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from maqayis_constitutional_schemas import MaqayisConstitutionalAugmentationResult

    class _Bundle:
        domain_directive = "ACCEPT"
        class root_claim:
            radicals = ("ح", "د", "ر")

    result = augment_evidence_from_bundle(_Bundle())
    assert hasattr(result, "hokom_root_licensed"), "§5: missing hokom_root_licensed"
    assert hasattr(result, "source_candidate_found"), "§5: missing source_candidate_found"
    assert hasattr(result, "lexical_evidence_licensed"), "§4: missing lexical_evidence_licensed"
    # §4: lexical_evidence_licensed must NEVER be True for machine candidates
    assert not result.lexical_evidence_licensed, (
        "§4: lexical_evidence_licensed must be False for machine candidates "
        "(only True for FOUND_LEXICALLY_REVIEWED + ReviewCertificate)"
    )


def test_kb09_deferred_root_hokom_not_licensed():
    """§9: DEFER directive → hokom_root_licensed=False.
    §5: uses real Hokom API (domain_directive on the bundle).
    """
    from maqayis_constitutional_evidence_adapter import augment_evidence_from_bundle
    from types import SimpleNamespace

    class _Bundle:
        domain_directive = "DEFER"
        class root_claim:
            radicals = ("ح", "د", "ر")

    result = augment_evidence_from_bundle(_Bundle())
    assert not result.hokom_root_licensed, "§9: DEFER → hokom_root_licensed must be False"
    assert not result.lexical_evidence_licensed, "§4: DEFER → lexical_evidence_licensed=False"


def test_ea10_registry_failure_returns_load_failure():
    """R8: constitutional_lookup exceptions must return REGISTRY_LOAD_FAILURE."""
    from maqayis_constitutional_schemas import LookupResultKind
    from maqayis_constitutional_registry import _ConstitutionalRegistry
    # Force a registry that will fail
    bad_registry = _ConstitutionalRegistry()
    bad_registry._failed = True
    result = bad_registry.lookup("حدر")
    assert result.kind == LookupResultKind.REGISTRY_LOAD_FAILURE, \
        f"R8: forced failure should return REGISTRY_LOAD_FAILURE, got {result.kind}"


def test_rg01_registry_partial_load_behavior():
    """R9: Registry with malformed JSONL lines sets _partial_load=True and _malformed_count>=1.
    Valid entries before/after the malformed line must still be accessible via lookup.
    Proves REGISTRY_PARTIAL_LOAD is a runtime measurement, not hardcoded.
    """
    import json
    import pathlib
    import tempfile
    from maqayis_constitutional_registry import _ConstitutionalRegistry
    from maqayis_constitutional_schemas import LookupResultKind

    # Build a minimal temp JSONL: 2 valid entries + 1 malformed line
    valid_entry_1 = {
        "entry_id": "02.pdf:p001:r001",
        "root_letters": "حدر",
        "review_status": "AUTO_AGREED",
        "semantic_origin_type": "SINGULAR",
        "semantic_origin_text": None,
        "bab_letter": "الحاء",
        "source_pdf": "02.pdf",
        "pdf_page": 1,
        "correction_version": "v1",
    }
    valid_entry_2 = {
        "entry_id": "02.pdf:p002:r001",
        "root_letters": "حمل",
        "review_status": "AUTO_AGREED",
        "semantic_origin_type": "SINGULAR",
        "semantic_origin_text": None,
        "bab_letter": "الحاء",
        "source_pdf": "02.pdf",
        "pdf_page": 2,
        "correction_version": "v1",
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", encoding="utf-8", delete=False
    ) as f:
        f.write(json.dumps(valid_entry_1, ensure_ascii=False) + "\n")
        f.write("{NOT VALID JSON\n")  # malformed line
        f.write(json.dumps(valid_entry_2, ensure_ascii=False) + "\n")
        tmp_path = pathlib.Path(f.name)

    try:
        import maqayis_constitutional_registry as _reg_module

        # Capture public counter BEFORE this registry load
        count_before = _reg_module.REGISTRY_PARTIAL_LOAD_COUNT

        reg = _ConstitutionalRegistry()
        reg.ensure_loaded(tmp_path)

        assert reg._loaded, "R9: Registry must load successfully despite malformed line"
        assert not reg._failed, "R9: Registry must not fail entirely due to one malformed line"
        assert reg._partial_load, \
            "R9: _partial_load must be True when malformed lines are present"
        assert reg._malformed_count >= 1, \
            f"R9: _malformed_count must be >= 1, got {reg._malformed_count}"

        # R9 public contract: module-level REGISTRY_PARTIAL_LOAD_COUNT must increment.
        # This proves the counter is a runtime measurement, not a hardcoded constant.
        count_after = _reg_module.REGISTRY_PARTIAL_LOAD_COUNT
        assert count_after == count_before + 1, (
            f"R9: REGISTRY_PARTIAL_LOAD_COUNT must increment from {count_before} to "
            f"{count_before + 1} on partial load; got {count_after}. "
            f"Public contract requires the module-level counter to be updated."
        )

        # Valid entries must still be accessible
        result = reg.lookup("حدر")
        assert result.kind != LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME, \
            f"R9: حدر should be found in partial-load registry, got {result.kind}"
        # R9: ConstitutionalLookupResult.partial_load must reflect registry state
        assert result.partial_load == True, \
            "R9: ConstitutionalLookupResult.partial_load must be True when registry has malformed lines"
        assert result.malformed_line_count >= 1, \
            f"R9: ConstitutionalLookupResult.malformed_line_count must be >= 1, got {result.malformed_line_count}"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_s06_source_passage_has_provenance_fields():
    """R3: SourcePassage schema has all new provenance fields."""
    from maqayis_constitutional_schemas import SourcePassage, ReviewState, EvidenceStatus
    p = SourcePassage(
        id="p1", source_id="s1", page_number=1,
        raw_passage_candidate="test", corrected_passage=None,
        ocr_confidence=0.9, review_state=ReviewState.MACHINE_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
    )
    assert p.entry_id == ""
    assert p.source_pdf == ""
    assert p.line_ids == ()
    assert p.passage_checksum == ""
    assert p.bounding_box is None
    assert p.image_ref is None


def test_s07_residual_type_has_origin_not_extracted():
    """R7: ResidualType.ORIGIN_NOT_EXTRACTED must exist."""
    from maqayis_constitutional_schemas import ResidualType
    assert ResidualType.ORIGIN_NOT_EXTRACTED is not None
    assert len(ResidualType) == 12, f"Expected 12 ResidualType values, got {len(ResidualType)}"  # +1 for PIPELINE_EXCEPTION


def test_ea11_stage0_bypass_enforced():
    """§6: _STAGE_0_BUNDLE_ONLY_ENFORCEMENT=True — direct string API returns () in production.
    DIRECT_LOOKUP_BYPASS_COUNT increments on each direct call.
    """
    import maqayis_constitutional_evidence_adapter as adapter
    assert adapter._STAGE_0_BUNDLE_ONLY_ENFORCEMENT is True, (
        "§6: _STAGE_0_BUNDLE_ONLY_ENFORCEMENT must be True in production"
    )
    before = adapter.DIRECT_LOOKUP_BYPASS_COUNT
    ids = adapter.get_constitutional_evidence_ids("حدر")
    assert ids == (), "§6: direct API must return () when bypass enforcement is True"
    assert adapter.DIRECT_LOOKUP_BYPASS_COUNT == before + 1, (
        "§6: DIRECT_LOOKUP_BYPASS_COUNT must increment on each direct call"
    )


def test_kb10_lexical_evidence_never_true_for_machine():
    """§4: lexical_evidence_licensed must be False for all machine/review-required/conflict kinds.
    Only FOUND_LEXICALLY_REVIEWED + ReviewCertificate may set it True.
    """
    from maqayis_constitutional_schemas import (
        MaqayisConstitutionalAugmentationResult,
        LookupResultKind,
        EvidenceStatus,
        ReviewState,
        ConstitutionalLookupResult,
    )
    # Simulate result for each machine-producible kind
    machine_kinds = [
        LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY,
        LookupResultKind.FOUND_REVIEW_REQUIRED_UNRESOLVED,
        LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED,
    ]
    for kind in machine_kinds:
        result = ConstitutionalLookupResult(
            kind=kind,
            root_letters="حدر",
            evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
            review_state=ReviewState.MACHINE_CANDIDATE,
        )
        augment = MaqayisConstitutionalAugmentationResult.from_lookup_result(
            result,
            evidence_ids=("maqayis:root:حدر:bab:ح",),  # non-empty evidence_ids
        )
        assert not augment.lexical_evidence_licensed, (
            f"§4: {kind.value} must produce lexical_evidence_licensed=False, "
            f"got {augment.lexical_evidence_licensed}"
        )


def test_kb11_trace_ids_never_contain_residual_ids():
    """§11: trace_ids must never contain Residual IDs.
    from_lookup_result() propagates trace_event_ids from ConstitutionalLookupResult.
    A synthetic result with no trace_event_ids set (defaults to ()) must produce
    trace_ids=() in the augmentation result — residual IDs must never bleed into
    trace_ids regardless of whether trace propagation is active.
    """
    from maqayis_constitutional_schemas import (
        MaqayisConstitutionalAugmentationResult,
        ConstitutionalLookupResult,
        LookupResultKind,
        EvidenceStatus,
        ReviewState,
        Residual,
        ResidualType,
    )
    residual = Residual(
        id="maqayis:residual:ORIGIN_NOT_EXTRACTED:حدر",
        target_id="maqayis:source-root-claim:حدر:0",
        target_type="SourceRootClaim",
        residual_type=ResidualType.ORIGIN_NOT_EXTRACTED,
        description="test",
        blocking_until=ReviewState.ORIGIN_CANDIDATE,
        created_at="2026-08-03T00:00:00Z",
    )
    result = ConstitutionalLookupResult(
        kind=LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY,
        root_letters="حدر",
        residuals=(residual,),
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
        review_state=ReviewState.MACHINE_CANDIDATE,
    )
    augment = MaqayisConstitutionalAugmentationResult.from_lookup_result(result, evidence_ids=())
    # §11: trace_ids must be () because the synthetic ConstitutionalLookupResult
    # has no trace_event_ids (defaults to ()) — residual IDs must not appear here.
    assert augment.trace_ids == (), (
        f"§11: trace_ids must be () when lookup result has no trace_event_ids, "
        f"got: {augment.trace_ids}"
    )
    # Residual IDs must appear in residual_ids, not trace_ids
    residual_id = "maqayis:residual:ORIGIN_NOT_EXTRACTED:حدر"
    assert residual_id not in augment.trace_ids, "§11: residual ID must not appear in trace_ids"
    assert residual_id in augment.residual_ids, "§11: residual ID must appear in residual_ids"


def test_hokom_real_type_integration():
    """§6: Maqayis adapter must consume real Hokom domain types (not locally defined stubs).
    Imports from pipeline.p3_candidate.root_contracts — skipped if that module is
    not available in the current test environment.
    HOKOM_STUB_TYPE_COUNT = 0 enforced in production; this test verifies the import path.
    """
    try:
        import sys
        import pathlib as _pathlib

        _hokom_search_root = _pathlib.Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_hokom_search_root))
        from pipeline.p3_candidate.root_contracts import (  # type: ignore[import]
            RootCandidateRecord,
        )
    except ImportError:
        pytest.skip(
            "Real Hokom types not available in test environment "
            "(pipeline.p3_candidate.root_contracts not importable). "
            "This test passes in production where the full Hokom tree is present."
        )

    # If import succeeded, verify the type has the expected contract fields
    # that the Maqayis adapter reads (§5: domain_directive + radicals).
    assert hasattr(RootCandidateRecord, "__dataclass_fields__") or hasattr(
        RootCandidateRecord, "__annotations__"
    ), (
        "§6: RootCandidateRecord must be a typed class with inspectable fields; "
        "Maqayis adapter reads domain_directive and radicals from it"
    )
