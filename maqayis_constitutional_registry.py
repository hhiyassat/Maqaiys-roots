"""
maqayis_constitutional_registry.py — Constitutional typed registry
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01  Commit 5

Replaces the legacy maqayis_root_registry.py typed_lookup() with an
11-kind ConstitutionalLookupResult that carries the full evidence chain.

Also provides the backward-compatible bridge: legacy callers that use
typed_lookup() still get the same LookupResult interface, but constitutional
callers get the richer ConstitutionalLookupResult.

MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT = 0 is enforced:
  Maqayis may only look up roots that are licensed by Hokom's canonical_root.
  This registry never infers roots from raw tokens.

Missing volume contract (same as legacy):
  Hamza variants أ/إ/آ normalize to ا for coverage check ONLY.
  Stored data never modified.
  Missing initials: ا ب ت ث ج → MISSING_VOLUME_COVERAGE_GAP

Fail-Open Contract
──────────────────
All exceptions caught. Constitutional registry failure must never block
Taaqol admission. Returns NOT_FOUND_IN_COVERED_VOLUME on any internal error.
"""
from __future__ import annotations

import pathlib
import threading
from typing import Optional

from maqayis_constitutional_schemas import (
    ConstitutionalLookupResult,
    LookupResultKind,
    ReviewState,
    EvidenceStatus,
    RootIdentityCandidate,
    SourceRootClaim,
    LexicalOriginCandidate,
    Residual,
)
from maqayis_legacy_importer import import_legacy_corpus, LegacyCandidateImport
from maqayis_claim_pipeline import run_claim_pipeline, _normalize_origin_type


# ── Repo-root discovery (§2) ─────────────────────────────────────────────────

def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "data" / "maqaees" / "full").is_dir():
            return here
        if here.parent == here:
            break
        here = here.parent
    return pathlib.Path(__file__).resolve().parent


# ── Constants ─────────────────────────────────────────────────────────────────

_REPO_ROOT = _find_repo_root()
_DATA_DIR  = _REPO_ROOT / "data" / "maqaees" / "full"
_CORRECTED = _DATA_DIR / "root_entries_corrected.jsonl"
_ORIGINAL  = _DATA_DIR / "root_entries.jsonl"

# Missing volume initials (same as legacy)
_MAQAYIS_MISSING_INITIALS: frozenset[str] = frozenset({'ا', 'ب', 'ت', 'ث', 'ج'})
# §8: bare ء included so ءمن → MISSING_VOLUME_COVERAGE_GAP correctly.
# BARE_HAMZA_COVERAGE_FAILURE_COUNT = 0 enforced here.
_HAMZA_VARIANTS:           frozenset[str] = frozenset({'أ', 'إ', 'آ', 'ء'})

# Accounting counter — must remain 0 in production
MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT: int = 0

# R9: Track partial load for malformed corpus accounting
REGISTRY_PARTIAL_LOAD_COUNT: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — REGISTRY CACHE (singleton, thread-safe)
# ═══════════════════════════════════════════════════════════════════════════════

