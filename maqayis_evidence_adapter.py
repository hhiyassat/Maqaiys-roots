"""
maqayis_evidence_adapter.py — Taaqol integration layer
Maqayis OCR v2  (production-hardened)

Enriches the Taaqol EvidenceContract with Ibn Faris lexical evidence
when a Hokom claim bundle carries a known root.

Evidence ID format
──────────────────
    maqayis:root:{root_letters}:origin:{origin_type}:count:{n|none}
    maqayis:root:{root_letters}:bab:{bab_letter}

These IDs are recognised by evidence_adapter._classify_evidence_id as
'maqayis_root_catalog_evidence'.

Review Status Contract
──────────────────────
The contract controls which evidence IDs are emitted:

    AUTO_AGREED + valid semantic origin
        → emit origin ID  (maqayis:root:…:origin:…:count:…)
        → emit bab ID     (maqayis:root:…:bab:…)  if corrected bab valid

    REVIEW_REQUIRED
        → do NOT emit origin ID  ← production safety contract
        → emit bab ID ONLY if corrected bab is valid and non-empty
        (REVIEW_REQUIRED is not evidence of absence; NONE review_status
         is NOT_EXTRACTED_OR_NOT_VERIFIED — never a negative semantic claim)

    MISSING_VOLUME_COVERAGE_GAP | NOT_FOUND | LOAD_FAILURE | INVALID_INPUT
        → emit nothing

Accounting Counters (enforced by this module)
─────────────────────────────────────────────
    REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT  = 0  (always)
    NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT = 0 (always)

Fail-Open Contract
──────────────────
Every function catches all exceptions.  A missing or corrupt Maqayis corpus
must never block Taaqol admission.

Stage-0 Integration Constraints
────────────────────────────────
Maqayis evidence IDs are supplementary only.  They MUST NOT:
• approve admission independently
• increase token rank
• suppress residual codes
• assert roots not licensed by Hokom's morphological chain
• infer sentence relation, maqam, produce Ifadah/Hukm/Manat/Tanzil/AnswerAudit
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .maqayis_root_registry import (
    typed_lookup,
    LookupResult,
    LookupResultKind,
    MaqayisRootEntry,
)

if TYPE_CHECKING:
    from .provider_models import HokomLinguisticClaimBundle


# ── Evidence ID builder ───────────────────────────────────────────────────────

def get_maqayis_evidence_ids(root_letters: str) -> tuple[str, ...]:
    """
    Return Maqayis evidence IDs for *root_letters* per the review status contract.

    Parameters
    ──────────
    root_letters : str
        Undiacritized Arabic consonants, e.g. "حد", "كتب", "دين".

    Returns
    ───────
    Tuple of evidence ID strings (may be empty).  Never raises.

    Review Status Contract
    ──────────────────────
    AUTO_AGREED   → origin ID + bab ID (if bab valid)
    REVIEW_REQUIRED → bab ID only (origin ID suppressed — see module docstring)
    All other LookupResultKinds → empty tuple
    """
    if not root_letters:
        return ()
    try:
        result = typed_lookup(root_letters)
        return _ids_from_result(root_letters, result)
    except Exception:
        return ()


def _ids_from_result(root: str, result: LookupResult) -> tuple[str, ...]:
    """
    Build evidence IDs from a typed LookupResult, enforcing the review status contract.

    Called only from get_maqayis_evidence_ids — never directly.
    """
    # Non-found kinds → no evidence
    if not result.found:
        return ()

    entry = result.entry
    if entry is None:
        return ()

    ids: list[str] = []

    # ── Origin ID — AUTO_AGREED only ──────────────────────────────────────────
    # REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT = 0 is maintained here.
    if result.auto_agreed:
        if entry.semantic_origin_type not in ("NONE", "UNKNOWN", None, ""):
            cnt_str = str(entry.origin_count) if entry.origin_count is not None else "none"
            ids.append(
                f"maqayis:root:{root}:origin:{entry.semantic_origin_type}:count:{cnt_str}"
            )

    # ── Bab ID — any review status if corrected bab is valid ─────────────────
    # bab_letter is the corrected value (from maqayis_bab_corrector.py or derived).
    if entry.bab_letter:
        ids.append(f"maqayis:root:{root}:bab:{entry.bab_letter}")

    return tuple(ids)


# ── Root extraction from bundle ───────────────────────────────────────────────

def extract_root_letters_from_bundle(bundle: "HokomLinguisticClaimBundle") -> Optional[str]:
    """
    Extract undiacritized root letters from a HokomLinguisticClaimBundle.

    Uses bundle.root_claim.canonical_root (a tuple of radical objects).
    Returns None if:
    • root_claim is None (no root identified by Hokom)
    • canonical_root is None/empty (root deferred or blocked)
    • any other exception (fail-open)

    This function does NOT accept raw tokens → Maqayis root guessing.
    Root extraction is always from Hokom's licensed canonical_root only.
    """
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


# ── Bundle-level convenience ──────────────────────────────────────────────────

def augment_evidence_from_bundle(
    bundle: "HokomLinguisticClaimBundle",
) -> tuple[str, ...]:
    """
    Extract root letters from the bundle and return Maqayis evidence IDs.

    Combines extract_root_letters_from_bundle + get_maqayis_evidence_ids.
    Returns () on any failure — never raises.

    The returned IDs enforce the full review status contract:
    • AUTO_AGREED roots: origin ID + bab ID
    • REVIEW_REQUIRED roots: bab ID only
    • All other cases: empty tuple

    These IDs are supplementary evidence — the function never modifies the
    bundle, admission verdict, rank, residuals, or any Taaqol output field.
    """
    try:
        root = extract_root_letters_from_bundle(bundle)
        if not root:
            return ()
        return get_maqayis_evidence_ids(root)
    except Exception:
        return ()


# ── Diagnostic helper (not used in production pipeline) ──────────────────────

def explain_lookup(root_letters: str) -> dict:
    """
    Return a diagnostic dict explaining the lookup outcome for *root_letters*.

    Intended for debugging and review tooling — not called by the pipeline.
    """
    try:
        from .maqayis_root_registry import typed_lookup as _tl
        result = _tl(root_letters)
    except Exception as exc:
        return {"root": root_letters, "error": str(exc)}

    out: dict = {
        "root":       root_letters,
        "kind":       result.kind.value,
        "evidence_ids": list(get_maqayis_evidence_ids(root_letters)),
    }
    if result.entry:
        e = result.entry
        out.update({
            "review_status":         e.review_status,
            "semantic_origin_type":  e.semantic_origin_type,
            "origin_count":          e.origin_count,
            "bab_letter":            e.bab_letter,
            "original_bab_letter":   e.original_bab_letter,
            "correction_version":    e.correction_version,
            "source_pdfs":           list(e.source_pdfs),
        })
    return out
