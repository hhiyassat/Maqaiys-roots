"""
maqayis_claim_extractor.py — Structured claim extractor for Maqayis body text
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Converts BodySegment objects (from MaqayisBodyLoader.segment_body) into
typed LexicalClaim objects by applying extraction patterns to each segment.

Claim taxonomy
──────────────
  USAGE_CONDITIONAL   يقال X إذا Y     → term=X, definition=Y (condition)
  USAGE_FORM          يقال X .         → term=X (bare attested form)
  USAGE_NAMED         يقال له X        → term=X (named form / technical term)
  AUTHORITY_CITATION  قال NAME : TEXT  → authority=NAME, definition=TEXT
  ETYMOLOGY_ORIGIN    أصله / أصلان X   → definition=X (root origin claim)
  ETYMOLOGY_CAUSAL    لأنّه / كأنّه X  → definition=X (causal analogy)
  ETYMOLOGY_NAMING    سُمِّي X لأنّ Y  → term=X, definition=Y (naming reason)
  ETYMOLOGY_SEMANTIC  يدلّ على X       → definition=X (semantic pointer)
  PLURAL_FORM         والجمع / وجمعه X → term=X (plural form)
  HADITH_EVIDENCE     وفى الحديث : X  → definition=X (prophetic evidence)
  BRANCH_ITEM         ومن الباب        → raw segment (derived item)
  EXCEPTION_NOTE      ومما شذّ         → raw segment (deviation from pattern)
  ORIGIN_BOUNDARY     والأصل الآخر     → marks transition to second origin
  INTRO_EXAMPLE       من ذلك           → raw segment (first examples)
  RAW_SEGMENT         (unmatched)      → raw text, no sub-extraction

origin_index tracking
─────────────────────
All claims carry origin_index (0 or 1). Starts at 0; flips to 1 when a
SECOND_ORIG segment is encountered. Allows callers to separate claims that
belong to the first vs. second origin of a DUAL entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — LEXICAL CLAIM DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LexicalClaim:
    """
    One structured claim extracted from a Maqayis body segment.

    Attributes
    ──────────
    claim_type    : semantic claim type (see module docstring)
    segment_type  : the BodySegment.type that produced this claim
    marker        : the BodySegment.marker (discourse marker text)
    raw_text      : the full BodySegment.text (before extraction)
    term          : extracted Arabic term / form / name (may be None)
    definition    : extracted definition, condition, or explanation (may be None)
    authority     : named authority for AUTHORITY_CITATION claims (may be None)
    origin_index  : 0 = first origin, 1 = second origin (DUAL entries)
    """
    claim_type:   str
    segment_type: str
    marker:       str
    raw_text:     str
    term:         Optional[str] = None
    definition:   Optional[str] = None
    authority:    Optional[str] = None
    origin_index: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Serialisable representation."""
        return {
            "claim_type":   self.claim_type,
            "segment_type": self.segment_type,
            "marker":       self.marker,
            "raw_text":     self.raw_text,
            "term":         self.term,
            "definition":   self.definition,
            "authority":    self.authority,
            "origin_index": self.origin_index,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — EXTRACTION PATTERNS
#   All patterns derived from full-corpus scan (11,164 body lines).
# ═══════════════════════════════════════════════════════════════════════════════

# Arabic letter + diacritic range
_AR = r"[؀-ۿً-ْ]"

# ── USAGE patterns ────────────────────────────────────────────────────────────

# يقال X إذا Y — most informative: term + condition/definition (2,039 إذا occurrences)
_USAGE_COND_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+(.{2,30}?)(?:\s*،\s*|\s+)إذا\s+(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# يقال له X — named form / technical term (11 occurrences)
_USAGE_NAMED_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+له\s+({ar}+(?:\s+{ar}+){{0,2}})".format(ar=_AR),
    re.UNICODE,
)

# يقال X : Y — form with colon definition
_USAGE_COLON_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+(.{2,25}?)\s*:\s*(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# يقال X . — bare form before sentence end
_USAGE_FORM_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+({ar}+(?:\s+{ar}+){{0,4}})\s*[.،]".format(ar=_AR),
    re.UNICODE,
)

# ── AUTHORITY patterns ────────────────────────────────────────────────────────

# قال NAME : TEXT  (name = 1–3 Arabic words)
_AUTH_NAMED_RE = re.compile(
    r"(?:و)?قال\s+({ar}+(?:\s+{ar}+){{0,2}})\s*[:\s]\s*(.{{5,200}})".format(ar=_AR),
    re.UNICODE | re.DOTALL,
)

# قالوا : TEXT
_AUTH_QALU_RE = re.compile(
    r"قالوا\s*[:\s]\s*(.{5,200})",
    re.UNICODE | re.DOTALL,
)

# ── ETYMOLOGY patterns ────────────────────────────────────────────────────────

_ETYM_ORIGIN_RE = re.compile(
    r"أصل(?:ه|ها|هُ|ان)\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)
_ETYM_NAMING_RE = re.compile(
    r"سُمِّي(?:ت)?\s+({ar}+(?:\s+{ar}+){{0,3}})\s+(?:لأنَّ?|لأنه|ل)\s*(.{{5,120}}?)(?:[.،؛]|$)".format(ar=_AR),
    re.UNICODE,
)
_ETYM_CAUSAL_RE = re.compile(
    r"لأنَّ?ه\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)
_ETYM_ANALOGY_RE = re.compile(
    r"كأنَّ?ه\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)
_ETYM_SEMANTIC_RE = re.compile(
    r"يدلُّ? على\s+(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)
_ETYM_DERIV_RE = re.compile(
    r"(?:اشتقاق(?:ه|ها)?|مشتق)\s+(?:من\s+)?(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# ── PLURAL patterns ───────────────────────────────────────────────────────────

# والجمع / وجمعه X — one or more Arabic words possibly joined by و/أو
_PLURAL_RE = re.compile(
    r"(?:و)?(?:الجمع|جمعه)\s+({ar}+(?:\s+(?:و|أو)\s+{ar}+)*)".format(ar=_AR),
    re.UNICODE,
)

# ── HADITH patterns ───────────────────────────────────────────────────────────

_HADITH_RE = re.compile(
    r"(?:و)?(?:فى|في)\s+الحديث\s*[:\s]\s*(.{5,200})",
    re.UNICODE | re.DOTALL,
)

# ── Authority name cleanup ────────────────────────────────────────────────────

_AUTH_TRAIL_RE = re.compile(r"[،:.؛\s]+$", re.UNICODE)


def _clean_authority(raw: str) -> str:
    name  = _AUTH_TRAIL_RE.sub("", raw.strip())
    words = name.split()
    return " ".join(words[:3]) if words else name


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — PER-TYPE EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_usage(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    full = f"{seg_marker} {seg_text}"
    m = _USAGE_NAMED_RE.search(full)
    if m:
        return LexicalClaim("USAGE_NAMED", "USAGE", seg_marker, seg_text,
                            term=m.group(1).strip(), origin_index=origin_idx)
    m = _USAGE_COND_RE.search(full)
    if m:
        return LexicalClaim("USAGE_CONDITIONAL", "USAGE", seg_marker, seg_text,
                            term=m.group(1).strip(), definition=m.group(2).strip(),
                            origin_index=origin_idx)
    m = _USAGE_COLON_RE.search(full)
    if m:
        return LexicalClaim("USAGE_FORM", "USAGE", seg_marker, seg_text,
                            term=m.group(1).strip(), definition=m.group(2).strip(),
                            origin_index=origin_idx)
    m = _USAGE_FORM_RE.search(full)
    if m:
        return LexicalClaim("USAGE_FORM", "USAGE", seg_marker, seg_text,
                            term=m.group(1).strip(), origin_index=origin_idx)
    return LexicalClaim("RAW_SEGMENT", "USAGE", seg_marker, seg_text,
                        origin_index=origin_idx)


def _extract_authority(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    full = f"{seg_marker} {seg_text}"
    if "قالوا" in full:
        m = _AUTH_QALU_RE.search(full)
        if m:
            return LexicalClaim("AUTHORITY_CITATION", "AUTHORITY", seg_marker, seg_text,
                                authority="قالوا", definition=m.group(1).strip()[:200],
                                origin_index=origin_idx)
    m = _AUTH_NAMED_RE.search(full)
    if m:
        return LexicalClaim("AUTHORITY_CITATION", "AUTHORITY", seg_marker, seg_text,
                            authority=_clean_authority(m.group(1)),
                            definition=m.group(2).strip()[:200],
                            origin_index=origin_idx)
    return LexicalClaim("RAW_SEGMENT", "AUTHORITY", seg_marker, seg_text,
                        origin_index=origin_idx)


def _extract_etymology(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    full = f"{seg_marker} {seg_text}"
    m = _ETYM_NAMING_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_NAMING", "ETYMOLOGY", seg_marker, seg_text,
                            term=m.group(1).strip(), definition=m.group(2).strip(),
                            origin_index=origin_idx)
    m = _ETYM_ORIGIN_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_ORIGIN", "ETYMOLOGY", seg_marker, seg_text,
                            definition=m.group(1).strip(), origin_index=origin_idx)
    m = _ETYM_SEMANTIC_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_SEMANTIC", "ETYMOLOGY", seg_marker, seg_text,
                            definition=m.group(1).strip(), origin_index=origin_idx)
    m = _ETYM_CAUSAL_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_CAUSAL", "ETYMOLOGY", seg_marker, seg_text,
                            definition=m.group(1).strip(), origin_index=origin_idx)
    m = _ETYM_ANALOGY_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_CAUSAL", "ETYMOLOGY", seg_marker, seg_text,
                            definition=m.group(1).strip(), origin_index=origin_idx)
    m = _ETYM_DERIV_RE.search(full)
    if m:
        return LexicalClaim("ETYMOLOGY_ORIGIN", "ETYMOLOGY", seg_marker, seg_text,
                            definition=m.group(1).strip(), origin_index=origin_idx)
    return LexicalClaim("RAW_SEGMENT", "ETYMOLOGY", seg_marker, seg_text,
                        origin_index=origin_idx)


def _extract_plural(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    full = f"{seg_marker} {seg_text}"
    m = _PLURAL_RE.search(full)
    if m:
        return LexicalClaim("PLURAL_FORM", "PLURAL", seg_marker, seg_text,
                            term=m.group(1).strip(), origin_index=origin_idx)
    return LexicalClaim("RAW_SEGMENT", "PLURAL", seg_marker, seg_text,
                        origin_index=origin_idx)


def _extract_hadith(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    full = f"{seg_marker} {seg_text}"
    m = _HADITH_RE.search(full)
    definition = m.group(1).strip()[:200] if m else seg_text[:200]
    return LexicalClaim("HADITH_EVIDENCE", "HADITH", seg_marker, seg_text,
                        definition=definition, origin_index=origin_idx)


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — MAIN EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════════

def extract_claims(segments: list) -> list[LexicalClaim]:
    """
    Convert a list of BodySegment objects into typed LexicalClaim objects.

    Parameters
    ──────────
    segments : list[BodySegment] — output of MaqayisBodyLoader.segment_body()

    Returns
    ───────
    list[LexicalClaim] — ordered, origin_index tracks position in DUAL entries.
    """
    claims: list[LexicalClaim] = []
    origin_idx = 0

    for seg in segments:
        stype  = seg.type
        marker = seg.marker
        text   = seg.text

        if stype == "SECOND_ORIG":
            origin_idx = 1
            claims.append(LexicalClaim("ORIGIN_BOUNDARY", "SECOND_ORIG",
                                       marker, text, origin_index=origin_idx))

        elif stype == "USAGE":
            claims.append(_extract_usage(marker, text, origin_idx))

        elif stype == "AUTHORITY":
            claims.append(_extract_authority(marker, text, origin_idx))

        elif stype == "ETYMOLOGY":
            claims.append(_extract_etymology(marker, text, origin_idx))

        elif stype == "PLURAL":
            claims.append(_extract_plural(marker, text, origin_idx))

        elif stype == "HADITH":
            claims.append(_extract_hadith(marker, text, origin_idx))

        elif stype == "BRANCH":
            claims.append(LexicalClaim("BRANCH_ITEM", "BRANCH",
                                       marker, text, origin_index=origin_idx))

        elif stype == "EXCEPTION":
            claims.append(LexicalClaim("EXCEPTION_NOTE", "EXCEPTION",
                                       marker, text, origin_index=origin_idx))

        elif stype == "INTRO":
            claims.append(LexicalClaim("INTRO_EXAMPLE", "INTRO",
                                       marker, text, origin_index=origin_idx))

        else:
            claims.append(LexicalClaim("RAW_SEGMENT", stype,
                                       marker, text, origin_index=origin_idx))

    return claims


def extract_claims_from_entry(entry: dict, loader: Any) -> list[LexicalClaim]:
    """
    Convenience wrapper: segment body text then extract claims in one call.

    Parameters
    ──────────
    entry  : root entry dict from root_entries JSONL
    loader : MaqayisBodyLoader instance

    Returns
    ───────
    list[LexicalClaim]
    """
    segments = loader.segment_body(entry)
    return extract_claims(segments)


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — SUMMARY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def claims_summary(claims: list[LexicalClaim]) -> dict[str, Any]:
    """
    Return a structured summary dict for one entry's claims:
      total, by_type counts, usage_terms, plural_forms, authorities,
      hadiths, etymology notes, dual_entry flag.
    """
    from collections import Counter
    by_type  = Counter(c.claim_type for c in claims)
    usage    = [c.term for c in claims
                if c.claim_type in ("USAGE_CONDITIONAL", "USAGE_FORM", "USAGE_NAMED")
                and c.term]
    plurals  = [c.term for c in claims if c.claim_type == "PLURAL_FORM" and c.term]
    auths    = [c.authority for c in claims
                if c.claim_type == "AUTHORITY_CITATION" and c.authority]
    hadiths  = [c.definition for c in claims
                if c.claim_type == "HADITH_EVIDENCE" and c.definition]
    etym     = [c.definition for c in claims
                if c.claim_type.startswith("ETYMOLOGY") and c.definition]
    return {
        "total":        len(claims),
        "by_type":      dict(by_type),
        "usage_terms":  usage,
        "plural_forms": plurals,
        "authorities":  list(dict.fromkeys(auths)),
        "hadiths":      hadiths,
        "etymology":    etym,
        "dual_entry":   any(c.claim_type == "ORIGIN_BOUNDARY" for c in claims),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# § 6 — LEXICAL CLAIM GRAPH BUILDER
#   Converts LexicalClaim objects → LexicalClaimGraph (Layer 2 of
#   MaqayisSourceBundle).  All constitutional constraints from
#   maqayis_source_schema.py are enforced here.
#
#   Graph construction rules:
#     • One ClaimNode per LexicalClaim.
#     • One TermNode per unique (normalized) term string.
#     • One AuthorityNode per unique authority name.
#     • One EvidenceNode per HADITH_EVIDENCE or embedded poetry AUTHORITY_CITATION.
#     • CLAIM_ABOUT edge for every ClaimNode that has a term.
#     • ATTRIBUTED_TO edge for every ClaimNode that has an authority.
#     • SUPPORTED_BY edge from EvidenceNode to its parent ClaimNode.
#     • EXEMPLIFIES edge from EvidenceNode → ClaimNode for BRANCH/EXCEPTION items.
#     • ELABORATES edge chaining CONTINUATION segments to their predecessor.
#
#   claim_kind (entry-level) is passed in by the caller; it maps many
#   claim_type values.  Assertion strength is re-evaluated per ClaimNode
#   from the raw_text because segment-level text carries more context.
# ═══════════════════════════════════════════════════════════════════════════════

import uuid as _uuid

from .maqayis_source_schema import (
    AssertionStrength,
    AuthorPosition,
    ClaimAttribution,
    ClaimKind,
    EvidenceStatus,
    ExtractionMethod,
    ExtractionMetadata,
    GraphEdge,
    LexicalClaimEdgeType,
    LexicalClaimGraph,
    AuthorityNode,
    ClaimNode,
    EvidenceNode,
    TermNode,
    ReviewState,
    SCHEMA_VERSION,
    UsageType,
    WitnessFunction,
    EvidenceStrength,
)

# ── Poetry / Quran detection patterns ────────────────────────────────────────

_QURAN_RE = re.compile(r"قال\s+الله|قال\s+تعالى|قرآن", re.UNICODE)
_POETRY_RE = re.compile(
    r"(?:قال\s+الشاعر|قال\s+امرؤ|قال\s+زهير|أنشد|\bشعر\b|بيت\b)",
    re.UNICODE,
)
_HADITH_TEXT_RE = re.compile(r"(?:النبي|رسول\s+الله|صلى\s+الله)", re.UNICODE)

# Markers indicating Ibn Faris is the speaker (no authority name = self)
_SELF_MARKERS = frozenset({"يقال", "يقولون", "قيل", "من ذلك", "ومن الباب",
                            "ومما شذّ", "أصله", "والجمع"})


def _new_graph_id(prefix: str) -> str:
    return f"{prefix}:{_uuid.uuid4().hex[:10]}"


def _map_assertion_strength_for_claim(claim: LexicalClaim) -> AssertionStrength:
    """
    Derive AssertionStrength from claim_type and raw_text.

    Hierarchy:
      HADITH_EVIDENCE        → ASSERTED  (textual authority)
      AUTHORITY_CITATION     → REPORTED  (scholar's speech)
      ETYMOLOGY_SEMANTIC     → ASSERTED  (explicit diacritical pointing)
      ETYMOLOGY_ORIGIN/CAUSAL/NAMING → ASSERTED
      ETYMOLOGY_ANALOGY      → PROBABLE  (كأنه = analogy, not certainty)
      USAGE_CONDITIONAL      → ASSERTED  (attested usage with condition)
      USAGE_FORM / USAGE_NAMED → ASSERTED
      RAW_SEGMENT            → UNKNOWN
      ORIGIN_BOUNDARY        → UNKNOWN   (structural marker, not a claim)
      PLURAL_FORM            → ASSERTED  (lexicographic fact)
    """
    ct = claim.claim_type
    raw = claim.raw_text or ""

    if ct == "HADITH_EVIDENCE":
        return AssertionStrength.ASSERTED
    if ct == "AUTHORITY_CITATION":
        return AssertionStrength.REPORTED
    if ct in ("ETYMOLOGY_ORIGIN", "ETYMOLOGY_SEMANTIC", "ETYMOLOGY_NAMING",
              "ETYMOLOGY_CAUSAL"):
        if re.search(r"كأنَّ?", raw, re.UNICODE):
            return AssertionStrength.PROBABLE
        return AssertionStrength.ASSERTED
    if ct in ("USAGE_CONDITIONAL", "USAGE_FORM", "USAGE_NAMED"):
        return AssertionStrength.ASSERTED
    if ct == "PLURAL_FORM":
        return AssertionStrength.ASSERTED
    if ct in ("BRANCH_ITEM", "INTRO_EXAMPLE"):
        return AssertionStrength.ASSERTED
    if ct in ("EXCEPTION_NOTE",):
        return AssertionStrength.REPORTED
    return AssertionStrength.UNKNOWN


def _map_author_position(claim: LexicalClaim) -> AuthorPosition:
    """
    Derive AuthorPosition for a ClaimNode.

    Ibn Faris's own claims → ADOPTED.
    Reported speech from named authority → REPORTED_ONLY.
    قالوا (anonymous) → REPORTED_ONLY.
    """
    if claim.claim_type == "AUTHORITY_CITATION":
        return AuthorPosition.REPORTED_ONLY
    return AuthorPosition.ADOPTED


def _map_attribution(claim: LexicalClaim) -> ClaimAttribution:
    """Map claim to ClaimAttribution (who makes this claim in the source text)."""
    if claim.claim_type == "AUTHORITY_CITATION":
        auth = (claim.authority or "").strip()
        if "قالوا" in auth:
            return ClaimAttribution.ARABS_GENERAL
        if auth:
            return ClaimAttribution.QUOTED_SCHOLAR
        return ClaimAttribution.UNKNOWN
    if claim.claim_type == "HADITH_EVIDENCE":
        return ClaimAttribution.QUOTED_SCHOLAR  # Prophet's reported speech
    # Markers in _SELF_MARKERS indicate Ibn Faris himself
    if claim.marker in _SELF_MARKERS or claim.segment_type in (
        "USAGE", "ETYMOLOGY", "BRANCH", "EXCEPTION", "PLURAL", "INTRO",
    ):
        return ClaimAttribution.IBN_FARIS
    return ClaimAttribution.UNKNOWN


def _map_usage_type(claim: LexicalClaim) -> UsageType:
    """Map a HADITH or AUTHORITY claim to UsageType for EvidenceNode."""
    raw = claim.raw_text or ""
    if claim.claim_type == "HADITH_EVIDENCE":
        return UsageType.HADITH
    if _QURAN_RE.search(raw):
        return UsageType.QURANIC
    if _POETRY_RE.search(raw):
        return UsageType.POETRY
    if _HADITH_TEXT_RE.search(raw):
        return UsageType.HADITH
    if claim.claim_type == "AUTHORITY_CITATION":
        return UsageType.ARAB_SPEECH
    return UsageType.AUTHOR_EXAMPLE


def _map_witness_function(claim: LexicalClaim) -> WitnessFunction:
    """Derive WitnessFunction for an EvidenceNode from this claim."""
    ct = claim.claim_type
    if ct in ("USAGE_CONDITIONAL", "USAGE_FORM", "USAGE_NAMED"):
        return WitnessFunction.DEMONSTRATES_USAGE
    if ct in ("ETYMOLOGY_ORIGIN", "ETYMOLOGY_CAUSAL", "ETYMOLOGY_NAMING",
              "ETYMOLOGY_SEMANTIC"):
        return WitnessFunction.SUPPORTS_ORIGIN
    if ct == "HADITH_EVIDENCE":
        return WitnessFunction.DEMONSTRATES_USAGE
    if ct == "EXCEPTION_NOTE":
        return WitnessFunction.SUPPORTS_EXCEPTION
    if ct == "BRANCH_ITEM":
        return WitnessFunction.DEMONSTRATES_DERIVATION
    if ct == "AUTHORITY_CITATION":
        return WitnessFunction.DEMONSTRATES_SENSE
    return WitnessFunction.DEMONSTRATES_SENSE


def _default_extraction_meta() -> ExtractionMetadata:
    """Return a blank ExtractionMetadata for graph nodes (shared baseline)."""
    return ExtractionMetadata(
        extraction_method=ExtractionMethod.RULE_BASED,
        explicitness=None,
        extraction_confidence=None,
        review_state=ReviewState.MACHINE_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
        residuals=[],
        counterevidence_ids=[],
        version=SCHEMA_VERSION,
        supersedes_id=None,
    )


def build_lexical_claim_graph(
    entry_id: str,
    claims: "list[LexicalClaim]",
    claim_kind: ClaimKind = ClaimKind.POSITIVE_ORIGIN,
) -> LexicalClaimGraph:
    """
    Build a LexicalClaimGraph from an ordered list of LexicalClaim objects.

    Parameters
    ──────────
    entry_id   : the entry_id string from root_entries JSONL
    claims     : output of extract_claims() for this entry
    claim_kind : entry-level claim kind (from SourceClaimRecord.claim_kind)
                 Default: POSITIVE_ORIGIN

    Returns
    ───────
    LexicalClaimGraph with fully populated nodes and typed edges.

    Graph invariants:
      - Every ClaimNode with a term has exactly one CLAIM_ABOUT edge → TermNode.
      - Every ClaimNode with an authority has exactly one ATTRIBUTED_TO edge.
      - HADITH / QURANIC evidence nodes have a SUPPORTED_BY edge to ClaimNode.
      - TermNodes are deduplicated by normalized form.
      - AuthorityNodes are deduplicated by normalized authority name.
      - No edges between CHAPTER_HEADER claim nodes (there are none produced).
    """
    claim_nodes:     list[ClaimNode]     = []
    term_nodes:      list[TermNode]      = []
    authority_nodes: list[AuthorityNode] = []
    evidence_nodes:  list[EvidenceNode]  = []
    edges:           list[GraphEdge]     = []

    # Deduplication registries
    term_registry: dict[str, str]      = {}  # normalized_form → term_node_id
    auth_registry: dict[str, str]      = {}  # normalized_name → authority_node_id

    def _norm_ar(text: str) -> str:
        """Lightweight Arabic normalisation for dedup keys."""
        t = text.strip()
        t = re.sub(r"[ً-ٰٟ]", "", t)   # strip harakat
        t = re.sub(r"[أإآ]", "ا", t)                  # unify alef
        t = re.sub(r"[ة]", "ه", t)                    # ta marbuta → ha
        return re.sub(r"\s+", " ", t).strip()

    def _get_or_create_term(term_text: str) -> str:
        """Return existing term_node_id or create new TermNode; return its id."""
        norm = _norm_ar(term_text)
        if norm in term_registry:
            return term_registry[norm]
        tid = _new_graph_id("TRM")
        term_nodes.append(TermNode(
            term_node_id=tid,
            lexical_form=term_text.strip(),
            normalized_form=norm,
        ))
        term_registry[norm] = tid
        return tid

    def _get_or_create_authority(auth_name: str) -> str:
        """Return existing authority_node_id or create new AuthorityNode."""
        norm = _norm_ar(auth_name)
        if norm in auth_registry:
            return auth_registry[norm]
        aid = _new_graph_id("AUTH")
        authority_nodes.append(AuthorityNode(
            authority_node_id=aid,
            name=auth_name.strip(),
            name_normalized=norm,
        ))
        auth_registry[norm] = aid
        return aid

    def _add_edge(
        edge_type: LexicalClaimEdgeType,
        source_id: str,
        target_id: str,
        meta: Optional[dict] = None,
    ) -> None:
        edges.append(GraphEdge(
            edge_id=_new_graph_id("EDGE"),
            edge_type=edge_type,
            source_id=source_id,
            target_id=target_id,
            meta=meta or {},
        ))

    # ── Build ClaimNodes and edges ────────────────────────────────────────────

    prev_claim_node_id: Optional[str] = None

    for claim in claims:
        cid = _new_graph_id("CLM")

        # Assertion strength and attribution at sentence level
        astr = _map_assertion_strength_for_claim(claim)
        apos = _map_author_position(claim)
        attr = _map_attribution(claim)

        cnode = ClaimNode(
            claim_node_id=cid,
            claim_type=claim.claim_type,
            raw_text=claim.raw_text,
            term=claim.term,
            definition=claim.definition,
            authority=claim.authority,
            origin_index=claim.origin_index,
            assertion_strength=astr,
            author_position=apos,
            extraction_meta=_default_extraction_meta(),
        )
        claim_nodes.append(cnode)

        # CLAIM_ABOUT: ClaimNode → TermNode (when term is present)
        if claim.term:
            tid = _get_or_create_term(claim.term)
            _add_edge(LexicalClaimEdgeType.CLAIM_ABOUT, cid, tid)

        # ATTRIBUTED_TO: ClaimNode → AuthorityNode (when authority is present)
        if claim.authority:
            aid = _get_or_create_authority(claim.authority)
            _add_edge(LexicalClaimEdgeType.ATTRIBUTED_TO, cid, aid)

        # ELABORATES: chain CONTINUATION / RAW_SEGMENT to predecessor
        if (claim.claim_type == "RAW_SEGMENT"
                and claim.segment_type == "CONTINUATION"
                and prev_claim_node_id is not None):
            _add_edge(LexicalClaimEdgeType.ELABORATES, cid, prev_claim_node_id)

        # Build EvidenceNode for HADITH and strong AUTHORITY citations
        if claim.claim_type in ("HADITH_EVIDENCE",) or (
            claim.claim_type == "AUTHORITY_CITATION"
            and attr in (ClaimAttribution.QUOTED_SCHOLAR, ClaimAttribution.ARABS_GENERAL)
        ):
            usage_type = _map_usage_type(claim)
            witness_fn = _map_witness_function(claim)
            ev_strength = (
                EvidenceStrength.DIRECT
                if usage_type in (UsageType.QURANIC, UsageType.HADITH)
                else EvidenceStrength.SUPPORTING
            )
            # Detect embedded poetry (poetry text inside prose body)
            is_embedded = _POETRY_RE.search(claim.raw_text or "") is not None

            evid = EvidenceNode(
                evidence_node_id=_new_graph_id("EV"),
                text=(claim.definition or claim.raw_text or "")[:300],
                usage_type=usage_type,
                witness_function=witness_fn,
                is_embedded_poetry=is_embedded,
            )
            evidence_nodes.append(evid)

            # SUPPORTED_BY: EvidenceNode → ClaimNode it supports
            _add_edge(
                LexicalClaimEdgeType.SUPPORTED_BY,
                evid.evidence_node_id,
                cid,
                meta={"evidence_strength": ev_strength.value},
            )

        prev_claim_node_id = cid

    graph = LexicalClaimGraph(
        graph_id=_new_graph_id("LCG"),
        entry_id=entry_id,
        claim_nodes=claim_nodes,
        term_nodes=term_nodes,
        authority_nodes=authority_nodes,
        evidence_nodes=evidence_nodes,
        edges=edges,
    )
    return graph


def build_lexical_claim_graph_from_entry(
    entry: dict,
    loader: "Any",
    claim_kind: ClaimKind = ClaimKind.POSITIVE_ORIGIN,
) -> LexicalClaimGraph:
    """
    Convenience wrapper: segment + extract claims + build graph in one call.

    Parameters
    ──────────
    entry      : root entry dict from root_entries JSONL
    loader     : MaqayisBodyLoader instance
    claim_kind : entry-level claim kind (from SourceClaimRecord)

    Returns
    ───────
    LexicalClaimGraph ready for attachment to MaqayisSourceBundle.lexical_claim_graph
    """
    claims = extract_claims_from_entry(entry, loader)
    return build_lexical_claim_graph(
        entry_id=entry.get("entry_id") or "",
        claims=claims,
        claim_kind=claim_kind,
    )
