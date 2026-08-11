"""
maqayis_ontology_candidate_builder.py — Layer 4 builder: OntologyCandidateProfile
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Builds OntologyCandidateProfile (Layer 4 of MaqayisSourceBundle) from the
completed Layers 1-3 (SourceEvidence, LexicalClaimGraph, SemanticOriginGraph).

Constitutional contract (the most critical in the entire pipeline):
  ┌─────────────────────────────────────────────────────────────────────┐
  │  EVERY field produced here is labeled ONTOLOGY_CANDIDATE_ONLY.     │
  │  This file NEVER produces licensed ontological facts.               │
  │  All outputs require human review before any ontological use.       │
  │  Maqayis al-Lugha is a lexical source, not an ontological authority.│
  └─────────────────────────────────────────────────────────────────────┘

Blocking conditions (OntologyCandidateProfile NOT built when any holds):
  a. bundle.extraction_meta contains any BLOCKING_RESIDUAL
     (ROOT_IDENTITY_CONFLICT, ROOT_IDENTITY_UNRESOLVED, MISSING_SOURCE_PASSAGE,
      TEXT_VERIFICATION_FAILED, INTER_ENTRY_CONFLICT)
  b. bundle.root_identity.root_identity_match is CONFLICT or UNRESOLVED
  c. bundle.entry_kind is CHAPTER_HEADER or OCR_NOISE
  d. bundle.semantic_origin_graph is None (Layer 3 not built)
  e. bundle.lexical_claim_graph is None (Layer 2 not built)
  f. No LexicalOriginRecords in bundle.origins

One ConceptCandidate is built per LexicalOriginRecord.
For DUAL entries: two ConceptCandidates — one per semantic origin.

Candidate derivation logic:
  GenusCandidateRecord      → semantic_nucleus from RootOriginNode
  DifferentiaCandidateRecord → PROPERTY_KIND branches or AUTHORITY_CITATION claims
  PropertyCandidateRecord   → branches with PART_OF / QUALITY / STATE relations
  ParticipantRoleRecord     → AGENT_OF / PATIENT_OF / INSTRUMENT_OF branches
  EventProfileCandidateRecord → when semantic_kind_candidate is EVENT_KIND
  FunctionCandidateRecord   → when semantic_kind_candidate is FUNCTION_KIND
  RelationCandidateRecord   → when semantic_kind_candidate is RELATION_KIND
  MereologyCandidateRecord  → PART_OF branches
  CausalRelationCandidateRecord → causal_profile fields from LexicalOriginRecord
  SimilarityCandidateRecord → SIMILARITY_EXTENSION branches
  OppositionCandidateRecord → CROSS_REFERENCE claims or NEGATIVE_CLAIM entry
  SemanticTransferRecord    → METAPHORICAL_EXTENSION branches

Upper kind mapping (from OriginSemanticKind to UpperKindCandidate):
  ENTITY_KIND  → ENTITY
  EVENT_KIND   → EVENT
  STATE_KIND   → STATE
  PROPERTY_KIND → PROPERTY
  RELATION_KIND → RELATION
  SPATIAL_KIND → PLACE
  TEMPORAL_KIND → TIME
  QUANTITY_KIND → QUANTITY
  FUNCTION_KIND → FUNCTION
  MOTION_KIND   → EVENT  (motion = dynamic event)
  EVALUATIVE_KIND → PROPERTY
  UNKNOWN       → UNKNOWN
"""
from __future__ import annotations

import re
import uuid
from dataclasses import field
from typing import Dict, List, Optional, Tuple

