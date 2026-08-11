"""
maqayis_source_schema.py
────────────────────────
Constitutional data schema for the Maqayis al-Lugha knowledge source.

Three attribute categories — never mixed:

  Source Attributes         : where the text came from, OCR quality, provenance
  Lexical Attributes        : what Ibn Faris actually claimed about the material
  Ontology Candidate Attrs  : inferred structure — ONTOLOGY_CANDIDATE_ONLY

Pipeline authority:
  Hokom    → canonical_root, morphological analysis
  Maqayis  → claims about material, origins, branches (this file)
  Ontology → candidates built from Maqayis claims (after human review)
  Taaqol   → tests concept validity in running composition

Nothing in this schema promotes a candidate to a fact.
Promotion requires human review and explicit review_state transition.
Machine code may never write IDENTITY_VERIFIED, TEXT_VERIFIED, or
LEXICALLY_REVIEWED — those states require a human reviewer.

Constitutional constraint:
  Maqayis does NOT extract roots from running text,
  does NOT analyse morphological patterns,
  does NOT determine contextual meaning of a word in a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════════════
# MODULE CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

WORK_ID        = "MAQAYIS-AL-LUGHA"
AUTHOR_ID      = "IBN-FARIS"
SCHEMA_VERSION = "1.0.0"

# Sentinel applied to every OntologyCandidateProfile —
# signals to every consumer that this is not a licensed ontological fact.
ONTOLOGY_CANDIDATE_ONLY = "ONTOLOGY_CANDIDATE_ONLY"

# ══════════════════════════════════════════════════════════════════════════════
# A. SOURCE & BIBLIOGRAPHIC ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class CoverageState(str, Enum):
    COVERED               = "COVERED"
    MISSING_VOLUME        = "MISSING_VOLUME"
    PARTIAL_PAGE          = "PARTIAL_PAGE"
    UNREADABLE_PAGE       = "UNREADABLE_PAGE"
    REGISTRY_LOAD_FAILURE = "REGISTRY_LOAD_FAILURE"

class TextReviewState(str, Enum):
    TEXT_CANDIDATE  = "TEXT_CANDIDATE"
    TEXT_VERIFIED   = "TEXT_VERIFIED"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"

# ══════════════════════════════════════════════════════════════════════════════
# B. ENTRY IDENTITY ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class EntryKind(str, Enum):
    ROOT_ENTRY      = "ROOT_ENTRY"
    SUBENTRY        = "SUBENTRY"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    LOAN_WORD_NOTE  = "LOAN_WORD_NOTE"
    DISPUTED_ENTRY  = "DISPUTED_ENTRY"
    NEGATIVE_ENTRY  = "NEGATIVE_ENTRY"
    OCR_NOISE       = "OCR_NOISE"

class HeadingType(str, Enum):
    ROOT_ENTRY      = "ROOT_ENTRY"
    CHAPTER_HEADER  = "CHAPTER_HEADER"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    NOT_ROOT        = "NOT_ROOT"
    UNCERTAIN       = "UNCERTAIN"

class RootIdentityMatch(str, Enum):
    EXACT            = "EXACT"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    CONFLICT         = "CONFLICT"
    UNRESOLVED       = "UNRESOLVED"

# ══════════════════════════════════════════════════════════════════════════════
# C. CLAIM ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class ClaimKind(str, Enum):
    """Entry-level: nature of Ibn Faris's overall claim about the root.
    Distinct from claim_type (sentence-level, in ClaimNode)."""
    POSITIVE_ORIGIN  = "POSITIVE_ORIGIN"
    NEGATIVE_CLAIM   = "NEGATIVE_CLAIM"
    DERIVATION_CLAIM = "DERIVATION_CLAIM"
    LOAN_WORD_CLAIM  = "LOAN_WORD_CLAIM"
    DISPUTED_CLAIM   = "DISPUTED_CLAIM"
    INCOMPLETE_CLAIM = "INCOMPLETE_CLAIM"
    CROSS_REFERENCE  = "CROSS_REFERENCE"

class OriginType(str, Enum):
    SINGULAR      = "SINGULAR"
    DUAL          = "DUAL"
    TRIPLE        = "TRIPLE"
    MULTIPLE      = "MULTIPLE"
    SOUND_ROOTS   = "SOUND_ROOTS"
    NOT_EXTRACTED = "NOT_EXTRACTED"
    UNKNOWN       = "UNKNOWN"

class AssertionStrength(str, Enum):
    """Strength of Ibn Faris's assertion — extracted from lexical cues."""
    ASSERTED          = "ASSERTED"
    EMPHATIC_ASSERTED = "EMPHATIC_ASSERTED"  # «هو أصل صحيح»
    PREFERRED         = "PREFERRED"          # «والأصل عندنا»
    PROBABLE          = "PROBABLE"
    POSSIBLE          = "POSSIBLE"           # «ولعل»
    REPORTED          = "REPORTED"           # «ويقال»
    DOUBTFUL          = "DOUBTFUL"           # «ولا أدري»
    REJECTED          = "REJECTED"           # «وليس بصحيح»
    UNKNOWN           = "UNKNOWN"

class ClaimAttribution(str, Enum):
    IBN_FARIS      = "IBN_FARIS"
    QUOTED_SCHOLAR = "QUOTED_SCHOLAR"
    ARABS_GENERAL  = "ARABS_GENERAL"
    POETIC_WITNESS = "POETIC_WITNESS"
    UNKNOWN        = "UNKNOWN"

class AuthorPosition(str, Enum):
    """Ibn Faris's stance toward a quoted scholar's claim."""
    ADOPTED       = "ADOPTED"
    PREFERRED     = "PREFERRED"
    REPORTED_ONLY = "REPORTED_ONLY"
    REJECTED      = "REJECTED"
    UNRESOLVED    = "UNRESOLVED"

class Polarity(str, Enum):
    POSITIVE  = "POSITIVE"
    NEGATIVE  = "NEGATIVE"
    UNCERTAIN = "UNCERTAIN"

# ══════════════════════════════════════════════════════════════════════════════
# D. ORIGIN SEMANTIC ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class GlossMethod(str, Enum):
    SOURCE_EXPLICIT    = "SOURCE_EXPLICIT"
    MACHINE_SUMMARIZED = "MACHINE_SUMMARIZED"
    HUMAN_SUMMARIZED   = "HUMAN_SUMMARIZED"
    NOT_EXTRACTABLE    = "NOT_EXTRACTABLE"

