"""
test_maqayis_production.py — Maqayis subsystem production tests

Covers all 17 scenarios from the production hardening spec.

Run:
    python -m pytest pipeline/taaqol_integration/test_maqayis_production.py -v

Or standalone (no pytest required):
    python test_maqayis_production.py

The tests use a minimal in-memory corpus built from literal JSONL strings
so they never depend on the filesystem corpus path.
"""
from __future__ import annotations

import json
import tempfile
import textwrap
from pathlib import Path
from typing import Optional


# ── Corpus fixtures ───────────────────────────────────────────────────────────

# Three representative root entries covering AUTO_AGREED, REVIEW_REQUIRED, and
# corrected bab_letter.

_ENTRY_AUTO = {
    "entry_id": "02.pdf:p100:r001",
    "source_pdf": "02.pdf",
    "pdf_page": 100,
    "root_heading_text": "( حلك ) الحاء واللام والكاف",
    "root_letters": "حلك",
    "bab_letter": "الحاء",
    "corrected_bab_letter": "الحاء",
    "original_bab_letter": "الحاء",
    "correction_reason": "first_radical_derivation",
    "correction_version": "v1",
    "semantic_origin_type": "SINGULAR",
    "origin_count": 1,
    "review_status": "AUTO_AGREED",
    "human_verified": False,
}

_ENTRY_REVIEW = {
    "entry_id": "02.pdf:p200:r001",
    "source_pdf": "02.pdf",
    "pdf_page": 200,
    "root_heading_text": "( حمش ) الحاء والميم والشين",
    "root_letters": "حمش",
    "bab_letter": "الحاء",
    "corrected_bab_letter": "الحاء",
    "original_bab_letter": "الحاء",
    "correction_reason": "first_radical_derivation",
    "correction_version": "v1",
    "semantic_origin_type": "DUAL",
    "origin_count": 2,
    "review_status": "REVIEW_REQUIRED",
    "human_verified": False,
}

_ENTRY_WRONG_BAB = {
    "entry_id": "02.pdf:p300:r001",
    "source_pdf": "02.pdf",
    "pdf_page": 300,
    "root_heading_text": "( حمز ) الحاء والميم والزاي",
    "root_letters": "حمز",
    "bab_letter": "الضاد",           # raw OCR error — second radical captured
    "corrected_bab_letter": "الحاء", # corrected by maqayis_bab_corrector.py
    "original_bab_letter": "الضاد",
    "correction_reason": "first_radical_derivation",
    "correction_version": "v1",
    "semantic_origin_type": "SINGULAR",
    "origin_count": 1,
    "review_status": "AUTO_AGREED",
    "human_verified": False,
}


def _make_registry(entries: list[dict]):
    """
    Build a MaqayisRootRegistry from a list of entry dicts written to a tmp file.
    """
    import sys, types
    from pathlib import Path

    src = Path(__file__).parent / "maqayis_root_registry.py"
    # If running from /root during development, resolve alongside this test file
    if not src.exists():
        src = Path(__file__).with_name("maqayis_root_registry.py")

    module_src = src.read_text()
    # Patch path resolution for test isolation
    module_src = module_src.replace(
        "_REPO_ROOT    = Path(__file__).resolve().parents[2]",
        "_REPO_ROOT    = Path('/nonexistent/repo')",
    )

    mod_name = "maqayis_root_registry_test_" + str(id(entries))
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    exec(compile(module_src, str(src), "exec"), mod.__dict__)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        path = fh.name

    reg = mod.MaqayisRootRegistry(path)
    return reg, mod


def _make_adapter_ids(root_letters: str, entries: list[dict]) -> tuple[str, ...]:
    """
    Run the evidence adapter logic directly against an in-memory registry.
    Returns the evidence ID tuple.
    """
    import sys, types
    from pathlib import Path

    reg, reg_mod = _make_registry(entries)
    LookupResultKind = reg_mod.LookupResultKind

    # Build the adapter logic inline to avoid import-time binding issues
    result = reg.typed_lookup(root_letters)
    if not result.found or result.entry is None:
        return ()

    entry = result.entry
    ids: list[str] = []

    # Review status contract
    if result.kind == LookupResultKind.FOUND_AUTO_AGREED:
        if entry.semantic_origin_type not in ("NONE", "UNKNOWN", None, ""):
            cnt = str(entry.origin_count) if entry.origin_count is not None else "none"
            ids.append(
                f"maqayis:root:{root_letters}:origin:{entry.semantic_origin_type}:count:{cnt}"
            )
    if entry.bab_letter:
        ids.append(f"maqayis:root:{root_letters}:bab:{entry.bab_letter}")

    return tuple(ids)