from .maqayis_source_schema import (
    BLOCKING_RESIDUALS,
    ONTOLOGY_CANDIDATE_ONLY,
    SCHEMA_VERSION,
    AttributionMode,
    BranchRelation,
    CausalMode,
    CausalRelationCandidateRecord,
    ConceptCandidate,
    DifferentiaCandidateRecord,
    Dynamicity,
    EntryKind,
    EventKind,
    EventProfileCandidateRecord,
    EvidenceStatus,
    Explicitness,
    ExtractionMetadata,
    ExtractionMethod,
    FunctionCandidateRecord,
    GenusCandidateRecord,
    Gradability,
    LexicalOriginRecord,
    MaqayisSourceBundle,
    MereologyCandidateRecord,
    MereologyKind,
    OppositionCandidateRecord,
    OppositionType,
    OriginSemanticKind,
    ParticipantRole,
    ParticipantRoleRecord,
    Persistence,
    PropertyCandidateRecord,
    PropertyType,
    RelationCandidateRecord,
    RelationKind,
    ReviewState,
    RootIdentityMatch,
    SemanticTransferRecord,
    SemanticTransferType,
    SimilarityCandidateRecord,
    SimilarityDimension,
    UpperKindCandidate,
    OntologyCandidateProfile,
    ResidualType,
    BranchRecord,
)


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

#: Map OriginSemanticKind → UpperKindCandidate
_UPPER_KIND_MAP: Dict[OriginSemanticKind, UpperKindCandidate] = {
    OriginSemanticKind.ENTITY_KIND:    UpperKindCandidate.ENTITY,
    OriginSemanticKind.EVENT_KIND:     UpperKindCandidate.EVENT,
    OriginSemanticKind.STATE_KIND:     UpperKindCandidate.STATE,
    OriginSemanticKind.PROPERTY_KIND:  UpperKindCandidate.PROPERTY,
    OriginSemanticKind.RELATION_KIND:  UpperKindCandidate.RELATION,
    OriginSemanticKind.SPATIAL_KIND:   UpperKindCandidate.PLACE,
    OriginSemanticKind.TEMPORAL_KIND:  UpperKindCandidate.TIME,
    OriginSemanticKind.QUANTITY_KIND:  UpperKindCandidate.QUANTITY,
    OriginSemanticKind.FUNCTION_KIND:  UpperKindCandidate.FUNCTION,
    OriginSemanticKind.MOTION_KIND:    UpperKindCandidate.EVENT,   # motion = dynamic event
    OriginSemanticKind.EVALUATIVE_KIND: UpperKindCandidate.PROPERTY,
    OriginSemanticKind.UNKNOWN:        UpperKindCandidate.UNKNOWN,
}

#: EventKind heuristics by motion/event term patterns
_EVENT_KIND_PATTERNS: List[Tuple[re.Pattern, EventKind]] = [
    (re.compile(r"حركة|تحرك|ذهاب|مشي|سير|عبور", re.UNICODE),  EventKind.MOTION),
    (re.compile(r"كلام|قول|نطق|خبر|بلاغ", re.UNICODE),         EventKind.COMMUNICATION),
    (re.compile(r"صنع|خلق|إنشاء|تأليف|إيجاد", re.UNICODE),     EventKind.CREATION),
    (re.compile(r"كسر|هدم|إفساد|تدمير|إتلاف", re.UNICODE),     EventKind.DESTRUCTION),
    (re.compile(r"نقل|إعطاء|تسليم|أخذ|أخذ\s+من", re.UNICODE),  EventKind.TRANSFER),
    (re.compile(r"رؤية|سمع|إدراك|شعور|إحساس", re.UNICODE),     EventKind.PERCEPTION),
    (re.compile(r"فكر|علم|معرفة|تذكر|نسيان", re.UNICODE),      EventKind.COGNITION),
    (re.compile(r"تغيّر|تحوّل|انقلب|صار\b", re.UNICODE),       EventKind.STATE_TRANSITION),
    (re.compile(r"فعل|عمل|نشاط|سعي", re.UNICODE),              EventKind.ACTION),
]

#: BranchRelation → ParticipantRole mapping
_RELATION_TO_ROLE: Dict[BranchRelation, ParticipantRole] = {
    BranchRelation.AGENT_OF:    ParticipantRole.AGENT,
    BranchRelation.PATIENT_OF:  ParticipantRole.PATIENT,
    BranchRelation.INSTRUMENT_OF: ParticipantRole.INSTRUMENT,
    BranchRelation.RESULT_OF:   ParticipantRole.RESULT,
    BranchRelation.LOCATION_OF: ParticipantRole.LOCATION,
}

#: BranchRelation → MereologyKind mapping
_RELATION_TO_MEREOLOGY: Dict[BranchRelation, MereologyKind] = {
    BranchRelation.PART_OF: MereologyKind.STRUCTURAL_PART_OF,
}