class OriginSemanticKind(str, Enum):
    ENTITY_KIND     = "ENTITY_KIND"
    EVENT_KIND      = "EVENT_KIND"
    STATE_KIND      = "STATE_KIND"
    PROPERTY_KIND   = "PROPERTY_KIND"
    RELATION_KIND   = "RELATION_KIND"
    MOTION_KIND     = "MOTION_KIND"
    SPATIAL_KIND    = "SPATIAL_KIND"
    TEMPORAL_KIND   = "TEMPORAL_KIND"
    QUANTITY_KIND   = "QUANTITY_KIND"
    FUNCTION_KIND   = "FUNCTION_KIND"
    EVALUATIVE_KIND = "EVALUATIVE_KIND"
    UNKNOWN         = "UNKNOWN"

class AbstractionLevel(str, Enum):
    CONCRETE          = "CONCRETE"
    PHYSICAL_PROCESS  = "PHYSICAL_PROCESS"
    ABSTRACT_RELATION = "ABSTRACT_RELATION"
    MENTAL_STATE      = "MENTAL_STATE"
    SOCIAL_CONVENTION = "SOCIAL_CONVENTION"
    MIXED             = "MIXED"
    UNKNOWN           = "UNKNOWN"

class TemporalProfile(str, Enum):
    STATIC       = "STATIC"
    DYNAMIC      = "DYNAMIC"
    PUNCTUAL     = "PUNCTUAL"
    DURATIVE     = "DURATIVE"
    ITERATIVE    = "ITERATIVE"
    RESULT_STATE = "RESULT_STATE"
    UNKNOWN      = "UNKNOWN"

class DirectionalityKind(str, Enum):
    INWARD          = "INWARD"
    OUTWARD         = "OUTWARD"
    UPWARD          = "UPWARD"
    DOWNWARD        = "DOWNWARD"
    TOWARD          = "TOWARD"
    AWAY_FROM       = "AWAY_FROM"
    BIDIRECTIONAL   = "BIDIRECTIONAL"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"
    UNKNOWN         = "UNKNOWN"

class CausalRole(str, Enum):
    CAUSE        = "CAUSE"
    EFFECT       = "EFFECT"
    ENABLEMENT   = "ENABLEMENT"
    PREVENTION   = "PREVENTION"
    MOTIVATION   = "MOTIVATION"
    NAMING_CAUSE = "NAMING_CAUSE"
    NONE_STATED  = "NONE_STATED"

class ComponentComposition(str, Enum):
    CONJUNCTIVE = "CONJUNCTIVE"
    ALTERNATIVE = "ALTERNATIVE"
    SEQUENTIAL  = "SEQUENTIAL"
    CAUSAL      = "CAUSAL"
    RESULTATIVE = "RESULTATIVE"
    UNSPECIFIED = "UNSPECIFIED"

# ══════════════════════════════════════════════════════════════════════════════
# E. BRANCH ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class BranchRelation(str, Enum):
    DIRECT_INSTANCE        = "DIRECT_INSTANCE"
    SPECIALIZATION         = "SPECIALIZATION"
    RESULT_OF              = "RESULT_OF"
    CAUSE_OF               = "CAUSE_OF"
    INSTRUMENT_OF          = "INSTRUMENT_OF"
    LOCATION_OF            = "LOCATION_OF"
    AGENT_OF               = "AGENT_OF"
    PATIENT_OF             = "PATIENT_OF"
    PART_OF                = "PART_OF"
    SIMILARITY_EXTENSION   = "SIMILARITY_EXTENSION"
    METAPHORICAL_EXTENSION = "METAPHORICAL_EXTENSION"
    NAMING_BY_PROPERTY     = "NAMING_BY_PROPERTY"
    NAMING_BY_EFFECT       = "NAMING_BY_EFFECT"
    NAMING_BY_CAUSE        = "NAMING_BY_CAUSE"
    ASSOCIATED_WITH        = "ASSOCIATED_WITH"
    EXCEPTION              = "EXCEPTION"
    UNKNOWN                = "UNKNOWN"

class RelationExplicitness(str, Enum):
    EXPLICIT_IN_SOURCE = "EXPLICIT_IN_SOURCE"
    STRONGLY_IMPLIED   = "STRONGLY_IMPLIED"
    SYSTEM_INFERRED    = "SYSTEM_INFERRED"
    HUMAN_INFERRED     = "HUMAN_INFERRED"

class SemanticDistance(str, Enum):
    DIRECT       = "DIRECT"
    NEAR         = "NEAR"
    EXTENDED     = "EXTENDED"
    METAPHORICAL = "METAPHORICAL"
    REMOTE       = "REMOTE"
    DISPUTED     = "DISPUTED"
    UNKNOWN      = "UNKNOWN"

class Regularity(str, Enum):
    REGULAR     = "REGULAR"
    ANALOGICAL  = "ANALOGICAL"
    IRREGULAR   = "IRREGULAR"
    EXCEPTIONAL = "EXCEPTIONAL"
    DISPUTED    = "DISPUTED"
    UNKNOWN     = "UNKNOWN"

class DomainCandidate(str, Enum):
    GENERAL_LANGUAGE = "GENERAL_LANGUAGE"
    ANATOMY          = "ANATOMY"
    MOTION           = "MOTION"
    COLOR            = "COLOR"
    SOUND            = "SOUND"
    COGNITION        = "COGNITION"
    SOCIAL           = "SOCIAL"
    LEGAL            = "LEGAL"
    RELIGIOUS        = "RELIGIOUS"
    ARTIFACT         = "ARTIFACT"
    ANIMAL           = "ANIMAL"
    PLANT            = "PLANT"
    UNKNOWN          = "UNKNOWN"

# ══════════════════════════════════════════════════════════════════════════════
# F. USAGE EVIDENCE ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class UsageType(str, Enum):
    QURANIC        = "QURANIC"
    HADITH         = "HADITH"
    POETRY         = "POETRY"
    PROVERB        = "PROVERB"
    ARAB_SPEECH    = "ARAB_SPEECH"
    AUTHOR_EXAMPLE = "AUTHOR_EXAMPLE"
    UNKNOWN        = "UNKNOWN"

class WitnessFunction(str, Enum):
    DEMONSTRATES_SENSE      = "DEMONSTRATES_SENSE"
    DEMONSTRATES_DERIVATION = "DEMONSTRATES_DERIVATION"
    DEMONSTRATES_USAGE      = "DEMONSTRATES_USAGE"
    SUPPORTS_ORIGIN         = "SUPPORTS_ORIGIN"
    SUPPORTS_EXCEPTION      = "SUPPORTS_EXCEPTION"
    SUPPORTS_NEGATIVE_CLAIM = "SUPPORTS_NEGATIVE_CLAIM"

class EvidenceStrength(str, Enum):
    DIRECT       = "DIRECT"
    SUPPORTING   = "SUPPORTING"
    ILLUSTRATIVE = "ILLUSTRATIVE"
    AMBIGUOUS    = "AMBIGUOUS"