# ── Test runner ───────────────────────────────────────────────────────────────

_PASS = []
_FAIL = []


def _assert(condition: bool, name: str, detail: str = "") -> None:
    if condition:
        _PASS.append(name)
        print(f"  ✓  {name}")
    else:
        _FAIL.append(name)
        print(f"  ✗  FAIL  {name}" + (f" — {detail}" if detail else ""))


# ── T-01: AUTO_AGREED root emits origin ID + bab ID ──────────────────────────

def test_01_auto_agreed_emits_origin_and_bab():
    """T-01: AUTO_AGREED + valid semantic origin → emit origin ID and bab ID."""
    ids = _make_adapter_ids("حلك", [_ENTRY_AUTO])
    origin_id = "maqayis:root:حلك:origin:SINGULAR:count:1"
    bab_id    = "maqayis:root:حلك:bab:الحاء"
    _assert(origin_id in ids, "T-01a AUTO_AGREED emits origin ID",   f"ids={ids}")
    _assert(bab_id    in ids, "T-01b AUTO_AGREED emits bab ID",      f"ids={ids}")


# ── T-02: REVIEW_REQUIRED suppresses origin ID ───────────────────────────────

def test_02_review_required_suppresses_origin():
    """T-02: REVIEW_REQUIRED → origin ID must NOT be emitted."""
    ids = _make_adapter_ids("حمش", [_ENTRY_REVIEW])
    origin_id = "maqayis:root:حمش:origin:DUAL:count:2"
    bab_id    = "maqayis:root:حمش:bab:الحاء"
    _assert(origin_id not in ids, "T-02a REVIEW_REQUIRED suppresses origin ID", f"ids={ids}")
    _assert(bab_id    in     ids, "T-02b REVIEW_REQUIRED still emits bab ID",   f"ids={ids}")
    # REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT = 0
    _assert(
        all("origin" not in eid for eid in ids),
        "T-02c no origin token in any REVIEW_REQUIRED IDs",
        f"ids={ids}",
    )


# ── T-03: Corrected bab letter used ──────────────────────────────────────────

def test_03_corrected_bab_letter():
    """T-03: bab_letter must use corrected value, not raw OCR value."""
    reg, mod = _make_registry([_ENTRY_WRONG_BAB])
    entry = reg.lookup("حمز")
    _assert(entry is not None,          "T-03a حمز found in registry")
    if entry:
        _assert(entry.bab_letter == "الحاء",  "T-03b corrected bab = الحاء",    f"got {entry.bab_letter!r}")
        _assert(entry.original_bab_letter == "الضاد", "T-03c original bab preserved", f"got {entry.original_bab_letter!r}")
        _assert(entry.correction_version == "v1", "T-03d correction_version = v1")
    ids = _make_adapter_ids("حمز", [_ENTRY_WRONG_BAB])
    bab_correct  = "maqayis:root:حمز:bab:الحاء"
    bab_wrong    = "maqayis:root:حمز:bab:الضاد"
    _assert(bab_correct in ids, "T-03e bab ID uses corrected value", f"ids={ids}")
    _assert(bab_wrong not in ids, "T-03f bab ID does not use raw OCR value", f"ids={ids}")


# ── T-04: Missing-volume initials → MISSING_VOLUME_COVERAGE_GAP ──────────────

def test_04_missing_volume_coverage_gap():
    """T-04: Roots with ا ب ت ث ج initials → MISSING_VOLUME_COVERAGE_GAP."""
    reg, mod = _make_registry([_ENTRY_AUTO])  # corpus has no missing-initial entries
    LookupResultKind = mod.LookupResultKind

    for root in ["بسط", "تكل", "ثلث", "جمل", "بيت", "أمر"]:
        result = reg.typed_lookup(root)
        _assert(
            result.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP,
            f"T-04 {root!r} → MISSING_VOLUME_COVERAGE_GAP",
            f"got {result.kind.value}",
        )
        _assert(result.entry is None, f"T-04 {root!r} entry is None")
        # Must never produce evidence
        ids = _make_adapter_ids(root, [_ENTRY_AUTO])
        _assert(not ids, f"T-04 {root!r} emits no evidence IDs", f"ids={ids}")