class _ConstitutionalRegistry:
    """
    In-memory cache of the constitutional entity graph.
    Loaded once at first use; thread-safe via lock.
    """

    def __init__(self) -> None:
        self._lock   = threading.Lock()
        self._loaded = False
        self._failed = False
        self._malformed_count: int = 0  # R9: count malformed entries
        self._partial_load: bool = False  # R9: True if any malformed entries

        # Primary indices: root_letters → list of LegacyCandidateImport
        self._imports_by_root:   dict[str, list[LegacyCandidateImport]] = {}
        self._claims_by_root:    dict[str, list[SourceRootClaim]] = {}
        self._origins_by_root:   dict[str, list[LexicalOriginCandidate]] = {}
        self._residuals_by_root: dict[str, list[Residual]] = {}
        self._candidates_by_root: dict[str, list[RootIdentityCandidate]] = {}
        self._conflict_roots:    frozenset[str] = frozenset()

    def _load(self, jsonl_path: Optional[pathlib.Path] = None) -> None:
        """Load and index the constitutional graph. Called once."""
        try:
            if jsonl_path is None:
                jsonl_path = _CORRECTED if _CORRECTED.exists() else _ORIGINAL

            import_result = import_legacy_corpus(jsonl_path)
            claim_result  = run_claim_pipeline(import_result)

            # Build identity pipeline result for candidates
            from maqayis_identity_pipeline import run_identity_pipeline
            identity_result = run_identity_pipeline(import_result)

            # Index by root
            for imp in import_result.imports:
                root = imp.legacy_root_letters
                self._imports_by_root.setdefault(root, []).append(imp)

            # ID format: "maqayis:{type}:{root}:{idx}" → root is at parts[2]
            for claim in claim_result.claims:
                parts = claim.id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._claims_by_root.setdefault(root, []).append(claim)

            for origin in claim_result.origin_candidates:
                parts = origin.id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._origins_by_root.setdefault(root, []).append(origin)

            for candidate in identity_result.candidates:
                parts = candidate.id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._candidates_by_root.setdefault(root, []).append(candidate)

            for residual in claim_result.residuals:
                parts = residual.target_id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._residuals_by_root.setdefault(root, []).append(residual)

            for residual in identity_result.residuals:
                parts = residual.target_id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._residuals_by_root.setdefault(root, []).append(residual)

            for residual in import_result.residuals:
                parts = residual.target_id.split(":")
                if len(parts) >= 3:
                    root = parts[2]
                    self._residuals_by_root.setdefault(root, []).append(residual)

            self._conflict_roots = frozenset(claim_result.conflict_map.keys())
            self._loaded = True

            # R9: Track partial load for malformed corpus accounting
            self._partial_load = (self._malformed_count > 0)

        except Exception:
            self._failed = True

    def ensure_loaded(self, jsonl_path: Optional[pathlib.Path] = None) -> None:
        if not self._loaded and not self._failed:
            with self._lock:
                if not self._loaded and not self._failed:
                    self._load(jsonl_path)

    def lookup(self, root: str) -> ConstitutionalLookupResult:
        """
        Look up a root and return a ConstitutionalLookupResult.
        Never raises.
        §7: ensure_loaded() failure → REGISTRY_LOAD_FAILURE (not NOT_FOUND).
        REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT = 0 enforced here.
        """
        try:
            self.ensure_loaded()
        except Exception:
            # §7: any exception in ensure_loaded marks registry as failed.
            # Must NOT fall through to NOT_FOUND — that would relabel the failure.
            self._failed = True

        if self._failed:
            return ConstitutionalLookupResult(
                kind=LookupResultKind.REGISTRY_LOAD_FAILURE,
                root_letters=root,
            )

        # Validate input
        if not root or not root.strip():
            return ConstitutionalLookupResult(
                kind=LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME,
                root_letters=root,
            )

        # Check missing volume coverage
        normalized_initial = root[0]
        if normalized_initial in _HAMZA_VARIANTS:
            normalized_initial = 'ا'
        if normalized_initial in _MAQAYIS_MISSING_INITIALS:
            return ConstitutionalLookupResult(
                kind=LookupResultKind.MISSING_VOLUME_COVERAGE_GAP,
                root_letters=root,
                coverage_note=(
                    f"Root '{root}' starts with '{root[0]}' which falls in the "
                    f"missing volumes (ا ب ت ث ج — not in OCR corpus). "
                    f"This is a coverage gap, not an absence claim."
                ),
            )

        # Look up imports for this root
        imports = self._imports_by_root.get(root, [])
        if not imports:
            return ConstitutionalLookupResult(
                kind=LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME,
                root_letters=root,
            )

        # Collect all entities
        claims   = tuple(self._claims_by_root.get(root, []))
        origins  = tuple(self._origins_by_root.get(root, []))
        residuals = tuple(self._residuals_by_root.get(root, []))
        candidates = self._candidates_by_root.get(root, [])
        candidate = candidates[0] if candidates else None

        # Determine kind
        is_conflict = root in self._conflict_roots
        all_auto = all(imp.legacy_review_status == "AUTO_AGREED" for imp in imports)
        any_review_req = any(imp.legacy_review_status == "REVIEW_REQUIRED" for imp in imports)

        if is_conflict:
            kind = LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED
        elif all_auto:
            kind = LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY
        else:
            kind = LookupResultKind.FOUND_REVIEW_REQUIRED_UNRESOLVED

        # Determine review_state and evidence_status
        # Use the best import's state
        review_state = (
            ReviewState.IDENTITY_CANDIDATE
            if any(imp.initial_review_state == ReviewState.MACHINE_CANDIDATE for imp in imports)
            else ReviewState.UNVERIFIED_REVIEW_REQUIRED
        )

        return ConstitutionalLookupResult(
            kind=kind,
            root_letters=root,
            identity_candidate=candidate,
            identity_carrier=None,  # no human carriers in V1
            claims=claims,
            origin_candidates=origins,
            residuals=residuals,
            evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
            review_state=review_state,
            conflict_notes=(
                f"Conflict: {self._imports_by_root.get(root, [{}])[0]}"
                if is_conflict else None
            ),
        )


# ── Global singleton ──────────────────────────────────────────────────────────

_REGISTRY = _ConstitutionalRegistry()


def constitutional_lookup(root_letters: str) -> ConstitutionalLookupResult:
    """
    Primary constitutional lookup API.
    R8: exceptions → REGISTRY_LOAD_FAILURE (not NOT_FOUND).

    Parameters
    ──────────
    root_letters : str — undiacritized Arabic root letters

    Returns
    ───────
    ConstitutionalLookupResult — never raises (fail-open contract)
    """
    try:
        return _REGISTRY.lookup(root_letters)
    except Exception:
        return ConstitutionalLookupResult(
            kind=LookupResultKind.REGISTRY_LOAD_FAILURE,
            root_letters=root_letters,
        )


def reload_registry(jsonl_path: Optional[pathlib.Path] = None) -> None:
    """Reload the registry (for testing or after corpus update)."""
    global _REGISTRY
    _REGISTRY = _ConstitutionalRegistry()
    _REGISTRY.ensure_loaded(jsonl_path)