# ══════════════════════════════════════════════════════════════════════════════
# G. ONTOLOGY CANDIDATE ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class UpperKindCandidate(str, Enum):
    ENTITY             = "ENTITY"
    EVENT              = "EVENT"
    STATE              = "STATE"
    PROPERTY           = "PROPERTY"
    RELATION           = "RELATION"
    PLACE              = "PLACE"
    TIME               = "TIME"
    QUANTITY           = "QUANTITY"
    INFORMATION_OBJECT = "INFORMATION_OBJECT"
    FUNCTION           = "FUNCTION"
    ROLE               = "ROLE"
    UNKNOWN            = "UNKNOWN"

class Explicitness(str, Enum):
    VERBATIM         = "VERBATIM"
    EXPLICIT         = "EXPLICIT"
    STRONGLY_IMPLIED = "STRONGLY_IMPLIED"
    INFERRED         = "INFERRED"
    SPECULATIVE      = "SPECULATIVE"

class PropertyType(str, Enum):
    QUALITY             = "QUALITY"
    QUANTITY            = "QUANTITY"
    DISPOSITION         = "DISPOSITION"
    STATE               = "STATE"
    RELATIONAL_PROPERTY = "RELATIONAL_PROPERTY"
    FUNCTIONAL_PROPERTY = "FUNCTIONAL_PROPERTY"
    TEMPORAL_PROPERTY   = "TEMPORAL_PROPERTY"
    SPATIAL_PROPERTY    = "SPATIAL_PROPERTY"

class AttributionMode(str, Enum):
    DEFINING            = "DEFINING"
    NECESSARY_CANDIDATE = "NECESSARY_CANDIDATE"
    TYPICAL             = "TYPICAL"
    CONTINGENT          = "CONTINGENT"
    UNKNOWN             = "UNKNOWN"

class Gradability(str, Enum):
    TRUE    = "TRUE"
    FALSE   = "FALSE"
    UNKNOWN = "UNKNOWN"

class Persistence(str, Enum):
    INTRINSIC       = "INTRINSIC"
    TEMPORARY       = "TEMPORARY"
    ACQUIRED        = "ACQUIRED"
    DISPOSITIONAL   = "DISPOSITIONAL"
    EVENT_DEPENDENT = "EVENT_DEPENDENT"
    UNKNOWN         = "UNKNOWN"

class EventKind(str, Enum):
    ACTION           = "ACTION"
    PROCESS          = "PROCESS"
    CHANGE           = "CHANGE"
    MOTION           = "MOTION"
    CREATION         = "CREATION"
    DESTRUCTION      = "DESTRUCTION"
    TRANSFER         = "TRANSFER"
    PERCEPTION       = "PERCEPTION"
    COGNITION        = "COGNITION"
    COMMUNICATION    = "COMMUNICATION"
    STATE_TRANSITION = "STATE_TRANSITION"
    UNKNOWN          = "UNKNOWN"

class Dynamicity(str, Enum):
    DYNAMIC = "DYNAMIC"
    STATIVE = "STATIVE"
    UNKNOWN = "UNKNOWN"

class ParticipantRole(str, Enum):
    AGENT       = "AGENT"
    PATIENT     = "PATIENT"
    INSTRUMENT  = "INSTRUMENT"
    SOURCE      = "SOURCE"
    DESTINATION = "DESTINATION"
    LOCATION    = "LOCATION"
    RESULT      = "RESULT"
    THEME       = "THEME"
    EXPERIENCER = "EXPERIENCER"

class RelationKind(str, Enum):
    PART_OF         = "PART_OF"
    HAS_PART        = "HAS_PART"
    LOCATED_IN      = "LOCATED_IN"
    LOCATED_ON      = "LOCATED_ON"
    ORIGINATES_FROM = "ORIGINATES_FROM"
    MOVES_TOWARD    = "MOVES_TOWARD"
    MOVES_AWAY_FROM = "MOVES_AWAY_FROM"
    CAUSES          = "CAUSES"
    RESULTS_IN      = "RESULTS_IN"
    PREVENTS        = "PREVENTS"
    ENABLES         = "ENABLES"
    INSTRUMENT_OF   = "INSTRUMENT_OF"
    FUNCTION_OF     = "FUNCTION_OF"
    SIMILAR_TO      = "SIMILAR_TO"
    OPPOSITE_TO     = "OPPOSITE_TO"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"

class MereologyKind(str, Enum):
    MATERIAL_PART_OF   = "MATERIAL_PART_OF"
    STRUCTURAL_PART_OF = "STRUCTURAL_PART_OF"
    FUNCTIONAL_PART_OF = "FUNCTIONAL_PART_OF"
    MEMBER_OF          = "MEMBER_OF"
    PORTION_OF         = "PORTION_OF"
    UNKNOWN            = "UNKNOWN"

class CausalMode(str, Enum):
    DIRECT            = "DIRECT"
    ENABLEMENT        = "ENABLEMENT"
    PREVENTION        = "PREVENTION"
    MOTIVATIONAL      = "MOTIVATIONAL"
    NAMING_MOTIVATION = "NAMING_MOTIVATION"
    ASSOCIATIVE       = "ASSOCIATIVE"
    UNKNOWN           = "UNKNOWN"

class SimilarityDimension(str, Enum):
    SHAPE     = "SHAPE"
    MOTION    = "MOTION"
    FUNCTION  = "FUNCTION"
    EFFECT    = "EFFECT"
    SOUND     = "SOUND"
    COLOR     = "COLOR"
    STRUCTURE = "STRUCTURE"
    MEANING   = "MEANING"
    UNKNOWN   = "UNKNOWN"

class OppositionType(str, Enum):
    GRADABLE      = "GRADABLE"
    COMPLEMENTARY = "COMPLEMENTARY"
    DIRECTIONAL   = "DIRECTIONAL"
    CONVERSE      = "CONVERSE"
    REVERSIVE     = "REVERSIVE"
    LEXICAL_ONLY  = "LEXICAL_ONLY"
    UNKNOWN       = "UNKNOWN"

class SemanticTransferType(str, Enum):
    METAPHOR             = "METAPHOR"
    METONYMY             = "METONYMY"
    FUNCTIONAL_EXTENSION = "FUNCTIONAL_EXTENSION"
    CAUSAL_EXTENSION     = "CAUSAL_EXTENSION"
    RESULT_EXTENSION     = "RESULT_EXTENSION"
    LOCATION_EXTENSION   = "LOCATION_EXTENSION"
    INSTRUMENT_EXTENSION = "INSTRUMENT_EXTENSION"
    ABSTRACT_EXTENSION   = "ABSTRACT_EXTENSION"
    UNKNOWN              = "UNKNOWN"