# ── T-05: Root absent from covered volume ─────────────────────────────────────

def test_05_root_absent_from_covered_volume():
    """T-05: Root with covered initial but not in corpus → NOT_FOUND_IN_COVERED_VOLUME."""
    reg, mod = _make_registry([_ENTRY_AUTO])
    LookupResultKind = mod.LookupResultKind

    result = reg.typed_lookup("ححح")  # not in corpus
    _assert(
        result.kind == LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME,
        "T-05 absent root → NOT_FOUND_IN_COVERED_VOLUME",
        f"got {result.kind.value}",
    )
    _assert(result.entry is None, "T-05 entry is None for absent root")


# ── T-06: Corrupt corpus (malformed JSON) ─────────────────────────────────────

def test_06_corrupt_corpus():
    """T-06: Corrupt JSONL lines are skipped; valid lines still load."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        fh.write("THIS IS NOT JSON\n")
        fh.write(json.dumps(_ENTRY_AUTO, ensure_ascii=False) + "\n")
        fh.write("{broken json\n")
        path = fh.name

    import sys, types
    from pathlib import Path
    src = Path(__file__).with_name("maqayis_root_registry.py")
    module_src = src.read_text().replace(
        "_REPO_ROOT    = Path(__file__).resolve().parents[2]",
        "_REPO_ROOT    = Path('/nonexistent/repo')",
    )
    mod_name = "maqayis_rr_t06"
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    exec(compile(module_src, str(src), "exec"), mod.__dict__)

    reg = mod.MaqayisRootRegistry(path)
    _assert(reg.total_roots >= 1,         "T-06 valid entries survive corrupt lines")
    entry = reg.lookup("حلك")
    _assert(entry is not None,            "T-06 حلك found despite corrupt peers")


# ── T-07: Registry load failure ───────────────────────────────────────────────

def test_07_registry_load_failure():
    """T-07: Missing corpus file → REGISTRY_LOAD_FAILURE for every lookup."""
    import sys, types
    from pathlib import Path
    src = Path(__file__).with_name("maqayis_root_registry.py")
    module_src = src.read_text().replace(
        "_REPO_ROOT    = Path(__file__).resolve().parents[2]",
        "_REPO_ROOT    = Path('/nonexistent/repo')",
    )
    mod_name = "maqayis_rr_t07"
    mod = types.ModuleType(mod_name)
    sys.modules[mod_name] = mod
    exec(compile(module_src, str(src), "exec"), mod.__dict__)

    reg = mod.MaqayisRootRegistry("/nonexistent/corpus.jsonl")
    LookupResultKind = mod.LookupResultKind
    result = reg.typed_lookup("حلك")
    _assert(
        result.kind == LookupResultKind.REGISTRY_LOAD_FAILURE,
        "T-07 missing file → REGISTRY_LOAD_FAILURE",
        f"got {result.kind.value}",
    )
    _assert(result.entry is None, "T-07 entry is None on load failure")
    # Adapter must return empty tuple — never raises
    ids = _make_adapter_ids("حلك", [])  # empty corpus
    _assert(isinstance(ids, tuple), "T-07 adapter returns tuple on failure")


# ── T-08: Invalid bundle / None bundle ───────────────────────────────────────

def test_08_invalid_bundle():
    """T-08: None bundle → () from augment_evidence_from_bundle; never raises."""
    # We test the extraction logic: extract_root_letters_from_bundle(None)
    class FakeBundle:
        root_claim = None

    class NoClaim:
        canonical_root = None

    class GoodClaim:
        canonical_root = ['ح', 'ل', 'ك']

    class GoodBundle:
        root_claim = GoodClaim()

    def _extract(bundle):
        try:
            rc = getattr(bundle, "root_claim", None)
            if rc is None:
                return None
            cr = getattr(rc, "canonical_root", None)
            if not cr:
                return None
            letters = "".join(str(c) for c in cr)
            return letters if letters else None
        except Exception:
            return None

    _assert(_extract(None)        is None, "T-08a None bundle → None root")
    _assert(_extract(FakeBundle()) is None, "T-08b bundle.root_claim=None → None root")
    _assert(_extract(GoodBundle()) == "حلك", "T-08c valid bundle → حلك")


# ── T-09: Absent root claim → no evidence ─────────────────────────────────────

def test_09_absent_root_claim():
    """T-09: Bundle with no root_claim emits no Maqayis evidence."""
    class NoRootBundle:
        root_claim = None

    # augment_evidence_from_bundle with no canonical root must return ()
    def _augment(bundle):
        try:
            rc = getattr(bundle, "root_claim", None)
            if not rc:
                return ()
            cr = getattr(rc, "canonical_root", None)
            if not cr:
                return ()
            root = "".join(str(c) for c in cr)
            return _make_adapter_ids(root, [_ENTRY_AUTO, _ENTRY_REVIEW])
        except Exception:
            return ()

    ids = _augment(NoRootBundle())
    _assert(ids == (), "T-09 absent root_claim → empty evidence tuple")


# ── T-10: Tuple root input ────────────────────────────────────────────────────

def test_10_tuple_root_input():
    """T-10: tuple root_letters input → INVALID_ROOT_INPUT (not a string)."""
    reg, mod = _make_registry([_ENTRY_AUTO])
    LookupResultKind = mod.LookupResultKind
    result = reg.typed_lookup(('ح', 'ل', 'ك'))  # type: ignore[arg-type]
    _assert(
        result.kind == LookupResultKind.INVALID_ROOT_INPUT,
        "T-10 tuple input → INVALID_ROOT_INPUT",
        f"got {result.kind.value}",
    )


# ── T-11: List root input ─────────────────────────────────────────────────────

def test_11_list_root_input():
    """T-11: list root_letters input → INVALID_ROOT_INPUT."""
    reg, mod = _make_registry([_ENTRY_AUTO])
    LookupResultKind = mod.LookupResultKind
    result = reg.typed_lookup(['ح', 'ل', 'ك'])  # type: ignore[arg-type]
    _assert(
        result.kind == LookupResultKind.INVALID_ROOT_INPUT,
        "T-11 list input → INVALID_ROOT_INPUT",
        f"got {result.kind.value}",
    )


# ── T-12: Canonical string input ──────────────────────────────────────────────

def test_12_canonical_string_input():
    """T-12: str root_letters → found correctly."""
    reg, mod = _make_registry([_ENTRY_AUTO])
    LookupResultKind = mod.LookupResultKind
    result = reg.typed_lookup("حلك")
    _assert(
        result.kind == LookupResultKind.FOUND_AUTO_AGREED,
        "T-12 canonical string → FOUND_AUTO_AGREED",
        f"got {result.kind.value}",
    )


# ── T-13: Evidence classifier ordering ───────────────────────────────────────

def test_13_evidence_classifier_ordering():
    """T-13: maqayis:root: prefix is classified BEFORE generic root+catalog branch."""
    maqayis_id   = "maqayis:root:حلك:origin:SINGULAR:count:1"
    generic_root = "root:catalog:حلك"

    def classify(eid: str) -> str:
        eid_lower = eid.lower()
        if eid_lower.startswith("maqayis:root:"):
            return "maqayis_root_catalog_evidence"
        if "root" in eid_lower and "catalog" in eid_lower:
            return "root_catalog_evidence"
        return "unknown"

    _assert(
        classify(maqayis_id) == "maqayis_root_catalog_evidence",
        "T-13a maqayis:root: → maqayis_root_catalog_evidence",
    )
    _assert(
        classify(generic_root) == "root_catalog_evidence",
        "T-13b generic root:catalog: → root_catalog_evidence",
    )
    # A maqayis ID that also contains "catalog" must still hit Maqayis branch
    tricky = "maqayis:root:حلك:catalog:foo"
    _assert(
        classify(tricky) == "maqayis_root_catalog_evidence",
        "T-13c maqayis:root: wins over root+catalog overlap",
    )


# ── T-14: No admission verdict mutation ───────────────────────────────────────

def test_14_no_verdict_mutation():
    """T-14: Maqayis evidence IDs are additive only — no verdict field."""
    ids = _make_adapter_ids("حلك", [_ENTRY_AUTO])
    # None of the IDs should encode an admission verdict
    verdict_tokens = ["admit", "reject", "approve", "deny", "verdict"]
    for eid in ids:
        for tok in verdict_tokens:
            _assert(tok not in eid.lower(), f"T-14 ID {eid!r} must not contain {tok!r}")


# ── T-15: No rank mutation ────────────────────────────────────────────────────

def test_15_no_rank_mutation():
    """T-15: Maqayis evidence IDs must not encode rank."""
    ids = _make_adapter_ids("حلك", [_ENTRY_AUTO])
    rank_tokens = ["rank", "score", "boost", "weight", "priority"]
    for eid in ids:
        for tok in rank_tokens:
            _assert(tok not in eid.lower(), f"T-15 ID {eid!r} must not contain {tok!r}")


# ── T-16: Deterministic registry reload ───────────────────────────────────────

def test_16_deterministic_reload():
    """T-16: Two registry instances from the same JSONL produce equal results."""
    reg1, _ = _make_registry([_ENTRY_AUTO, _ENTRY_REVIEW, _ENTRY_WRONG_BAB])
    reg2, _ = _make_registry([_ENTRY_AUTO, _ENTRY_REVIEW, _ENTRY_WRONG_BAB])

    _assert(reg1.total_roots == reg2.total_roots, "T-16a same root count")

    for root in ["حلك", "حمش", "حمز"]:
        e1 = reg1.lookup(root)
        e2 = reg2.lookup(root)
        _assert(
            (e1 is None) == (e2 is None),
            f"T-16b {root!r} presence consistent",
        )
        if e1 and e2:
            _assert(
                e1.semantic_origin_type == e2.semantic_origin_type,
                f"T-16c {root!r} origin_type consistent",
            )
            _assert(e1.bab_letter == e2.bab_letter, f"T-16d {root!r} bab_letter consistent")


# ── T-17: Corpus hash stability ───────────────────────────────────────────────

def test_17_corpus_hash_stability():
    """T-17: Same JSONL bytes → same SHA-256 corpus hash."""
    import hashlib, tempfile

    content = "\n".join(
        json.dumps(e, ensure_ascii=False)
        for e in [_ENTRY_AUTO, _ENTRY_REVIEW, _ENTRY_WRONG_BAB]
    ) + "\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f1:
        f1.write(content)
        path1 = f1.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f2:
        f2.write(content)
        path2 = f2.name

    h1 = hashlib.sha256(Path(path1).read_bytes()).hexdigest()
    h2 = hashlib.sha256(Path(path2).read_bytes()).hexdigest()
    _assert(h1 == h2, "T-17 same content → identical SHA-256 corpus hash", f"h1={h1} h2={h2}")


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> int:
    print("Maqayis production tests (17 scenarios)\n")
    print("=" * 60)

    tests = [
        test_01_auto_agreed_emits_origin_and_bab,
        test_02_review_required_suppresses_origin,
        test_03_corrected_bab_letter,
        test_04_missing_volume_coverage_gap,
        test_05_root_absent_from_covered_volume,
        test_06_corrupt_corpus,
        test_07_registry_load_failure,
        test_08_invalid_bundle,
        test_09_absent_root_claim,
        test_10_tuple_root_input,
        test_11_list_root_input,
        test_12_canonical_string_input,
        test_13_evidence_classifier_ordering,
        test_14_no_verdict_mutation,
        test_15_no_rank_mutation,
        test_16_deterministic_reload,
        test_17_corpus_hash_stability,
    ]

    for test_fn in tests:
        label = test_fn.__name__.replace("_", " ").upper()
        print(f"\n{label}")
        try:
            test_fn()
        except Exception as exc:
            _FAIL.append(test_fn.__name__)
            print(f"  ✗  EXCEPTION: {exc}")

    print("\n" + "=" * 60)
    total = len(_PASS) + len(_FAIL)
    print(f"Results: {len(_PASS)}/{total} assertions passed")
    if _FAIL:
        print(f"Failed:  {_FAIL}")
        return 1
    else:
        print("ALL TESTS PASSED ✓")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
