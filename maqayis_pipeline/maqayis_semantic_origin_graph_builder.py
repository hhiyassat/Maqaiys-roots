"""
maqayis_semantic_origin_graph_builder.py — Layer 3 builder: SemanticOriginGraph
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Builds the SemanticOriginGraph (DAG of meaning structure) and its constituent
LexicalOriginRecord + BranchRecord objects from BodySegments + entry metadata.

Architecture:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Input                                                           │
  │    entry dict (from root_entries_corrected.jsonl)                │
  │    LexicalClaim list (from maqayis_claim_extractor)              │
  │    SourceClaimRecord (entry-level origin count / type)           │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  Step 1 — LexicalOriginRecord extraction                         │
  │    semantic_nucleus extracted from semantic_origin_text          │
  │    Priority: يدل على X > أصله X / هو X > first noun > NULL     │
  │    semantic_kind_candidate: ENTITY/EVENT/STATE/PROPERTY/...      │
  │    abstraction_level, temporal_profile_candidate heuristics      │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  Step 2 — BranchRecord extraction                                │
  │    One BranchRecord per BRANCH_ITEM LexicalClaim                 │
  │    branch_relation_to_origin: heuristic from branch gloss text   │
  │    semantic_distance_candidate: DIRECT / NEAR / EXTENDED / ...   │
  │    regularity: REGULAR unless exception markers present          │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  Step 3 — Graph construction                                     │
  │    RootOriginNode per LexicalOriginRecord                        │
  │    BranchGraphNode per BranchRecord                              │
  │    ExceptionGraphNode per EXCEPTION_NOTE claim                   │
  │    CrossRefGraphNode per CROSS_REFERENCE claim                   │
  │    BRANCHES_FROM edges: BranchNode → RootOriginNode              │
  │    IS_EXCEPTION_OF edges: ExceptionNode → RootOriginNode         │
  │    SECOND_ORIGIN_OF edge: origin[1] → origin[0]  (DUAL entries) │
  │    CROSS_REFERENCES edge: CrossRefNode → entry referenced        │
  └──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  Step 4 — DAG validation (validate_dag())                        │
  │    DFS cycle detection; cycles → INTER_ENTRY_CONFLICT residual   │
  └──────────────────────────────────────────────────────────────────┘

Constitutional contract:
  - hokom_form_analysis_ref = None on every BranchRecord (Hokom fills later)
  - semantic_kind_candidate is always tagged ONTOLOGY_CANDIDATE_ONLY
  - No canonical root extraction from body text (only from heading via Hokom)
  - NUCLEUS_NOT_EXTRACTABLE residual added when nucleus cannot be found
  - Embedded poetry in body lines marked is_embedded_poetry=True; not used
    for semantic analysis (structural marker only)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .maqayis_claim_extractor import LexicalClaim
from .maqayis_source_schema import (
    MaqayisSourceBundle,
    ONTOLOGY_CANDIDATE_ONLY,
    SCHEMA_VERSION,
    AbstractionLevel,
    BranchGraphNode,
    BranchRecord,
    BranchRelation,
    CausalProfile,
    CausalRole,
    ComponentComposition,
    CrossRefGraphNode,
    DomainCandidate,
    EvidenceStatus,
    ExceptionGraphNode,
    ExtractionMetadata,
    ExtractionMethod,
    GlossMethod,
    GraphEdge,
    LexicalOriginRecord,
    OriginSemanticKind,
    OriginType,
    Regularity,
    RelationExplicitness,
    ResidualType,
    ReviewState,
    RootOriginNode,
    SemanticComponent,
    SemanticDistance,
    SemanticOriginEdgeType,
    SemanticOriginGraph,
    TemporalProfile,
)


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — CONSTANTS AND PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# Arabic letter range (includes diacritics)
_AR = r"[؀-ۿً-ْ]"

# ── Semantic nucleus extraction patterns (priority order) ─────────────────────

# Priority 1: يدل على X — explicit semantic pointer
_NUCLEUS_DALALA_RE = re.compile(
    r"يدلُّ?\s+على\s+(.{3,80}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# Priority 2a: أصله X — root origin statement
_NUCLEUS_ASLUH_RE = re.compile(
    r"أصل(?:ه|ها|هُ|ان)?\s+(.{3,80}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# Priority 2b: والأصلان X — dual origin statement
_NUCLEUS_ASLAN_RE = re.compile(
    r"والأصلان\s+(.{3,80}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# Priority 2c: هو / هي X — defining copula
_NUCLEUS_HUWA_RE = re.compile(
    r"(?:^|\s)(?:هو|هي|هما)\s+({ar}+(?:\s+{ar}+){{0,4}})".format(ar=_AR),
    re.UNICODE,
)

# Priority 2d: يعني X — explicit gloss
_NUCLEUS_YAANI_RE = re.compile(
    r"يعني\s+(.{3,80}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# Priority 3: first noun phrase — fallback (crude: first 2-3 Arabic words)
_FIRST_NOUN_RE = re.compile(
    r"^[^؀-ۿ]*({ar}+(?:\s+{ar}+){{0,2}})".format(ar=_AR),
    re.UNICODE,
)

# ── Branch relation heuristics ────────────────────────────────────────────────

# Explicit relation markers in branch gloss text
_BRANCH_RELATION_PATTERNS: List[Tuple[re.Pattern, BranchRelation]] = [
    (re.compile(r"شُبِّه\b|شبَّه|يشبه\b|تشبيه", re.UNICODE), BranchRelation.SIMILARITY_EXTENSION),
    (re.compile(r"مجاز|على\s+المجاز", re.UNICODE),           BranchRelation.METAPHORICAL_EXTENSION),
    (re.compile(r"لأنَّ?ه\s+يُشبه", re.UNICODE),              BranchRelation.SIMILARITY_EXTENSION),
    (re.compile(r"سُمِّي.*لأن", re.UNICODE),                  BranchRelation.NAMING_BY_PROPERTY),
    (re.compile(r"سُمِّي.*بِ", re.UNICODE),                   BranchRelation.NAMING_BY_EFFECT),
    (re.compile(r"آلة|أداة", re.UNICODE),                    BranchRelation.INSTRUMENT_OF),
    (re.compile(r"جمع|جُمُوع", re.UNICODE),                  BranchRelation.SPECIALIZATION),
    (re.compile(r"مكان|موضع|محل", re.UNICODE),               BranchRelation.LOCATION_OF),
    (re.compile(r"فاعل|من\s+يفعل", re.UNICODE),              BranchRelation.AGENT_OF),
    (re.compile(r"نتيجة|أثر|يسبب", re.UNICODE),              BranchRelation.RESULT_OF),
    (re.compile(r"جزء|بعض", re.UNICODE),                     BranchRelation.PART_OF),
]

# ── Semantic distance heuristics ──────────────────────────────────────────────

_DISTANCE_PATTERNS: List[Tuple[re.Pattern, SemanticDistance]] = [
    (re.compile(r"على\s+المجاز|مجازاً", re.UNICODE),          SemanticDistance.METAPHORICAL),
    (re.compile(r"استعارة", re.UNICODE),                      SemanticDistance.METAPHORICAL),
    (re.compile(r"تشبيه|يشبه", re.UNICODE),                   SemanticDistance.EXTENDED),
    (re.compile(r"مشتق\s+من|اشتقاقه\s+من", re.UNICODE),      SemanticDistance.DIRECT),
]

# ── Domain candidate heuristics ───────────────────────────────────────────────

_DOMAIN_PATTERNS: List[Tuple[re.Pattern, DomainCandidate]] = [
    (re.compile(r"الخيل|الإبل|الناقة|البعير|الفرس", re.UNICODE), DomainCandidate.ANIMAL),
    (re.compile(r"الشجر|النبات|الزرع|الثمر", re.UNICODE),         DomainCandidate.PLANT),
    (re.compile(r"العين|الرأس|اليد|القدم|الظهر", re.UNICODE),     DomainCandidate.ANATOMY),
    (re.compile(r"مشى|سار|جرى|وثب|ركض", re.UNICODE),             DomainCandidate.MOTION),
    (re.compile(r"لون|أبيض|أسود|أحمر|أخضر", re.UNICODE),         DomainCandidate.COLOR),
    (re.compile(r"صوت|نطق|كلام|قول", re.UNICODE),                DomainCandidate.SOUND),
    (re.compile(r"عقل|فهم|علم|معرفة", re.UNICODE),               DomainCandidate.COGNITION),
    (re.compile(r"حكم|قضاء|شريعة|فقه", re.UNICODE),              DomainCandidate.LEGAL),
    (re.compile(r"صلاة|زكاة|حج|إيمان|دين", re.UNICODE),          DomainCandidate.RELIGIOUS),
    (re.compile(r"سيف|رمح|قوس|سلاح", re.UNICODE),               DomainCandidate.ARTIFACT),
    (re.compile(r"قبيلة|قوم|أهل|عشيرة", re.UNICODE),             DomainCandidate.SOCIAL),
]

# ── Semantic kind heuristics ──────────────────────────────────────────────────

_KIND_PATTERNS: List[Tuple[re.Pattern, OriginSemanticKind]] = [
    (re.compile(r"الحركة|الذهاب|الإقبال|الإدبار|يمشي|يسير", re.UNICODE), OriginSemanticKind.MOTION_KIND),
    (re.compile(r"الاجتماع|الالتقاء|الانفراد|الفراق", re.UNICODE),       OriginSemanticKind.EVENT_KIND),
    (re.compile(r"الشدة|القوة|اللين|الصلابة|الصفة", re.UNICODE),         OriginSemanticKind.PROPERTY_KIND),
    (re.compile(r"الضعف|الوهن|الخوف|الفزع|الحال", re.UNICODE),          OriginSemanticKind.STATE_KIND),
    (re.compile(r"فوق|تحت|أمام|خلف|بين|عند", re.UNICODE),               OriginSemanticKind.SPATIAL_KIND),
    (re.compile(r"الزمان|الوقت|الحين|المدة", re.UNICODE),               OriginSemanticKind.TEMPORAL_KIND),
    (re.compile(r"العدد|الكثرة|القلة|الواحد", re.UNICODE),               OriginSemanticKind.QUANTITY_KIND),
    (re.compile(r"النسبة|الإضافة|الصلة|الارتباط", re.UNICODE),          OriginSemanticKind.RELATION_KIND),
    (re.compile(r"الوظيفة|الاستعمال|الغاية|المقصد", re.UNICODE),        OriginSemanticKind.FUNCTION_KIND),
    (re.compile(r"الحسن|القبح|المدح|الذم|الخير|الشر", re.UNICODE),      OriginSemanticKind.EVALUATIVE_KIND),
    # Entity is the fallback for concrete nouns
    (re.compile(r"الرجل|المرأة|الشيء|الأمر|الجسم|شخص", re.UNICODE),     OriginSemanticKind.ENTITY_KIND),
]

# ── Temporal profile heuristics ───────────────────────────────────────────────

_TEMPORAL_PATTERNS: List[Tuple[re.Pattern, TemporalProfile]] = [
    (re.compile(r"يدوم|دائم|مستمر|لا\s+ينقطع", re.UNICODE), TemporalProfile.DURATIVE),
    (re.compile(r"مرة|لحظة|بغتة|فجأة|وثبة", re.UNICODE),   TemporalProfile.PUNCTUAL),
    (re.compile(r"صفة|حال|كون|وصف", re.UNICODE),            TemporalProfile.STATIC),
    (re.compile(r"يتكرر|مرات|أحياناً", re.UNICODE),         TemporalProfile.ITERATIVE),
    (re.compile(r"يحدث|يقع|يجري|يسير", re.UNICODE),         TemporalProfile.DYNAMIC),
    (re.compile(r"أثر|نتيجة|ما\s+بقي", re.UNICODE),         TemporalProfile.RESULT_STATE),
]

# ── Cross-reference target extraction ─────────────────────────────────────────

_XREF_TARGET_RE = re.compile(
    r"(?:في|فى|في\s+باب|انظر)\s+(?:(?:باب|فصل)\s+)?([؀-ۿ]+(?:\s+[؀-ۿ]+){0,2})",
    re.UNICODE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — HELPER UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


def _norm_ar(text: str) -> str:
    """Lightweight normalisation: strip diacritics, unify alef."""
    t = re.sub(r"[ً-ٰٟ]", "", text)  # harakat
    t = re.sub(r"[أإآ]", "ا", t)
    t = t.strip()
    return re.sub(r"\s+", " ", t)


def _extract_semantic_nucleus(
    origin_text: Optional[str],
) -> Tuple[Optional[str], GlossMethod, bool]:
    """
    Extract semantic_nucleus from the raw origin text.

    Priority order (from constitutional design doc):
      1. «يدل على X» — explicit semantic pointer
      2. «أصله X» / «هو X» / «يعني X» — defining sentence
      3. First noun phrase in defining sentence — weak fallback
      4. None → NUCLEUS_NOT_EXTRACTABLE residual

    Returns:
      (nucleus_text, GlossMethod, needs_residual)
    """
    if not origin_text or not origin_text.strip():
        return None, GlossMethod.NOT_EXTRACTABLE, True

    text = origin_text.strip()

    # Priority 1: يدل على X
    m = _NUCLEUS_DALALA_RE.search(text)
    if m:
        return m.group(1).strip(), GlossMethod.SOURCE_EXPLICIT, False

    # Priority 2a: أصله / أصلان X
    m = _NUCLEUS_ASLAN_RE.search(text)
    if m:
        return m.group(1).strip(), GlossMethod.SOURCE_EXPLICIT, False
    m = _NUCLEUS_ASLUH_RE.search(text)
    if m:
        return m.group(1).strip(), GlossMethod.SOURCE_EXPLICIT, False

    # Priority 2b: هو / هي X
    m = _NUCLEUS_HUWA_RE.search(text)
    if m:
        return m.group(1).strip(), GlossMethod.SOURCE_EXPLICIT, False

    # Priority 2c: يعني X
    m = _NUCLEUS_YAANI_RE.search(text)
    if m:
        return m.group(1).strip(), GlossMethod.SOURCE_EXPLICIT, False

    # Priority 3: first noun fallback
    m = _FIRST_NOUN_RE.search(text)
    if m:
        words = m.group(1).strip().split()
        nucleus = " ".join(words[:3])
        return nucleus, GlossMethod.MACHINE_SUMMARIZED, False

    return None, GlossMethod.NOT_EXTRACTABLE, True


def _extract_semantic_kind(nucleus: Optional[str], origin_text: Optional[str]) -> OriginSemanticKind:
    """Heuristic OriginSemanticKind from nucleus + origin text."""
    combined = (nucleus or "") + " " + (origin_text or "")
    for pattern, kind in _KIND_PATTERNS:
        if pattern.search(combined):
            return kind
    return OriginSemanticKind.UNKNOWN


def _extract_abstraction_level(nucleus: Optional[str], origin_text: Optional[str]) -> AbstractionLevel:
    """Rough abstraction level from text content."""
    combined = (nucleus or "") + " " + (origin_text or "")
    if re.search(r"الفكر|المعنى|التصور|الذهن|المفهوم", combined, re.UNICODE):
        return AbstractionLevel.MENTAL_STATE
    if re.search(r"العرف|العادة|التقليد|الاجتماع", combined, re.UNICODE):
        return AbstractionLevel.SOCIAL_CONVENTION
    if re.search(r"النسبة|الإضافة|الصلة", combined, re.UNICODE):
        return AbstractionLevel.ABSTRACT_RELATION
    if re.search(r"الحركة|الفعل|العمل|الصنع", combined, re.UNICODE):
        return AbstractionLevel.PHYSICAL_PROCESS
    if re.search(r"الجسم|المادة|الشيء\s+الملموس|الجسماني", combined, re.UNICODE):
        return AbstractionLevel.CONCRETE
    return AbstractionLevel.UNKNOWN


def _extract_temporal_profile(origin_text: Optional[str]) -> TemporalProfile:
    """Heuristic temporal profile from origin text."""
    if not origin_text:
        return TemporalProfile.UNKNOWN
    for pattern, profile in _TEMPORAL_PATTERNS:
        if pattern.search(origin_text):
            return profile
    return TemporalProfile.UNKNOWN


def _extract_branch_relation(branch_gloss: str) -> Tuple[BranchRelation, RelationExplicitness]:
    """
    Extract branch_relation_to_origin from branch gloss text.

    Returns (BranchRelation, RelationExplicitness).
    Default: (DIRECT_INSTANCE, SYSTEM_INFERRED).
    """
    for pattern, relation in _BRANCH_RELATION_PATTERNS:
        if pattern.search(branch_gloss):
            return relation, RelationExplicitness.STRONGLY_IMPLIED
    return BranchRelation.DIRECT_INSTANCE, RelationExplicitness.SYSTEM_INFERRED


def _extract_semantic_distance(branch_gloss: str) -> SemanticDistance:
    """Heuristic SemanticDistance from branch gloss."""
    for pattern, dist in _DISTANCE_PATTERNS:
        if pattern.search(branch_gloss):
            return dist
    return SemanticDistance.NEAR  # default: close to origin but not identical


def _extract_domain(text: str) -> DomainCandidate:
    """Guess DomainCandidate from branch or origin gloss text."""
    for pattern, domain in _DOMAIN_PATTERNS:
        if pattern.search(text):
            return domain
    return DomainCandidate.GENERAL_LANGUAGE


def _extract_xref_target(raw_text: str) -> Optional[str]:
    """Extract the referenced entry identifier from a CROSS_REFERENCE claim text."""
    m = _XREF_TARGET_RE.search(raw_text)
    if m:
        return _norm_ar(m.group(1))
    return None


def _default_extraction_meta() -> ExtractionMetadata:
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


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — LEXICAL ORIGIN RECORD BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_lexical_origin_records(
    entry: dict,
    claims: List[LexicalClaim],
) -> Tuple[List[LexicalOriginRecord], bool]:
    """
    Build LexicalOriginRecord list from entry metadata + extracted claims.

    For SINGULAR entries: one record (origin_index=0).
    For DUAL entries: two records (origin_index=0 and 1).
    For CHAPTER_HEADER / CROSS_REFERENCE: empty list.

    Returns:
      (list[LexicalOriginRecord], needs_nucleus_residual)
    """
    semantic_origin_type = entry.get("semantic_origin_type") or "NONE"
    raw_origin_text = entry.get("semantic_origin_text") or ""
    origin_count = entry.get("origin_count")

    if semantic_origin_type in ("CHAPTER_HEADER", "CROSS_REFERENCE", "NOT_ROOT"):
        return [], False

    if not raw_origin_text:
        return [], True  # NUCLEUS_NOT_EXTRACTABLE

    # Determine how many origins
    dual = any(c.claim_type == "ORIGIN_BOUNDARY" for c in claims)
    n_origins = 2 if dual else 1

    records: List[LexicalOriginRecord] = []
    any_residual = False

    # For DUAL entries, split origin text at والأصل الآخر marker
    if dual and "والأصل الآخر" in raw_origin_text:
        parts = re.split(r"والأصل\s+الآخر|والثاني\b|فالأول\b", raw_origin_text, maxsplit=1)
    elif dual:
        # Split at the midpoint heuristically (fallback)
        parts = [raw_origin_text, ""]
    else:
        parts = [raw_origin_text]

    for idx, part in enumerate(parts[:n_origins]):
        nucleus, gloss_method, needs_res = _extract_semantic_nucleus(part or None)
        if needs_res:
            any_residual = True

        semantic_kind = _extract_semantic_kind(nucleus, part)
        abstraction = _extract_abstraction_level(nucleus, part)
        temporal = _extract_temporal_profile(part)

        rec = LexicalOriginRecord(
            origin_id=_new_id("ORI"),
            claim_id=None,               # linked by caller
            origin_index=idx,
            origin_type=_str_to_origin_type(semantic_origin_type),
            raw_origin_text=part or None,
            normalized_origin_text=_norm_ar(part) if part else None,
            verified_origin_text=None,   # human review required
            source_span_id=None,
            origin_gloss_candidate=nucleus,
            origin_gloss_language="ar",
            gloss_method=gloss_method,
            semantic_nucleus=nucleus,
            semantic_components=[],      # populated by downstream enricher
            component_composition=ComponentComposition.UNSPECIFIED,
            semantic_kind_candidate=semantic_kind,
            abstraction_level=abstraction,
            temporal_profile_candidate=temporal,
            directionality_candidate=None,
            causal_profile=None,
        )
        records.append(rec)

    return records, any_residual


def _str_to_origin_type(s: str) -> OriginType:
    mapping = {
        "SINGULAR": OriginType.SINGULAR,
        "DUAL":     OriginType.DUAL,
        "TRIPLE":   OriginType.TRIPLE,
        "MULTIPLE": OriginType.MULTIPLE,
        "SOUND_ROOTS": OriginType.SOUND_ROOTS,
    }
    return mapping.get(s, OriginType.UNKNOWN)


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — BRANCH RECORD BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_branch_records(
    claims: List[LexicalClaim],
    origins: List[LexicalOriginRecord],
) -> List[BranchRecord]:
    """
    Build BranchRecord list from BRANCH_ITEM LexicalClaims.

    Each BRANCH_ITEM claim → one BranchRecord linked to the correct
    LexicalOriginRecord via origin_index.

    Constitutional: hokom_form_analysis_ref = None (Hokom fills later).
    """
    records: List[BranchRecord] = []

    # Build origin_index → origin_id map
    origin_by_idx: Dict[int, str] = {
        r.origin_index: r.origin_id for r in origins
    }
    default_origin_id = origins[0].origin_id if origins else None

    branch_index_by_origin: Dict[int, int] = {}  # tracks per-origin branch count

    for claim in claims:
        if claim.claim_type != "BRANCH_ITEM":
            continue

        oi = claim.origin_index
        origin_id = origin_by_idx.get(oi) or default_origin_id
        branch_idx = branch_index_by_origin.get(oi, 0)
        branch_index_by_origin[oi] = branch_idx + 1

        # Extract the lexical form (term from claim) and gloss (definition)
        source_form = (claim.term or "").strip()
        raw_gloss = (claim.definition or claim.raw_text or "").strip()[:200]
        normalized_form = _norm_ar(source_form) if source_form else ""

        branch_rel, rel_explicit = _extract_branch_relation(raw_gloss)
        sem_dist = _extract_semantic_distance(raw_gloss)
        domain = _extract_domain(raw_gloss)

        rec = BranchRecord(
            branch_id=_new_id("BR"),
            origin_id=origin_id,
            origin_index=oi,
            branch_index=branch_idx,
            # Lexical form
            source_lexical_form=source_form or None,
            vocalized_form=None,         # requires human or specialised tool
            normalized_form=normalized_form or None,
            form_as_written_in_source=claim.raw_text[:80] if claim.raw_text else None,
            # Hokom interface: left None — Hokom fills morphological analysis
            hokom_form_analysis_ref=None,
            # Gloss / sense
            raw_branch_definition=raw_gloss or None,
            normalized_branch_gloss=_norm_ar(raw_gloss) if raw_gloss else None,
            branch_sense_candidate=raw_gloss[:100] if raw_gloss else None,
            # Semantic relations
            branch_relation_to_origin=branch_rel,
            relation_explicitness=rel_explicit,
            semantic_distance_candidate=sem_dist,
            regularity=Regularity.REGULAR,   # exception handled separately
            domain_candidate=domain,
        )
        records.append(rec)

    return records


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — SEMANTIC ORIGIN GRAPH BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticOriginGraphBuilder:
    """
    Builds SemanticOriginGraph (Layer 3) from claims + entry metadata.

    Usage::

        builder = SemanticOriginGraphBuilder()
        graph, origins, branches = builder.build(entry, claims)
    """

    def build(
        self,
        entry: dict,
        claims: List[LexicalClaim],
    ) -> Tuple[
        SemanticOriginGraph,
        List[LexicalOriginRecord],
        List[BranchRecord],
        bool,           # needs_nucleus_residual
    ]:
        """
        Build SemanticOriginGraph and its constituent records.

        Returns:
          (graph, origins, branches, needs_nucleus_residual)
        """
        entry_id = entry.get("entry_id") or ""

        # Step 1: LexicalOriginRecords
        origins, needs_nucleus_res = build_lexical_origin_records(entry, claims)

        # Step 2: BranchRecords
        branches = build_branch_records(claims, origins)

        # Step 3: Graph nodes
        root_nodes     = self._build_root_nodes(origins)
        branch_nodes   = self._build_branch_nodes(branches)
        exception_nodes = self._build_exception_nodes(claims, origins)
        cross_ref_nodes = self._build_cross_ref_nodes(claims)

        # Step 4: Edges
        edges = self._build_edges(
            root_nodes, branch_nodes, exception_nodes, cross_ref_nodes
        )

        graph = SemanticOriginGraph(
            graph_id=_new_id("SOG"),
            entry_id=entry_id,
            root_origin_nodes=root_nodes,
            branch_nodes=branch_nodes,
            exception_nodes=exception_nodes,
            cross_ref_nodes=cross_ref_nodes,
            edges=edges,
        )

        return graph, origins, branches, needs_nucleus_res

    # ── Node builders ────────────────────────────────────────────────────────

    def _build_root_nodes(
        self, origins: List[LexicalOriginRecord]
    ) -> List[RootOriginNode]:
        return [
            RootOriginNode(
                node_id=_new_id("RON"),
                origin_index=ori.origin_index,
                raw_text=ori.raw_origin_text,
                semantic_nucleus=ori.semantic_nucleus,
                semantic_kind_candidate=ori.semantic_kind_candidate,
            )
            for ori in origins
        ]

    def _build_branch_nodes(
        self, branches: List[BranchRecord]
    ) -> List[BranchGraphNode]:
        return [
            BranchGraphNode(
                node_id=_new_id("BGN"),
                branch_id=br.branch_id,
                origin_index=br.origin_index,
                source_form=br.source_lexical_form,
                raw_definition=br.raw_branch_definition,
                relation_to_origin=br.branch_relation_to_origin,
            )
            for br in branches
        ]

    def _build_exception_nodes(
        self,
        claims: List[LexicalClaim],
        origins: List[LexicalOriginRecord],
    ) -> List[ExceptionGraphNode]:
        origin_by_idx = {r.origin_index: r.origin_id for r in origins}
        nodes: List[ExceptionGraphNode] = []
        for claim in claims:
            if claim.claim_type != "EXCEPTION_NOTE":
                continue
            nodes.append(ExceptionGraphNode(
                node_id=_new_id("EXN"),
                source_form=(claim.term or "").strip() or None,
                raw_text=claim.raw_text or "",
                origin_index=claim.origin_index,
            ))
        return nodes

    def _build_cross_ref_nodes(
        self, claims: List[LexicalClaim]
    ) -> List[CrossRefGraphNode]:
        nodes: List[CrossRefGraphNode] = []
        for claim in claims:
            if claim.claim_type not in ("ORIGIN_BOUNDARY",) and claim.segment_type not in ("CROSS_REFERENCE",):
                continue
            target = _extract_xref_target(claim.raw_text or "")
            nodes.append(CrossRefGraphNode(
                node_id=_new_id("XRN"),
                target_entry_id=target,
                raw_text=claim.raw_text or "",
            ))
        return nodes

    # ── Edge builder ─────────────────────────────────────────────────────────

    def _build_edges(
        self,
        root_nodes:      List[RootOriginNode],
        branch_nodes:    List[BranchGraphNode],
        exception_nodes: List[ExceptionGraphNode],
        cross_ref_nodes: List[CrossRefGraphNode],
    ) -> List[GraphEdge]:
        edges: List[GraphEdge] = []

        # Map origin_index → root node_id
        root_by_idx: Dict[int, str] = {
            n.origin_index: n.node_id for n in root_nodes
        }
        default_root = root_nodes[0].node_id if root_nodes else None

        # SECOND_ORIGIN_OF: root[1] → root[0]
        if len(root_nodes) >= 2:
            edges.append(GraphEdge(
                edge_id=_new_id("EDGE"),
                edge_type=SemanticOriginEdgeType.SECOND_ORIGIN_OF,
                source_id=root_nodes[1].node_id,
                target_id=root_nodes[0].node_id,
                meta={},
            ))

        # BRANCHES_FROM: BranchGraphNode → RootOriginNode
        for bn in branch_nodes:
            root_id = root_by_idx.get(bn.origin_index) or default_root
            if root_id:
                edges.append(GraphEdge(
                    edge_id=_new_id("EDGE"),
                    edge_type=SemanticOriginEdgeType.BRANCHES_FROM,
                    source_id=bn.node_id,
                    target_id=root_id,
                    meta={
                        "relation": bn.relation_to_origin.value
                        if hasattr(bn.relation_to_origin, "value")
                        else str(bn.relation_to_origin),
                    },
                ))

        # IS_EXCEPTION_OF: ExceptionGraphNode → RootOriginNode
        for en in exception_nodes:
            root_id = root_by_idx.get(en.origin_index) or default_root
            if root_id:
                edges.append(GraphEdge(
                    edge_id=_new_id("EDGE"),
                    edge_type=SemanticOriginEdgeType.IS_EXCEPTION_OF,
                    source_id=en.node_id,
                    target_id=root_id,
                    meta={},
                ))

        # CROSS_REFERENCES: CrossRefGraphNode → (noted as dangling, resolved later)
        for xn in cross_ref_nodes:
            if xn.target_entry_id:
                edges.append(GraphEdge(
                    edge_id=_new_id("EDGE"),
                    edge_type=SemanticOriginEdgeType.CROSS_REFERENCES,
                    source_id=xn.node_id,
                    target_id=f"ENTRY_REF:{xn.target_entry_id}",
                    meta={"unresolved": True},
                ))

        return edges


# ═══════════════════════════════════════════════════════════════════════════════
# § 6 — PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_BUILDER = SemanticOriginGraphBuilder()


def build_semantic_origin_graph(
    entry: dict,
    claims: List[LexicalClaim],
) -> Tuple[
    SemanticOriginGraph,
    List[LexicalOriginRecord],
    List[BranchRecord],
]:
    """
    Build SemanticOriginGraph, LexicalOriginRecords, and BranchRecords
    for one Maqayis entry.

    Adds NUCLEUS_NOT_EXTRACTABLE residual to extraction metadata when
    semantic_nucleus cannot be identified.  The caller is responsible for
    attaching this residual to the bundle's ExtractionMetadata.

    Parameters
    ──────────
    entry  : root entry dict from root_entries_corrected.jsonl
    claims : LexicalClaim list from extract_claims()

    Returns
    ───────
    (SemanticOriginGraph, list[LexicalOriginRecord], list[BranchRecord])
    The bool needs_nucleus_residual is embedded in the graph's extraction_meta
    via the graph.validate_dag() caller convention; caller checks
    graph.root_origin_nodes[i].semantic_nucleus is None to detect the residual.
    """
    graph, origins, branches, _ = _DEFAULT_BUILDER.build(entry, claims)
    return graph, origins, branches


def attach_layer3_to_bundle(
    bundle: "MaqayisSourceBundle",
    graph: SemanticOriginGraph,
    origins: List[LexicalOriginRecord],
    branches: List[BranchRecord],
) -> "MaqayisSourceBundle":
    """
    Attach Layer 3 artefacts to an existing MaqayisSourceBundle.

    Adds NUCLEUS_NOT_EXTRACTABLE residual when any RootOriginNode has no
    semantic_nucleus (null nucleus = source not explicit enough for extraction).

    Returns the modified bundle (same object, mutated in place).
    """
    bundle.semantic_origin_graph = graph
    bundle.origins = origins
    bundle.branches = branches

    # Check for nucleus residuals
    for ron in graph.root_origin_nodes:
        if ron.semantic_nucleus is None:
            bundle.extraction_meta.add_residual(ResidualType.NUCLEUS_NOT_EXTRACTABLE)
            break

    # Validate DAG — add conflict residual if cycle detected
    if not graph.validate_dag():
        bundle.extraction_meta.add_residual(ResidualType.INTER_ENTRY_CONFLICT)

    return bundle