# ══════════════════════════════════════════════════════════════════════════════
# H. EXTRACTION & GOVERNANCE ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class ExtractionMethod(str, Enum):
    OCR              = "OCR"
    REGEX            = "REGEX"
    RULE_BASED       = "RULE_BASED"
    LLM_CANDIDATE    = "LLM_CANDIDATE"
    HUMAN_EXTRACTION = "HUMAN_EXTRACTION"
    IMPORTED_LEGACY  = "IMPORTED_LEGACY"

class ReviewState(str, Enum):
    """Ordered states — only humans may advance past MACHINE_CANDIDATE."""
    UNREVIEWED         = "UNREVIEWED"
    MACHINE_CANDIDATE  = "MACHINE_CANDIDATE"
    SOURCE_LOCATED     = "SOURCE_LOCATED"
    IDENTITY_VERIFIED  = "IDENTITY_VERIFIED"   # human only
    TEXT_VERIFIED      = "TEXT_VERIFIED"        # human only
    ORIGIN_CANDIDATE   = "ORIGIN_CANDIDATE"
    ORIGIN_SEGMENTED   = "ORIGIN_SEGMENTED"
    LEXICALLY_REVIEWED = "LEXICALLY_REVIEWED"   # human only
    AUDIT_PASSED       = "AUDIT_PASSED"         # human only

class EvidenceStatus(str, Enum):
    MACHINE_SOURCE_CLAIM_CANDIDATE = "MACHINE_SOURCE_CLAIM_CANDIDATE"
    SOURCE_LOCATED_EVIDENCE        = "SOURCE_LOCATED_EVIDENCE"
    IDENTITY_VERIFIED_EVIDENCE     = "IDENTITY_VERIFIED_EVIDENCE"
    TEXT_VERIFIED_EVIDENCE         = "TEXT_VERIFIED_EVIDENCE"
    ORIGIN_SEGMENTED_EVIDENCE      = "ORIGIN_SEGMENTED_EVIDENCE"
    LEXICALLY_REVIEWED_EVIDENCE    = "LEXICALLY_REVIEWED_EVIDENCE"

class ResidualType(str, Enum):
    OCR_AMBIGUITY                      = "OCR_AMBIGUITY"
    ROOT_IDENTITY_CONFLICT             = "ROOT_IDENTITY_CONFLICT"
    ROOT_NORMALIZED_MATCH              = "ROOT_NORMALIZED_MATCH"
    ROOT_IDENTITY_UNRESOLVED           = "ROOT_IDENTITY_UNRESOLVED"
    MISSING_SOURCE_PASSAGE             = "MISSING_SOURCE_PASSAGE"
    ORIGIN_CLAIM_CONFLICT              = "ORIGIN_CLAIM_CONFLICT"
    SEGMENTATION_REQUIRED              = "SEGMENTATION_REQUIRED"
    ORIGIN_NOT_EXTRACTABLE             = "ORIGIN_NOT_EXTRACTABLE"
    NUCLEUS_NOT_EXTRACTABLE            = "NUCLEUS_NOT_EXTRACTABLE"
    NUCLEUS_MACHINE_SUMMARIZED         = "NUCLEUS_MACHINE_SUMMARIZED"
    TEXT_VERIFICATION_FAILED           = "TEXT_VERIFICATION_FAILED"
    ONTOLOGY_CLASSIFICATION_UNRESOLVED = "ONTOLOGY_CLASSIFICATION_UNRESOLVED"
    GENUS_UNRESOLVED                   = "GENUS_UNRESOLVED"
    RELATION_TYPE_UNRESOLVED           = "RELATION_TYPE_UNRESOLVED"
    INTER_ENTRY_CONFLICT               = "INTER_ENTRY_CONFLICT"

# Residuals that block OntologyCandidateProfile construction
BLOCKING_RESIDUALS = frozenset({
    ResidualType.ROOT_IDENTITY_CONFLICT,
    ResidualType.ROOT_IDENTITY_UNRESOLVED,
    ResidualType.MISSING_SOURCE_PASSAGE,
    ResidualType.TEXT_VERIFICATION_FAILED,
    ResidualType.INTER_ENTRY_CONFLICT,
})

# ══════════════════════════════════════════════════════════════════════════════
# I. GRAPH EDGE TYPE ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class SemanticOriginEdgeType(str, Enum):
    """Edges for SemanticOriginGraph — meaning structure (DAG)."""
    BRANCHES_FROM    = "BRANCHES_FROM"    # BranchNode → RootOriginNode
    IS_EXCEPTION_OF  = "IS_EXCEPTION_OF"  # ExceptionNode → RootOriginNode
    SECOND_ORIGIN_OF = "SECOND_ORIGIN_OF" # RootOriginNode[1] → RootOriginNode[0]
    CROSS_REFERENCES = "CROSS_REFERENCES" # CrossRefNode → external entry
    SUBSUMES         = "SUBSUMES"         # BranchNode → BranchNode (sub-branch)

class LexicalClaimEdgeType(str, Enum):
    """Edges for LexicalClaimGraph — assertion structure."""
    CLAIM_ABOUT   = "CLAIM_ABOUT"    # ClaimNode → TermNode
    ATTRIBUTED_TO = "ATTRIBUTED_TO"  # ClaimNode → AuthorityNode
    SUPPORTED_BY  = "SUPPORTED_BY"   # ClaimNode → EvidenceNode
    QUALIFIES     = "QUALIFIES"      # ClaimNode → ClaimNode
    ELABORATES    = "ELABORATES"     # ClaimNode → ClaimNode
    CONTRADICTS   = "CONTRADICTS"    # ClaimNode → ClaimNode
    EXEMPLIFIES   = "EXEMPLIFIES"    # ClaimNode → ClaimNode

class AggregationState(str, Enum):
    SINGLE_SOURCE     = "SINGLE_SOURCE"
    CONSISTENT_MULTI  = "CONSISTENT_MULTI"
    CONFLICTING_MULTI = "CONFLICTING_MULTI"