#: BranchRelation → RelationKind mapping
_RELATION_TO_RELKIND: Dict[BranchRelation, RelationKind] = {
    BranchRelation.RESULT_OF:    RelationKind.RESULTS_IN,
    BranchRelation.CAUSE_OF:     RelationKind.CAUSES,
    BranchRelation.INSTRUMENT_OF: RelationKind.INSTRUMENT_OF,
    BranchRelation.LOCATION_OF:  RelationKind.LOCATED_IN,
    BranchRelation.PART_OF:      RelationKind.PART_OF,
}

#: CausalRole → CausalMode mapping
_CAUSAL_ROLE_TO_MODE = {
    "CAUSE":           CausalMode.DIRECT,
    "ENABLEMENT":      CausalMode.ENABLEMENT,
    "PREVENTION":      CausalMode.PREVENTION,
    "MOTIVATION":      CausalMode.MOTIVATIONAL,
    "NAMING_CAUSE":    CausalMode.NAMING_MOTIVATION,
    "NONE_STATED":     CausalMode.UNKNOWN,
}

#: Opposition detection: NEGATIVE_CLAIM entries may signal opposition
_OPPOSITION_PATTERNS: List[Tuple[re.Pattern, OppositionType]] = [
    (re.compile(r"ضد|نقيض|عكس", re.UNICODE),                   OppositionType.LEXICAL_ONLY),
    (re.compile(r"ليس\s+بـ?|ليس\s+هو|لا\s+يُقال", re.UNICODE), OppositionType.COMPLEMENTARY),
    (re.compile(r"مقابل|في\s+مقابل", re.UNICODE),               OppositionType.GRADABLE),
]


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


def _map_upper_kind(semantic_kind: OriginSemanticKind) -> UpperKindCandidate:
    return _UPPER_KIND_MAP.get(semantic_kind, UpperKindCandidate.UNKNOWN)


def _infer_event_kind(nucleus: Optional[str], gloss: Optional[str]) -> EventKind:
    text = (nucleus or "") + " " + (gloss or "")
    for pattern, kind in _EVENT_KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return EventKind.UNKNOWN


def _infer_dynamicity(semantic_kind: OriginSemanticKind) -> Dynamicity:
    if semantic_kind in (OriginSemanticKind.EVENT_KIND, OriginSemanticKind.MOTION_KIND):
        return Dynamicity.DYNAMIC
    if semantic_kind in (OriginSemanticKind.STATE_KIND, OriginSemanticKind.PROPERTY_KIND):
        return Dynamicity.STATIVE
    return Dynamicity.UNKNOWN


def _detect_opposition(raw_text: Optional[str]) -> Optional[OppositionType]:
    if not raw_text:
        return None
    for pattern, opp_type in _OPPOSITION_PATTERNS:
        if pattern.search(raw_text):
            return opp_type
    return None