# ══════════════════════════════════════════════════════════════════════════════
# 1. SOURCE EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SourceEvidence:
    """
    Layer 1 of MaqayisSourceBundle.
    Describes WHERE the text came from and HOW reliable it is.
    Contains no semantic claims — purely bibliographic and textual provenance.

    MISSING_VOLUME_COVERAGE_GAP ≠ NEGATIVE_LEXICAL_CLAIM
    Absence of a volume is a gap in coverage, not evidence of absence.
    """
    # ── Source identity ──────────────────────────────────────────────────────
    source_id:     str
    work_id:       str  = WORK_ID
    author_id:     str  = AUTHOR_ID
    edition_id:    Optional[str] = None
    volume_number: Optional[int] = None
    filename:      Optional[str] = None
    pdf_sha256:    Optional[str] = None
    page_count:    Optional[int] = None
    encoding:      str = "PDF_IMAGE"

    # ── Passage location ─────────────────────────────────────────────────────
    passage_id:  str = ""
    page_number: Optional[int] = None
    entry_id:    str = ""
    line_ids:    List[str] = field(default_factory=list)
    char_start:  Optional[int] = None
    char_end:    Optional[int] = None
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    image_ref:   Optional[str] = None

    # ── Text strata — never overwrite raw_ocr_text ───────────────────────────
    raw_ocr_text:         Optional[str] = None   # immutable after first write
    normalized_text:      Optional[str] = None   # after OCR normalisation
    human_corrected_text: Optional[str] = None   # after human review

    # ── OCR quality ──────────────────────────────────────────────────────────
    ocr_engine:                    Optional[str]   = None
    ocr_pass_id:                   Optional[str]   = None
    ocr_confidence:                Optional[float] = None
    text_review_state:             TextReviewState = TextReviewState.TEXT_CANDIDATE
    passage_checksum:              Optional[str]   = None
    replacement_character_count:   int = 0
    suspected_character_confusions: List[str] = field(default_factory=list)

    # ── Coverage ─────────────────────────────────────────────────────────────
    coverage_state: CoverageState = CoverageState.COVERED

    # ── Helpers ──────────────────────────────────────────────────────────────
    def best_text(self) -> Optional[str]:
        """Highest-confidence text available."""
        return (
            self.human_corrected_text
            or self.normalized_text
            or self.raw_ocr_text
        )

    def text_confidence(self) -> float:
        if self.human_corrected_text:
            return 1.0
        if self.normalized_text:
            return 0.70
        if self.raw_ocr_text:
            base = self.ocr_confidence if self.ocr_confidence is not None else 0.50
            return round(base * 0.60, 3)
        return 0.0

# ══════════════════════════════════════════════════════════════════════════════
# 2. ROOT IDENTITY
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RootIdentityCandidate:
    """
    Root identity as read from the Maqayis entry heading.
    This is a MaqayisRootIdentityCandidate — not a HokomCanonicalRoot.

    Hokom binding fields are filled ONLY after a Hokom call resolves them.
    On CONFLICT or UNRESOLVED: OntologyCandidateProfile must not be built.
    """
    source_root_candidate: str
    candidate_letters:     List[str] = field(default_factory=list)
    root_length_candidate: Optional[int] = None
    source_bab_letter:     Optional[str] = None
    heading_type:          HeadingType = HeadingType.UNCERTAIN

    # ── Hokom binding (filled post-Hokom call) ────────────────────────────────
    hokom_canonical_root_ref: Optional[str] = None
    root_identity_match:      RootIdentityMatch = RootIdentityMatch.UNRESOLVED
    match_confidence:         Optional[float] = None

    # ── Correction record ────────────────────────────────────────────────────
    original_bab_letter:    Optional[str] = None
    corrected_bab_letter:   Optional[str] = None
    correction_reason:      Optional[str] = None
    correction_version:     Optional[str] = None
    correction_review_state: ReviewState = ReviewState.MACHINE_CANDIDATE

    def is_resolved(self) -> bool:
        return self.root_identity_match in (
            RootIdentityMatch.EXACT,
            RootIdentityMatch.NORMALIZED_MATCH,
        )

# ══════════════════════════════════════════════════════════════════════════════
# 3. SOURCE CLAIM RECORD
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SourceClaimRecord:
    """
    Ibn Faris's overall claim about the root — entry-level.
    claim_kind is the entry-level classification.
    Sentence-level claim_type lives in ClaimNode.

    A quoted scholar's claim attributed with REPORTED_ONLY
    is not Ibn Faris's own claim, even if it appears in his text.
    """
    claim_kind:              ClaimKind = ClaimKind.POSITIVE_ORIGIN
    origin_type:             OriginType = OriginType.UNKNOWN
    declared_origin_count:   Optional[int] = None
    origin_count_explicit:   bool = False
    origin_count_expression: Optional[str] = None   # «أصلان صحيحان»

    raw_claim_text:          Optional[str] = None
    normalized_claim_text:   Optional[str] = None
    claim_span_start:        Optional[str] = None   # line_id
    claim_span_end:          Optional[str] = None   # line_id

    assertion_strength:      AssertionStrength = AssertionStrength.UNKNOWN
    claim_attribution:       ClaimAttribution = ClaimAttribution.IBN_FARIS
    attributed_name:         Optional[str] = None
    author_position:         AuthorPosition = AuthorPosition.UNRESOLVED

    claim_scope_language:    str = "CLASSICAL_ARABIC"
    claim_scope_lexical:     str = "ROOT_MATERIAL"

    polarity:                Polarity = Polarity.POSITIVE

# ══════════════════════════════════════════════════════════════════════════════
# 4. ORIGIN RECORDS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SemanticComponent:
    """One component of a compound semantic nucleus."""
    component_id:           str
    label:                  str
    normalized_concept_ref: Optional[str] = None

@dataclass
class CausalProfile:
    causal_role:      CausalRole = CausalRole.NONE_STATED
    cause_target_ref: Optional[str] = None

@dataclass
class LexicalOriginRecord:
    """
    One semantic origin (أصل) as described by Ibn Faris.
    DUAL → two records (origin_index 0 and 1).
    SINGULAR → one record (origin_index 0).

    semantic_nucleus: extracted by priority rule (يدل على → defining sentence
    → first noun). If not extractable → NULL + NUCLEUS_NOT_EXTRACTABLE residual.
    Never fabricated or paraphrased without gloss_method: MACHINE_SUMMARIZED.
    """
    origin_id:    str
    claim_id:     str
    origin_index: int = 0
    origin_type:  OriginType = OriginType.SINGULAR

    # ── Text ──────────────────────────────────────────────────────────────────
    raw_origin_text:        Optional[str] = None
    normalized_origin_text: Optional[str] = None
    verified_origin_text:   Optional[str] = None
    source_span_id:         Optional[str] = None   # line_id where origin starts

    # ── Gloss ─────────────────────────────────────────────────────────────────
    origin_gloss_candidate: Optional[str] = None
    origin_gloss_language:  str = "AR"
    gloss_method:           GlossMethod = GlossMethod.NOT_EXTRACTABLE

    # ── Semantic nucleus ───────────────────────────────────────────────────────
    semantic_nucleus:      Optional[str] = None
    semantic_components:   List[SemanticComponent] = field(default_factory=list)
    component_composition: ComponentComposition = ComponentComposition.UNSPECIFIED

    # ── Semantic classification (all candidates) ───────────────────────────────
    semantic_kind_candidate:    OriginSemanticKind = OriginSemanticKind.UNKNOWN
    abstraction_level:          AbstractionLevel = AbstractionLevel.UNKNOWN
    temporal_profile_candidate: TemporalProfile = TemporalProfile.UNKNOWN
    directionality_candidate:   DirectionalityKind = DirectionalityKind.UNKNOWN
    causal_profile:             CausalProfile = field(default_factory=CausalProfile)

# ══════════════════════════════════════════════════════════════════════════════
# 5. BRANCH RECORDS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BranchRecord:
    """
    One branch (فرع) from a semantic origin.

    hokom_form_analysis_ref is NOT filled by Maqayis — it is filled later
    by Hokom when it analyses the branch's surface form.

    relation_explicitness tracks whether ابن فارس explicitly connected this
    branch or the system inferred it from adjacency.
    """
    branch_id:    str
    origin_id:    str
    origin_index: int = 0
    branch_index: int = 0

    # ── Form ──────────────────────────────────────────────────────────────────
    source_lexical_form:       Optional[str] = None
    vocalized_form:            Optional[str] = None
    normalized_form:           Optional[str] = None
    form_as_written_in_source: Optional[str] = None
    hokom_form_analysis_ref:   Optional[str] = None   # filled by Hokom, not here

    # ── Definition ────────────────────────────────────────────────────────────
    raw_branch_definition:   Optional[str] = None
    normalized_branch_gloss: Optional[str] = None
    branch_sense_candidate:  Optional[str] = None

    # ── Relation ──────────────────────────────────────────────────────────────
    branch_relation_to_origin:    BranchRelation = BranchRelation.UNKNOWN
    relation_explicitness:        RelationExplicitness = RelationExplicitness.SYSTEM_INFERRED
    semantic_distance_candidate:  SemanticDistance = SemanticDistance.UNKNOWN
    regularity:                   Regularity = Regularity.UNKNOWN
    domain_candidate:             DomainCandidate = DomainCandidate.UNKNOWN

# ══════════════════════════════════════════════════════════════════════════════
# 6. USAGE EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class UsageEvidenceRecord:
    """
    A شاهد (witness) — Quranic, hadith, poetry, or author example.

    Supports claims but does not constitute them.
    is_embedded_poetry: True when poetry appears inside a body_line_id
    (quoted in prose) rather than in poetry_line_ids. Embedded poetry
    is NOT excluded — it is included as EvidenceNode with usage_type POETRY.
    """
    usage_id:           str
    usage_text:         str
    usage_type:         UsageType = UsageType.UNKNOWN

    # ── Target span ───────────────────────────────────────────────────────────
    target_expression:  Optional[str] = None
    target_start:       Optional[int] = None
    target_end:         Optional[int] = None

    # ── Source ────────────────────────────────────────────────────────────────
    source_line_id:     Optional[str] = None
    is_embedded_poetry: bool = False   # quoted poetry inside prose body

    # ── Function ──────────────────────────────────────────────────────────────
    witness_function:   Optional[WitnessFunction] = None
    evidence_strength:  EvidenceStrength = EvidenceStrength.ILLUSTRATIVE

    # ── Links ────────────────────────────────────────────────────────────────
    supports_claim_ids: List[str] = field(default_factory=list)

# ══════════════════════════════════════════════════════════════════════════════
# 7. EXTRACTION METADATA
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExtractionMetadata:
    """
    Attached to every extracted artifact.
    Tracks HOW it was found, HOW confident we are, and WHERE it stands in review.

    extraction_confidence: technical confidence that the pattern matched correctly.
    This is NOT epistemic confidence that the interpretation is correct.

    Blocking residuals: ROOT_IDENTITY_CONFLICT, ROOT_IDENTITY_UNRESOLVED,
    MISSING_SOURCE_PASSAGE, TEXT_VERIFICATION_FAILED, INTER_ENTRY_CONFLICT.
    When any of these are present, OntologyCandidateProfile must not be built.
    """
    extraction_method:     ExtractionMethod = ExtractionMethod.RULE_BASED
    explicitness:          Explicitness = Explicitness.EXPLICIT
    extraction_confidence: float = 0.0

    review_state:    ReviewState = ReviewState.MACHINE_CANDIDATE
    evidence_status: EvidenceStatus = EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE

    residuals:           List[ResidualType] = field(default_factory=list)
    counterevidence_ids: List[str] = field(default_factory=list)

    version:       int = 1
    supersedes_id: Optional[str] = None

    def is_ontology_buildable(self) -> bool:
        return not any(r in BLOCKING_RESIDUALS for r in self.residuals)

    def add_residual(self, r: ResidualType) -> None:
        if r not in self.residuals:
            self.residuals.append(r)

# ══════════════════════════════════════════════════════════════════════════════
# 8. LEXICAL CLAIM GRAPH  (Layer 2)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClaimNode:
    """
    One sentence-level claim within the entry (assertion structure).
    claim_type: sentence-level values from existing LexicalClaim taxonomy
                (USAGE_CONDITIONAL, AUTHORITY_CITATION, ETYMOLOGY_ORIGIN, …)
    claim_kind: entry-level context inherited from SourceClaimRecord.

    A ClaimNode ATTRIBUTED_TO a scholar with author_position REPORTED_ONLY
    carries a different epistemic weight than one attributed to IBN_FARIS.
    """
    claim_node_id: str
    claim_type:    str              # sentence-level: existing LexicalClaim.claim_type
    raw_text:      str
    term:          Optional[str] = None
    definition:    Optional[str] = None
    authority:     Optional[str] = None
    origin_index:  int = 0

    assertion_strength: AssertionStrength = AssertionStrength.UNKNOWN
    author_position:    AuthorPosition = AuthorPosition.UNRESOLVED
    extraction_meta:    ExtractionMetadata = field(default_factory=ExtractionMetadata)

@dataclass
class TermNode:
    term_node_id:   str
    lexical_form:   str
    normalized_form: Optional[str] = None

@dataclass
class AuthorityNode:
    authority_node_id: str
    name:              str
    name_normalized:   Optional[str] = None

@dataclass
class EvidenceNode:
    evidence_node_id: str
    text:             str
    usage_type:       UsageType = UsageType.UNKNOWN
    witness_function: Optional[WitnessFunction] = None

@dataclass
class GraphEdge:
    edge_id:   str
    edge_type: str    # value from SemanticOriginEdgeType or LexicalClaimEdgeType
    source_id: str
    target_id: str
    meta:      Optional[str] = None