def _default_ontology_meta() -> ExtractionMetadata:
    return ExtractionMetadata(
        extraction_method=ExtractionMethod.RULE_BASED,
        explicitness=Explicitness.INFERRED,
        extraction_confidence=None,
        review_state=ReviewState.MACHINE_CANDIDATE,
        evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
        residuals=[],
        counterevidence_ids=[],
        version=SCHEMA_VERSION,
        supersedes_id=None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — PER-CANDIDATE BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_genus_candidate(
    origin: LexicalOriginRecord,
    root_node_nucleus: Optional[str],
) -> Optional[GenusCandidateRecord]:
    """
    Genus candidate from semantic_nucleus.

    The genus is the broader concept under which this root's meaning falls.
    Source: semantic_nucleus from RootOriginNode (Priority 1 = يدل على X).
    """
    nucleus = root_node_nucleus or origin.semantic_nucleus
    if not nucleus:
        return None

    explicit = (
        Explicitness.EXPLICIT
        if origin.gloss_method and origin.gloss_method.value == "SOURCE_EXPLICIT"
        else Explicitness.INFERRED
    )
    return GenusCandidateRecord(
        concept_ref=nucleus,
        evidence_span_id=origin.source_span_id,
        confidence=0.7 if explicit == Explicitness.EXPLICIT else 0.4,
        explicitness=explicit,
    )


def _build_differentia_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[DifferentiaCandidateRecord]:
    """
    Differentia candidates: features that distinguish this concept from its genus.

    Sources:
      a. PROPERTY_KIND branches (branch_relation_to_origin marks a property)
      b. Naming-by-property / naming-by-effect branches
    """
    candidates: List[DifferentiaCandidateRecord] = []
    for br in branches:
        if br.origin_index != origin.origin_index:
            continue
        if br.branch_relation_to_origin in (
            BranchRelation.NAMING_BY_PROPERTY,
            BranchRelation.NAMING_BY_EFFECT,
            BranchRelation.NAMING_BY_CAUSE,
        ):
            label = (br.branch_sense_candidate or br.raw_branch_definition or "")[:100]
            if label:
                candidates.append(DifferentiaCandidateRecord(
                    label=label,
                    relation_to_genus="RESTRICTS",
                    evidence_span_id=None,
                ))
    return candidates


def _build_property_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[PropertyCandidateRecord]:
    """
    Property candidates from PROPERTY_KIND origin kind or relevant branches.
    """
    if origin.semantic_kind_candidate not in (
        OriginSemanticKind.PROPERTY_KIND,
        OriginSemanticKind.EVALUATIVE_KIND,
    ):
        # Also check branches with associative / similarity relations
        prop_branches = [
            br for br in branches
            if br.origin_index == origin.origin_index
            and br.branch_relation_to_origin in (
                BranchRelation.SIMILARITY_EXTENSION,
                BranchRelation.NAMING_BY_PROPERTY,
                BranchRelation.ASSOCIATED_WITH,
            )
        ]
        if not prop_branches:
            return []

    # One property candidate from the origin nucleus itself
    candidates: List[PropertyCandidateRecord] = []
    if origin.semantic_kind_candidate in (
        OriginSemanticKind.PROPERTY_KIND,
        OriginSemanticKind.EVALUATIVE_KIND,
    ):
        candidates.append(PropertyCandidateRecord(
            property_ref=origin.semantic_nucleus,
            property_type=PropertyType.QUALITY,
            attribution_mode=AttributionMode.DEFINING,
            gradable=Gradability.UNKNOWN,
            persistence=Persistence.UNKNOWN,
            bearer_kind=None,
            evidence_span_id=origin.source_span_id,
        ))
    return candidates


def _build_event_profile(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> Optional[EventProfileCandidateRecord]:
    """Build EventProfileCandidateRecord for EVENT_KIND and MOTION_KIND origins."""
    if origin.semantic_kind_candidate not in (
        OriginSemanticKind.EVENT_KIND,
        OriginSemanticKind.MOTION_KIND,
    ):
        return None

    ek = _infer_event_kind(origin.semantic_nucleus, origin.raw_origin_text)
    dyn = _infer_dynamicity(origin.semantic_kind_candidate)

    # Participant roles from branches
    roles: List[ParticipantRoleRecord] = []
    for br in branches:
        if br.origin_index != origin.origin_index:
            continue
        role = _RELATION_TO_ROLE.get(br.branch_relation_to_origin)
        if role:
            roles.append(ParticipantRoleRecord(
                role=role,
                type_constraint=br.source_lexical_form,
            ))

    return EventProfileCandidateRecord(
        event_kind=ek,
        dynamicity=dyn,
        participant_role_candidates=roles,
        result_state_candidate=None,
    )


def _build_function_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[FunctionCandidateRecord]:
    """Build FunctionCandidateRecord for FUNCTION_KIND origins."""
    if origin.semantic_kind_candidate != OriginSemanticKind.FUNCTION_KIND:
        # Also check for INSTRUMENT_OF branches
        inst_branches = [
            br for br in branches
            if br.origin_index == origin.origin_index
            and br.branch_relation_to_origin == BranchRelation.INSTRUMENT_OF
        ]
        if not inst_branches:
            return []
        return [
            FunctionCandidateRecord(
                function_type="INSTRUMENT_FOR",
                target_event_ref=br.raw_branch_definition,
                explicitness=Explicitness.STRONGLY_IMPLIED,
            )
            for br in inst_branches
        ]

    return [FunctionCandidateRecord(
        function_type="PURPOSIVE",
        target_event_ref=origin.semantic_nucleus,
        explicitness=Explicitness.INFERRED,
    )]


def _build_relation_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[RelationCandidateRecord]:
    """Build RelationCandidateRecord for RELATION_KIND origins."""
    if origin.semantic_kind_candidate != OriginSemanticKind.RELATION_KIND:
        # Check branches with explicit relational meaning
        rel_branches = [
            br for br in branches
            if br.origin_index == origin.origin_index
            and br.branch_relation_to_origin in _RELATION_TO_RELKIND
        ]
        if not rel_branches:
            return []
        return [
            RelationCandidateRecord(
                relation_kinds=[_RELATION_TO_RELKIND[br.branch_relation_to_origin]],
                domain_candidate=None,
                range_candidate=None,
                arity=2,
            )
            for br in rel_branches
        ]

    return [RelationCandidateRecord(
        relation_kinds=[],
        domain_candidate=None,
        range_candidate=None,
        arity=2,
    )]


def _build_mereology_candidate(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> Optional[MereologyCandidateRecord]:
    """Build MereologyCandidateRecord from PART_OF branches."""
    part_branches = [
        br for br in branches
        if br.origin_index == origin.origin_index
        and br.branch_relation_to_origin == BranchRelation.PART_OF
    ]
    if not part_branches:
        return None
    return MereologyCandidateRecord(relation_type=MereologyKind.STRUCTURAL_PART_OF)


def _build_causal_relation_candidate(
    origin: LexicalOriginRecord,
) -> Optional[CausalRelationCandidateRecord]:
    """Build CausalRelationCandidateRecord from origin's causal_profile."""
    cp = origin.causal_profile
    if cp is None:
        return None
    causal_role_str = (
        cp.causal_role.value
        if hasattr(cp.causal_role, "value")
        else str(cp.causal_role)
    )
    mode = _CAUSAL_ROLE_TO_MODE.get(causal_role_str, CausalMode.UNKNOWN)
    return CausalRelationCandidateRecord(
        cause_ref=cp.cause_target_ref,
        effect_ref=origin.semantic_nucleus,
        causal_mode=mode,
    )


def _build_similarity_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[SimilarityCandidateRecord]:
    """Build SimilarityCandidateRecord from SIMILARITY_EXTENSION branches."""
    sim_branches = [
        br for br in branches
        if br.origin_index == origin.origin_index
        and br.branch_relation_to_origin == BranchRelation.SIMILARITY_EXTENSION
    ]
    return [
        SimilarityCandidateRecord(
            source_ref=origin.semantic_nucleus,
            target_ref=br.source_lexical_form,
            dimension=SimilarityDimension.UNKNOWN,  # requires human determination
        )
        for br in sim_branches
    ]


def _build_opposition_candidates(
    origin: LexicalOriginRecord,
    entry_claim_kind_str: str,
    entry_raw_claim_text: Optional[str],
) -> List[OppositionCandidateRecord]:
    """
    Build OppositionCandidateRecord.

    Sources:
      a. NEGATIVE_CLAIM entry_kind: the root IS the opposition statement
      b. ليس/ضد markers in the origin claim text
    """
    opp_type = _detect_opposition(entry_raw_claim_text)
    if entry_claim_kind_str == "NEGATIVE_CLAIM":
        opp_type = opp_type or OppositionType.COMPLEMENTARY
    if opp_type is None:
        return []
    return [OppositionCandidateRecord(
        opposite_ref=None,  # resolved by cross-reference resolution step
        opposition_type=opp_type,
    )]


def _build_semantic_transfer_candidates(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
) -> List[SemanticTransferRecord]:
    """Build SemanticTransferRecord from METAPHORICAL_EXTENSION branches."""
    meta_branches = [
        br for br in branches
        if br.origin_index == origin.origin_index
        and br.branch_relation_to_origin == BranchRelation.METAPHORICAL_EXTENSION
    ]
    return [
        SemanticTransferRecord(
            source_concept_ref=origin.semantic_nucleus,
            target_concept_ref=br.source_lexical_form,
            transfer_type=SemanticTransferType.METAPHOR,
            source_domain=None,
            target_domain=None,
        )
        for br in meta_branches
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — CONCEPT CANDIDATE BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_concept_candidate(
    origin: LexicalOriginRecord,
    branches: List[BranchRecord],
    root_node_nucleus: Optional[str],
    entry_claim_kind_str: str,
    entry_raw_claim_text: Optional[str],
) -> ConceptCandidate:
    """
    Build one ConceptCandidate from a LexicalOriginRecord.

    All fields marked ONTOLOGY_CANDIDATE_ONLY.
    Definition candidate = semantic_nucleus (best available).
    Upper kind = from OriginSemanticKind mapping.
    """
    nucleus = root_node_nucleus or origin.semantic_nucleus
    upper_kind = _map_upper_kind(origin.semantic_kind_candidate)

    genus = _build_genus_candidate(origin, nucleus)
    differentia = _build_differentia_candidates(origin, branches)
    properties = _build_property_candidates(origin, branches)
    event_profile = _build_event_profile(origin, branches)
    functions = _build_function_candidates(origin, branches)
    relations = _build_relation_candidates(origin, branches)
    mereology = _build_mereology_candidate(origin, branches)
    causal = _build_causal_relation_candidate(origin)
    similarity = _build_similarity_candidates(origin, branches)
    opposition = _build_opposition_candidates(
        origin, entry_claim_kind_str, entry_raw_claim_text
    )
    transfers = _build_semantic_transfer_candidates(origin, branches)

    # Alternative labels from branches
    alt_labels: List[str] = []
    for br in branches:
        if br.origin_index == origin.origin_index and br.source_lexical_form:
            alt_labels.append(br.source_lexical_form)
    # deduplicate, preserve order
    seen: set = set()
    alt_labels_dedup: List[str] = []
    for lab in alt_labels:
        if lab not in seen:
            seen.add(lab)
            alt_labels_dedup.append(lab)

    return ConceptCandidate(
        concept_candidate_id=_new_id("CC"),
        lexical_origin_ref=origin.origin_id,
        ontology_label=ONTOLOGY_CANDIDATE_ONLY,
        preferred_arabic_label=nucleus,
        alternative_labels=alt_labels_dedup[:20],
        definition_candidate=(origin.raw_origin_text or "")[:300] or None,
        upper_kind_candidate=upper_kind,
        genus_candidates=[genus] if genus else [],
        differentia_candidates=differentia,
        property_candidates=properties,
        event_profile_candidate=event_profile,
        function_candidates=functions,
        relation_candidates=relations,
        mereology_candidate=mereology,
        causal_relation_candidate=causal,
        similarity_candidates=similarity,
        opposition_candidates=opposition,
        semantic_transfer_candidates=transfers,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — ONTOLOGY CANDIDATE PROFILE BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class OntologyCandidateBuilder:
    """
    Builds OntologyCandidateProfile (Layer 4) from a completed MaqayisSourceBundle.

    Constitutional: returns None (not an empty profile) when any blocking
    condition applies. The caller checks is_ontology_buildable() first.

    Usage::

        builder = OntologyCandidateBuilder()
        profile = builder.build(bundle)
        if profile is not None:
            bundle.ontology_candidate_profile = profile
    """

    def build(
        self,
        bundle: MaqayisSourceBundle,
    ) -> Optional[OntologyCandidateProfile]:
        """
        Build OntologyCandidateProfile or return None if blocked.

        Blocking conditions checked:
          1. bundle.is_ontology_buildable() → False
          2. bundle.entry_kind in (CHAPTER_HEADER, OCR_NOISE)
          3. bundle.semantic_origin_graph is None
          4. bundle.origins is empty
        """
        # Gate 1: constitutional blocking
        if not bundle.is_ontology_buildable():
            return None

        # Gate 2: entry kind
        if bundle.entry_kind == EntryKind.OCR_NOISE:
            return None

        # Gate 3: Layer 3 must be present
        if bundle.semantic_origin_graph is None:
            return None

        # Gate 4: must have at least one LexicalOriginRecord
        if not bundle.origins:
            return None

        # Gather data from all layers
        origins: List[LexicalOriginRecord] = bundle.origins
        branches: List[BranchRecord] = bundle.branches or []
        graph = bundle.semantic_origin_graph

        # Build nucleus map: origin_index → nucleus from RootOriginNode
        nucleus_by_idx: Dict[int, Optional[str]] = {
            node.origin_index: node.semantic_nucleus
            for node in (graph.root_origin_nodes or [])
        }

        # Entry-level context for opposition detection
        claim_kind_str = (
            bundle.source_claim.claim_kind.value
            if bundle.source_claim and bundle.source_claim.claim_kind
            else "POSITIVE_ORIGIN"
        )
        raw_claim_text = (
            bundle.source_claim.raw_claim_text
            if bundle.source_claim
            else None
        )

        # Build one ConceptCandidate per LexicalOriginRecord
        concept_candidates: List[ConceptCandidate] = []
        for origin in origins:
            nucleus = nucleus_by_idx.get(origin.origin_index)
            cc = build_concept_candidate(
                origin=origin,
                branches=branches,
                root_node_nucleus=nucleus,
                entry_claim_kind_str=claim_kind_str,
                entry_raw_claim_text=raw_claim_text,
            )
            concept_candidates.append(cc)

        return OntologyCandidateProfile(
            profile_id=_new_id("OCP"),
            entry_id=bundle.entry_id,
            ontology_label=ONTOLOGY_CANDIDATE_ONLY,
            concept_candidates=concept_candidates,
            extraction_meta=_default_ontology_meta(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# § 6 — PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_BUILDER = OntologyCandidateBuilder()


def build_ontology_candidate_profile(
    bundle: MaqayisSourceBundle,
) -> Optional[OntologyCandidateProfile]:
    """
    Build OntologyCandidateProfile for a bundle and return it.

    Returns None when any blocking condition applies (see class docstring).
    Does NOT mutate the bundle. Caller attaches the result:

        profile = build_ontology_candidate_profile(bundle)
        bundle.ontology_candidate_profile = profile

    Constitutional: every returned profile has ontology_label=ONTOLOGY_CANDIDATE_ONLY.
    Human review required before any ontological use.
    """
    return _DEFAULT_BUILDER.build(bundle)


def attach_layer4_to_bundle(
    bundle: MaqayisSourceBundle,
) -> MaqayisSourceBundle:
    """
    Build OntologyCandidateProfile and attach it to the bundle in-place.

    If blocked, ontology_candidate_profile remains None.
    Returns the same bundle object.
    """
    profile = _DEFAULT_BUILDER.build(bundle)
    bundle.ontology_candidate_profile = profile
    return bundle


def build_full_pipeline(
    entry: dict,
    loader: "Any",
) -> MaqayisSourceBundle:
    """
    Full pipeline: SourceEvidence → LexicalClaimGraph → SemanticOriginGraph
    → OntologyCandidateProfile, all in one call.

    Requires the module-level singletons from each builder:
      SourceEvidenceBuilder (auto-discovered data paths)
      extract_claims_from_entry, build_lexical_claim_graph_from_entry
      build_semantic_origin_graph, attach_layer3_to_bundle, attach_layer4_to_bundle

    Constitutional: each layer checks its own blocking conditions.
    """
    from .maqayis_source_evidence_builder import SourceEvidenceBuilder, iter_source_bundles
    from .maqayis_claim_extractor import (
        extract_claims_from_entry,
        build_lexical_claim_graph_from_entry,
        ClaimKind,
    )
    from .maqayis_semantic_origin_graph_builder import (
        build_semantic_origin_graph,
        attach_layer3_to_bundle,
    )

    # Layer 1 — build from entry directly using the loader's lines index
    # (This single-entry path goes via SourceEvidenceBuilder separately;
    #  the full-corpus path uses iter_source_bundles.)
    raise NotImplementedError(
        "build_full_pipeline() requires a SourceEvidenceBuilder instance. "
        "Use iter_source_bundles() with run_full_pipeline_on_bundle() instead."
    )


def run_full_pipeline_on_bundle(
    bundle: MaqayisSourceBundle,
    loader: "Any",
) -> MaqayisSourceBundle:
    """
    Run Layers 2-4 on a bundle that already has Layer 1 (SourceEvidence).

    This is the recommended entry point for the full pipeline:

        from pipeline.taaqol_integration.maqayis_source_evidence_builder import (
            iter_source_bundles
        )
        from pipeline.taaqol_integration.maqayis_body_loader import get_default_loader
        from pipeline.taaqol_integration.maqayis_ontology_candidate_builder import (
            run_full_pipeline_on_bundle
        )

        loader = get_default_loader()
        for bundle in iter_source_bundles():
            run_full_pipeline_on_bundle(bundle, loader)
            # bundle now has all four layers populated

    Parameters
    ──────────
    bundle : MaqayisSourceBundle with Layer 1 already populated
    loader : MaqayisBodyLoader for body text resolution

    Returns
    ───────
    The same bundle with Layers 2-4 populated in place.
    """
    from .maqayis_claim_extractor import (
        extract_claims_from_entry,
        build_lexical_claim_graph_from_entry,
    )
    from .maqayis_semantic_origin_graph_builder import (
        build_semantic_origin_graph,
        attach_layer3_to_bundle,
    )

    # Need the original entry dict to re-segment and extract claims.
    # The entry_id lets us re-load, but we don't store the dict in the bundle.
    # Callers that have the entry dict should call run_full_pipeline_on_entry()
    # instead. This function is for callers that already have the bundle.
    raise NotImplementedError(
        "Bundle does not carry the original entry dict. "
        "Use run_full_pipeline_on_entry(entry, loader) instead."
    )


def run_full_pipeline_on_entry(
    entry: dict,
    bundle: MaqayisSourceBundle,
    loader: "Any",
) -> MaqayisSourceBundle:
    """
    Run Layers 2-4 on a bundle that already has Layer 1, given the source entry.

    This is the standard way to run the full pipeline per entry::

        from pipeline.taaqol_integration.maqayis_source_evidence_builder import (
            SourceEvidenceBuilder,
        )
        from pipeline.taaqol_integration.maqayis_body_loader import get_default_loader
        from pipeline.taaqol_integration.maqayis_ontology_candidate_builder import (
            run_full_pipeline_on_entry,
        )

        loader = get_default_loader()
        builder = SourceEvidenceBuilder(lines_jsonl=..., entries_jsonl=...)
        for entry, bundle in zip(entries, builder.iter_bundles()):
            run_full_pipeline_on_entry(entry, bundle, loader)

    Parameters
    ──────────
    entry  : root entry dict from root_entries_corrected.jsonl
    bundle : MaqayisSourceBundle with Layer 1 already populated
    loader : MaqayisBodyLoader instance for body text resolution

    Returns
    ───────
    bundle with Layers 2-4 populated (same object, mutated in place).
    """
    from .maqayis_claim_extractor import (
        extract_claims_from_entry,
        build_lexical_claim_graph_from_entry,
    )
    from .maqayis_semantic_origin_graph_builder import (
        build_semantic_origin_graph,
        attach_layer3_to_bundle,
    )

    # Determine claim_kind from existing source_claim if available
    claim_kind_val = (
        bundle.source_claim.claim_kind
        if bundle.source_claim
        else None
    )

    # Layer 2 — LexicalClaimGraph
    claims = extract_claims_from_entry(entry, loader)
    if claim_kind_val is not None:
        from .maqayis_claim_extractor import ClaimKind as _CK
        # Import already done in claim extractor; pass through
        bundle.lexical_claim_graph = build_lexical_claim_graph_from_entry(
            entry, loader, claim_kind=claim_kind_val
        )
    else:
        bundle.lexical_claim_graph = build_lexical_claim_graph_from_entry(
            entry, loader
        )

    # Layer 3 — SemanticOriginGraph
    graph, origins, branches = build_semantic_origin_graph(entry, claims)
    attach_layer3_to_bundle(bundle, graph, origins, branches)

    # Layer 4 — OntologyCandidateProfile (only if not blocked)
    attach_layer4_to_bundle(bundle)

    return bundle