@dataclass
class LexicalClaimGraph:
    """
    Layer 2 of MaqayisSourceBundle.
    Assertion structure: who said what, backed by what evidence.

    Constraints:
    - ATTRIBUTED_TO requires an explicit name in source text
    - CONTRADICTS requires explicit contradiction, not mere difference
    - A quoted scholar's ClaimNode carries author_position on its edge metadata
    """
    graph_id: str
    entry_id: str

    claim_nodes:     List[ClaimNode]     = field(default_factory=list)
    term_nodes:      List[TermNode]      = field(default_factory=list)
    authority_nodes: List[AuthorityNode] = field(default_factory=list)
    evidence_nodes:  List[EvidenceNode]  = field(default_factory=list)
    edges:           List[GraphEdge]     = field(default_factory=list)

    def claims_by_type(self) -> Dict[str, List[ClaimNode]]:
        result: Dict[str, List[ClaimNode]] = {}
        for c in self.claim_nodes:
            result.setdefault(c.claim_type, []).append(c)
        return result

# ══════════════════════════════════════════════════════════════════════════════
# 9. SEMANTIC ORIGIN GRAPH  (Layer 3)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RootOriginNode:
    node_id:                 str
    origin_index:            int = 0
    raw_text:                Optional[str] = None
    semantic_nucleus:        Optional[str] = None
    semantic_kind_candidate: OriginSemanticKind = OriginSemanticKind.UNKNOWN

@dataclass
class BranchGraphNode:
    node_id:            str
    branch_id:          str
    origin_index:       int = 0
    source_form:        Optional[str] = None
    raw_definition:     Optional[str] = None
    relation_to_origin: BranchRelation = BranchRelation.UNKNOWN

@dataclass
class ExceptionGraphNode:
    node_id:      str
    source_form:  Optional[str] = None
    raw_text:     Optional[str] = None
    origin_index: int = 0

@dataclass
class CrossRefGraphNode:
    node_id:         str
    target_entry_id: str
    raw_text:        Optional[str] = None

@dataclass
class SemanticOriginGraph:
    """
    Layer 3 of MaqayisSourceBundle.
    Meaning structure: which branches come from which origins, and how.

    This is a DAG — validate_dag() must return True.
    SECOND_ORIGIN_OF connects origin[1] → origin[0] in DUAL entries.
    ExceptionNodes use IS_EXCEPTION_OF, never BRANCHES_FROM.
    A BranchNode connects to exactly one RootOriginNode (its origin_index).
    """
    graph_id:  str
    entry_id:  str

    root_origin_nodes: List[RootOriginNode]     = field(default_factory=list)
    branch_nodes:      List[BranchGraphNode]    = field(default_factory=list)
    exception_nodes:   List[ExceptionGraphNode] = field(default_factory=list)
    cross_ref_nodes:   List[CrossRefGraphNode]  = field(default_factory=list)
    edges:             List[GraphEdge]          = field(default_factory=list)

    def validate_dag(self) -> bool:
        """Returns True if the graph contains no directed cycles."""
        adj: Dict[str, List[str]] = {}
        for e in self.edges:
            adj.setdefault(e.source_id, []).append(e.target_id)
        visited: set = set()
        stack:   set = set()

        def dfs(node: str) -> bool:
            if node in stack:
                return False
            if node in visited:
                return True
            stack.add(node)
            for nb in adj.get(node, []):
                if not dfs(nb):
                    return False
            stack.discard(node)
            visited.add(node)
            return True

        all_ids = (
            [n.node_id for n in self.root_origin_nodes]
            + [n.node_id for n in self.branch_nodes]
            + [n.node_id for n in self.exception_nodes]
        )
        return all(dfs(n) for n in all_ids if n not in visited)

# ══════════════════════════════════════════════════════════════════════════════
# 10. ONTOLOGY CANDIDATE PROFILE  (Layer 4)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class GenusCandidateRecord:
    concept_ref:      Optional[str] = None
    evidence_span_id: Optional[str] = None
    confidence:       float = 0.0
    explicitness:     Explicitness = Explicitness.INFERRED

@dataclass
class DifferentiaCandidateRecord:
    label:            str = ""
    relation_to_genus: str = "RESTRICTS"
    evidence_span_id: Optional[str] = None

@dataclass
class PropertyCandidateRecord:
    property_ref:     Optional[str] = None
    property_type:    PropertyType = PropertyType.QUALITY
    attribution_mode: AttributionMode = AttributionMode.UNKNOWN
    gradable:         Gradability = Gradability.UNKNOWN
    persistence:      Persistence = Persistence.UNKNOWN
    bearer_kind:      Optional[str] = None
    evidence_span_id: Optional[str] = None

@dataclass
class ParticipantRoleRecord:
    role:            ParticipantRole = ParticipantRole.AGENT
    type_constraint: Optional[str] = None

@dataclass
class EventProfileCandidateRecord:
    event_kind:   EventKind = EventKind.UNKNOWN
    dynamicity:   Dynamicity = Dynamicity.UNKNOWN
    participant_role_candidates: List[ParticipantRoleRecord] = field(default_factory=list)
    result_state_candidate:      Optional[str] = None

@dataclass
class FunctionCandidateRecord:
    function_type:    str = "INSTRUMENT_FOR"
    target_event_ref: Optional[str] = None
    explicitness:     Explicitness = Explicitness.INFERRED

@dataclass
class RelationCandidateRecord:
    relation_kinds:   List[RelationKind] = field(default_factory=list)
    domain_candidate: Optional[str] = None
    range_candidate:  Optional[str] = None
    arity:            int = 2
    directionality:   str = "DIRECTED"
    symmetric:        Gradability = Gradability.UNKNOWN
    transitive:       Gradability = Gradability.UNKNOWN
    reflexive:        Gradability = Gradability.UNKNOWN
    functional:       Gradability = Gradability.UNKNOWN
    inverse_relation_ref: Optional[str] = None

@dataclass
class MereologyCandidateRecord:
    relation_type: MereologyKind = MereologyKind.UNKNOWN

@dataclass
class CausalRelationCandidateRecord:
    cause_ref:   Optional[str] = None
    effect_ref:  Optional[str] = None
    causal_mode: CausalMode = CausalMode.UNKNOWN

@dataclass
class SimilarityCandidateRecord:
    source_ref: Optional[str] = None
    target_ref: Optional[str] = None
    dimension:  SimilarityDimension = SimilarityDimension.UNKNOWN

@dataclass
class OppositionCandidateRecord:
    opposite_ref:    Optional[str] = None
    opposition_type: OppositionType = OppositionType.UNKNOWN

@dataclass
class SemanticTransferRecord:
    source_concept_ref: Optional[str] = None
    target_concept_ref: Optional[str] = None
    transfer_type:      SemanticTransferType = SemanticTransferType.UNKNOWN
    source_domain:      Optional[str] = None
    target_domain:      Optional[str] = None

@dataclass
class ConceptCandidate:
    """
    One concept candidate built from a LexicalOriginRecord.
    ontology_label is always ONTOLOGY_CANDIDATE_ONLY.
    This is never a licensed ontological fact.
    """
    concept_candidate_id:  str
    lexical_origin_ref:    str
    ontology_label:        str = ONTOLOGY_CANDIDATE_ONLY

    preferred_arabic_label: Optional[str] = None
    alternative_labels:     List[str] = field(default_factory=list)
    definition_candidate:   Optional[str] = None

    upper_kind_candidate: UpperKindCandidate = UpperKindCandidate.UNKNOWN

    genus_candidates:           List[GenusCandidateRecord]          = field(default_factory=list)
    differentia_candidates:     List[DifferentiaCandidateRecord]    = field(default_factory=list)
    property_candidates:        List[PropertyCandidateRecord]       = field(default_factory=list)
    event_profile_candidate:    Optional[EventProfileCandidateRecord] = None
    function_candidates:        List[FunctionCandidateRecord]       = field(default_factory=list)
    relation_candidates:        List[RelationCandidateRecord]       = field(default_factory=list)
    mereology_candidate:        Optional[MereologyCandidateRecord]  = None
    causal_relation_candidate:  Optional[CausalRelationCandidateRecord] = None
    similarity_candidates:      List[SimilarityCandidateRecord]    = field(default_factory=list)
    opposition_candidates:      List[OppositionCandidateRecord]    = field(default_factory=list)
    semantic_transfer_candidates: List[SemanticTransferRecord]     = field(default_factory=list)

@dataclass
class OntologyCandidateProfile:
    """
    Layer 4 of MaqayisSourceBundle.
    All ontological interpretations — every field is a candidate, never a fact.

    NOT built when root_identity_match is CONFLICT or UNRESOLVED.
    NOT built when any BLOCKING_RESIDUAL is present in extraction_meta.
    """
    profile_id:    str
    entry_id:      str
    ontology_label: str = ONTOLOGY_CANDIDATE_ONLY

    concept_candidates: List[ConceptCandidate] = field(default_factory=list)
    extraction_meta:    ExtractionMetadata = field(default_factory=ExtractionMetadata)

# ══════════════════════════════════════════════════════════════════════════════
# 11. TOP-LEVEL BUNDLES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MaqayisSourceBundle:
    """
    Complete knowledge package for one Maqayis lexical entry.

    Four layers in strict dependency order:
      1. SourceEvidence             — provenance, text strata, OCR quality
      2. LexicalClaimGraph          — assertion structure (who said what)
      3. SemanticOriginGraph        — meaning structure (what branches from what)
      4. OntologyCandidateProfile   — candidate ontological interpretation

    Layers 2–4 require Layer 1 to exist.
    Layer 4 requires root_identity.is_resolved() and no blocking residuals.

    entry_kind determines the pipeline path:
      ROOT_ENTRY      → full pipeline
      CHAPTER_HEADER  → SourceEvidence only
      CROSS_REFERENCE → SourceEvidence + LexicalClaimGraph (claim_kind=CROSS_REFERENCE)
      NONE origin     → SourceEvidence + residual ORIGIN_NOT_EXTRACTABLE
    """
    bundle_id: str
    entry_id:  str

    # Layer 1
    source_evidence: Optional[SourceEvidence] = None

    # Identity — precondition for layers 2–4
    root_identity: Optional[RootIdentityCandidate] = None
    source_claim:  Optional[SourceClaimRecord] = None
    entry_kind:    EntryKind = EntryKind.ROOT_ENTRY

    # Sub-records (inputs to graph builders)
    origins:        List[LexicalOriginRecord]  = field(default_factory=list)
    branches:       List[BranchRecord]         = field(default_factory=list)
    usage_evidence: List[UsageEvidenceRecord]  = field(default_factory=list)

    # Layer 2
    lexical_claim_graph:   Optional[LexicalClaimGraph]       = None

    # Layer 3
    semantic_origin_graph: Optional[SemanticOriginGraph]     = None

    # Layer 4
    ontology_candidate_profile: Optional[OntologyCandidateProfile] = None

    # Bundle-level metadata
    extraction_meta: ExtractionMetadata = field(default_factory=ExtractionMetadata)

    def is_ontology_buildable(self) -> bool:
        if self.root_identity is None:
            return False
        if not self.root_identity.is_resolved():
            return False
        return self.extraction_meta.is_ontology_buildable()

    def layer_summary(self) -> Dict[str, object]:
        return {
            "entry_kind":                   self.entry_kind.value,
            "source_evidence":              self.source_evidence is not None,
            "root_identity_match":          (
                self.root_identity.root_identity_match.value
                if self.root_identity else None
            ),
            "source_claim_kind":            (
                self.source_claim.claim_kind.value
                if self.source_claim else None
            ),
            "origins":                      len(self.origins),
            "branches":                     len(self.branches),
            "usage_evidence":               len(self.usage_evidence),
            "lexical_claim_graph":          self.lexical_claim_graph is not None,
            "semantic_origin_graph":        self.semantic_origin_graph is not None,
            "ontology_candidate_profile":   self.ontology_candidate_profile is not None,
            "ontology_buildable":           self.is_ontology_buildable(),
            "residuals":                    [r.value for r in self.extraction_meta.residuals],
        }

@dataclass
class RootKnowledgeBundle:
    """
    Aggregation of all MaqayisSourceBundle objects for the same canonical root.

    No silent merging — all source bundles are preserved independently.
    primary_entry_id: entry with POSITIVE_ORIGIN claim_kind and most body lines.
    On INTER_ENTRY_CONFLICT: OntologyCandidateProfile is not merged;
    each bundle retains its own profile with CONFLICT_PENDING review_state.
    """
    bundle_id:                str
    hokom_canonical_root_ref: str

    primary_entry_id:    Optional[str] = None
    secondary_entry_ids: List[str] = field(default_factory=list)

    source_bundles:   List[MaqayisSourceBundle] = field(default_factory=list)
    conflict_log:     List[str] = field(default_factory=list)
    aggregation_state: AggregationState = AggregationState.SINGLE_SOURCE

    def register(self, bundle: MaqayisSourceBundle) -> None:
        self.source_bundles.append(bundle)
        all_ids = [b.entry_id for b in self.source_bundles]
        if len(all_ids) > 1:
            self.secondary_entry_ids = all_ids[1:]
            self.aggregation_state = (
                AggregationState.CONFLICTING_MULTI
                if self.conflict_log
                else AggregationState.CONSISTENT_MULTI
            )
