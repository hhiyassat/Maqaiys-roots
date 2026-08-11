"""
maqayis_constitutional_schemas.py — Constitutional Source Lexicon Schemas
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01  Commit 1

All dataclasses, enums, and transition contract interfaces for the
Maqayis Constitutional Lexical Knowledge Graph.

Design Principles
─────────────────
• Immutable records only (frozen=True on all dataclasses)
• Version_n+1 = Revision(Version_n) — never destructive overwrite
• Machine operations cannot produce IDENTITY_VERIFIED, TEXT_VERIFIED,
  LEXICALLY_REVIEWED, or AUDIT_PASSED evidence
• AUTO_AGREED from legacy corpus → MACHINE_CANDIDATE (never VERIFIED)
• REVIEW_REQUIRED from legacy corpus → UNVERIFIED_REVIEW_REQUIRED
• Fail-open for Taaqol admission — this layer is supplementary only

Evidence Status Ranking (ascending certainty)
──────────────────────────────────────────────
MACHINE_SOURCE_CLAIM_CANDIDATE
  < SOURCE_LOCATED_EVIDENCE
  < IDENTITY_VERIFIED_EVIDENCE
  < TEXT_VERIFIED_EVIDENCE
  < ORIGIN_SEGMENTED_EVIDENCE
  < LEXICALLY_REVIEWED_EVIDENCE

Stage-0 Supplementary Constraints
───────────────────────────────────
Maqayis constitutional evidence MUST NOT:
  • approve admission independently
  • increase token rank
  • suppress residual codes
  • assert roots not licensed by Hokom's morphological chain
  • infer sentence relation, maqam, produce Ifadah/Hukm/Manat/Tanzil/AnswerAudit
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Sequence, FrozenSet


# ═══════════════════════════════════════════════════════════════════════════════
# § 1 — ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class LookupResultKind(enum.Enum):
    """
    11-kind typed lookup result for constitutional registry.

    Found kinds (5):
        FOUND_MACHINE_CANDIDATE_ONLY       — legacy import only; no human review
        FOUND_IDENTITY_CANDIDATE           — identity candidate extracted
        FOUND_IDENTITY_VERIFIED            — root identity human-verified
        FOUND_TEXT_VERIFIED                — source text human-verified
        FOUND_LEXICALLY_REVIEWED           — full lexical review passed

    Conflict kinds (2):
        FOUND_CONFLICT_REVIEW_REQUIRED     — conflicting claims for same root
        FOUND_REVIEW_REQUIRED_UNRESOLVED   — REVIEW_REQUIRED from legacy, no upgrade

    Gap / absence kinds (4):
        MISSING_VOLUME_COVERAGE_GAP        — initial in missing volumes (ا ب ت ث ج)
        NOT_FOUND_IN_COVERED_VOLUME        — covered volume, root absent
        REGISTRY_LOAD_FAILURE              — full load failed
        REGISTRY_PARTIAL_LOAD             — some volumes loaded, some failed
    """
    FOUND_MACHINE_CANDIDATE_ONLY        = "FOUND_MACHINE_CANDIDATE_ONLY"
    FOUND_IDENTITY_CANDIDATE            = "FOUND_IDENTITY_CANDIDATE"
    FOUND_IDENTITY_VERIFIED             = "FOUND_IDENTITY_VERIFIED"
    FOUND_TEXT_VERIFIED                 = "FOUND_TEXT_VERIFIED"
    FOUND_LEXICALLY_REVIEWED            = "FOUND_LEXICALLY_REVIEWED"
    FOUND_CONFLICT_REVIEW_REQUIRED      = "FOUND_CONFLICT_REVIEW_REQUIRED"
    FOUND_REVIEW_REQUIRED_UNRESOLVED    = "FOUND_REVIEW_REQUIRED_UNRESOLVED"
    MISSING_VOLUME_COVERAGE_GAP         = "MISSING_VOLUME_COVERAGE_GAP"
    NOT_FOUND_IN_COVERED_VOLUME         = "NOT_FOUND_IN_COVERED_VOLUME"
    REGISTRY_LOAD_FAILURE               = "REGISTRY_LOAD_FAILURE"
    REGISTRY_PARTIAL_LOAD               = "REGISTRY_PARTIAL_LOAD"


class ReviewState(enum.Enum):
    """
    16 review states forming the canonical upgrade path for a root record.

    Upgrade path (strictly ordered):
        UNREVIEWED
          → MACHINE_CANDIDATE            (auto import)
          → UNVERIFIED_REVIEW_REQUIRED   (flagged for review)
          → SOURCE_LOCATED               (PDF page identified)
          → IDENTITY_CANDIDATE           (candidate extracted)
          → IDENTITY_CONFLICT            (conflicts detected — must resolve)
          → IDENTITY_VERIFIED            (human verified root letters)
          → TEXT_CANDIDATE               (raw passage extracted)
          → TEXT_CONFLICT                (text conflicts detected)
          → TEXT_VERIFIED                (text confirmed by reviewer)
          → ORIGIN_CANDIDATE             (origin claim extracted)
          → ORIGIN_CONFLICT              (origin conflicts detected)
          → ORIGIN_SEGMENTED             (DUAL/TRIPLE/MULTIPLE split)
          → LEXICAL_REVIEW_IN_PROGRESS   (active review session)
          → LEXICALLY_REVIEWED           (review complete)
          → AUDIT_PASSED                 (independent audit passed)

    States marked HUMAN_REQUIRED cannot be set by machine operations.
    """
    UNREVIEWED                  = "UNREVIEWED"
    MACHINE_CANDIDATE           = "MACHINE_CANDIDATE"
    UNVERIFIED_REVIEW_REQUIRED  = "UNVERIFIED_REVIEW_REQUIRED"
    SOURCE_LOCATED              = "SOURCE_LOCATED"
    IDENTITY_CANDIDATE          = "IDENTITY_CANDIDATE"
    IDENTITY_CONFLICT           = "IDENTITY_CONFLICT"
    IDENTITY_VERIFIED           = "IDENTITY_VERIFIED"
    TEXT_CANDIDATE              = "TEXT_CANDIDATE"
    TEXT_CONFLICT               = "TEXT_CONFLICT"
    TEXT_VERIFIED               = "TEXT_VERIFIED"
    ORIGIN_CANDIDATE            = "ORIGIN_CANDIDATE"
    ORIGIN_CONFLICT             = "ORIGIN_CONFLICT"
    ORIGIN_SEGMENTED            = "ORIGIN_SEGMENTED"
    LEXICAL_REVIEW_IN_PROGRESS  = "LEXICAL_REVIEW_IN_PROGRESS"
    LEXICALLY_REVIEWED          = "LEXICALLY_REVIEWED"
    AUDIT_PASSED                = "AUDIT_PASSED"


# States that can only be set by a human reviewer
HUMAN_REQUIRED_STATES: FrozenSet[ReviewState] = frozenset({
    ReviewState.IDENTITY_VERIFIED,
    ReviewState.TEXT_VERIFIED,
    ReviewState.LEXICAL_REVIEW_IN_PROGRESS,
    ReviewState.LEXICALLY_REVIEWED,
    ReviewState.AUDIT_PASSED,
})


class EvidenceStatus(enum.Enum):
    """
    Evidence certainty ranking (ascending).
    Higher rank = greater certainty about the lexical claim.
    Machine operations cannot produce ranks above ORIGIN_SEGMENTED_EVIDENCE.
    """
    MACHINE_SOURCE_CLAIM_CANDIDATE  = 0
    SOURCE_LOCATED_EVIDENCE         = 1
    IDENTITY_VERIFIED_EVIDENCE      = 2
    TEXT_VERIFIED_EVIDENCE          = 3
    ORIGIN_SEGMENTED_EVIDENCE       = 4
    LEXICALLY_REVIEWED_EVIDENCE     = 5

    def __lt__(self, other: "EvidenceStatus") -> bool:
        return self.value < other.value

    def __le__(self, other: "EvidenceStatus") -> bool:
        return self.value <= other.value


# Machine operations may not produce evidence above this rank
MACHINE_EVIDENCE_CEILING = EvidenceStatus.ORIGIN_SEGMENTED_EVIDENCE


class OriginType(enum.Enum):
    """
    Lexical origin claim types, as extracted from Ibn Faris's text.

    Compound types (DUAL, TRIPLE, MULTIPLE) require segmentation into
    separate LexicalOriginCandidate records before reaching ORIGIN_SEGMENTED.
    """
    SINGULAR        = "SINGULAR"        # واحد أصل
    DUAL            = "DUAL"            # أصلان
    TRIPLE          = "TRIPLE"          # ثلاثة أصول
    MULTIPLE        = "MULTIPLE"        # أصول متعددة
    SOUND_ROOTS     = "SOUND_ROOTS"     # أصول صحيحة
    NONE            = "NONE"            # لا أصل له / ليس من كلامهم
    UNKNOWN         = "UNKNOWN"         # not extractable
    NOT_EXTRACTED   = "NOT_EXTRACTED"   # OCR extraction failed


class ClaimKind(enum.Enum):
    """
    Kind of lexical claim made by Ibn Faris about a root.
    """
    POSITIVE_ORIGIN     = "POSITIVE_ORIGIN"     # root exists, origin stated
    NEGATIVE_CLAIM      = "NEGATIVE_CLAIM"      # explicitly: لا أصل له
    DERIVATION_CLAIM    = "DERIVATION_CLAIM"    # derived from / related to
    LOAN_WORD_CLAIM     = "LOAN_WORD_CLAIM"     # دخيل / معرَّب
    DISPUTED_CLAIM      = "DISPUTED_CLAIM"      # يُختلف فيه
    INCOMPLETE_CLAIM    = "INCOMPLETE_CLAIM"    # text cut off / unclear
    CHAPTER_HEADER      = "CHAPTER_HEADER"      # OCR noise: chapter heading
    CROSS_REFERENCE     = "CROSS_REFERENCE"     # see: انظر
    NOT_ROOT_ENTRY      = "NOT_ROOT_ENTRY"      # OCR noise: not a root entry


class RootClass(enum.Enum):
    """
    Morphological root class (from Hokom, not derived by Maqayis layer).
    Maqayis may only assert roots licensed by Hokom's canonical_root.
    """
    TRILATERAL_SOUND    = "TRILATERAL_SOUND"    # ثلاثي صحيح
    TRILATERAL_HAMZATED = "TRILATERAL_HAMZATED" # ثلاثي مهموز
    TRILATERAL_WEAK     = "TRILATERAL_WEAK"     # ثلاثي معتل
    TRILATERAL_DOUBLED  = "TRILATERAL_DOUBLED"  # ثلاثي مضاعف
    QUADRILATERAL       = "QUADRILATERAL"       # رباعي
    QUINQUILATERAL      = "QUINQUILATERAL"      # خماسي
    UNKNOWN             = "UNKNOWN"


class KnowledgeType(enum.Enum):
    """
    7 knowledge types for evidence classification.
    Determines which downstream systems may use a given evidence record.
    """
    LEXICAL_ORIGIN          = "LEXICAL_ORIGIN"          # ibn faris origin claim
    ROOT_IDENTITY           = "ROOT_IDENTITY"           # root letter identity
    SOURCE_LOCATION         = "SOURCE_LOCATION"         # PDF page + volume
    BAB_CLASSIFICATION      = "BAB_CLASSIFICATION"      # chapter classification
    MORPHOLOGICAL_CLASS     = "MORPHOLOGICAL_CLASS"     # root class
    REVIEW_CERTIFICATION    = "REVIEW_CERTIFICATION"    # human review record
    CORPUS_PROVENANCE       = "CORPUS_PROVENANCE"       # OCR + correction history


class ResidualType(enum.Enum):
    """
    Types of unresolved issues tracked as Residuals.
    """
    OCR_AMBIGUITY               = "OCR_AMBIGUITY"
    ROOT_IDENTITY_CONFLICT      = "ROOT_IDENTITY_CONFLICT"
    ORIGIN_CLAIM_CONFLICT       = "ORIGIN_CLAIM_CONFLICT"
    MISSING_SOURCE_PASSAGE      = "MISSING_SOURCE_PASSAGE"
    SEGMENTATION_REQUIRED       = "SEGMENTATION_REQUIRED"
    BAB_DERIVATION_UNKNOWN      = "BAB_DERIVATION_UNKNOWN"
    REVIEW_REQUIRED_UNRESOLVED  = "REVIEW_REQUIRED_UNRESOLVED"
    VOLUME_COVERAGE_GAP         = "VOLUME_COVERAGE_GAP"
    TEXT_VERIFICATION_FAILED    = "TEXT_VERIFICATION_FAILED"
    AUDIT_DISCREPANCY           = "AUDIT_DISCREPANCY"
    ORIGIN_NOT_EXTRACTED        = "ORIGIN_NOT_EXTRACTED"


class ReviewerType(enum.Enum):
    """
    Reviewer type — determines which evidence ranks are reachable.
    MACHINE_ONLY cannot produce IDENTITY_VERIFIED or above.
    """
    MACHINE_ONLY        = "MACHINE_ONLY"
    HUMAN_REVIEWER      = "HUMAN_REVIEWER"
    HUMAN_AUDITOR       = "HUMAN_AUDITOR"   # independent second reviewer
    SENIOR_LEXICOGRAPHER = "SENIOR_LEXICOGRAPHER"


class TraceEventKind(enum.Enum):
    """
    Kind of immutable trace event.
    """
    IMPORT                  = "IMPORT"
    PARSE                   = "PARSE"
    BAB_CORRECTION          = "BAB_CORRECTION"
    IDENTITY_EXTRACTED      = "IDENTITY_EXTRACTED"
    IDENTITY_CONFLICT       = "IDENTITY_CONFLICT"
    IDENTITY_VERIFIED       = "IDENTITY_VERIFIED"
    TEXT_EXTRACTED          = "TEXT_EXTRACTED"
    TEXT_CONFLICT           = "TEXT_CONFLICT"
    TEXT_VERIFIED           = "TEXT_VERIFIED"
    ORIGIN_EXTRACTED        = "ORIGIN_EXTRACTED"
    ORIGIN_SEGMENTED        = "ORIGIN_SEGMENTED"
    ORIGIN_CONFLICT         = "ORIGIN_CONFLICT"
    REVIEW_STARTED          = "REVIEW_STARTED"
    REVIEW_COMPLETED        = "REVIEW_COMPLETED"
    AUDIT_PASSED            = "AUDIT_PASSED"
    SUPERSEDED              = "SUPERSEDED"
    RESIDUAL_CREATED        = "RESIDUAL_CREATED"
    RESIDUAL_RESOLVED       = "RESIDUAL_RESOLVED"


# ═══════════════════════════════════════════════════════════════════════════════
# § 2 — DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SourceRecord:
    """
    A Maqayis al-Lugha source document (one PDF volume).

    id                  : stable identifier, e.g. "maqayis:source:vol1"
    volume_number       : 1–6
    filename            : original PDF filename
    sha256              : content hash of PDF
    page_count          : total pages
    ocr_pass_count      : number of OCR passes completed
    is_missing_volume   : True if this volume is absent from the corpus
                          (covers initials ا ب ت ث ج)
    initial_letters     : Arabic initial letters this volume covers
    """
    id:                 str
    volume_number:      int
    filename:           str
    sha256:             str
    page_count:         int
    ocr_pass_count:     int
    is_missing_volume:  bool
    initial_letters:    tuple[str, ...]
    pdf_sha256:         str = ""

    def __post_init__(self) -> None:
        if self.volume_number < 1 or self.volume_number > 6:
            raise ValueError(f"volume_number must be 1–6, got {self.volume_number}")


@dataclass(frozen=True)
class SourcePassage:
    """
    A raw OCR passage from a SourceRecord, corresponding to one root entry.

    id                      : stable identifier, e.g. "maqayis:passage:حدد:vol1:p42"
    source_id               : foreign key → SourceRecord.id
    page_number             : PDF page number
    raw_passage_candidate   : raw OCR text (NOT a definition — this is the
                              heading/passage as extracted; it is a CANDIDATE
                              until TEXT_VERIFIED)
    corrected_passage       : human-corrected passage (None until TEXT_VERIFIED)
    ocr_confidence          : 0.0–1.0 confidence from OCR pass
    review_state            : current review state
    evidence_status         : current evidence status
    supersedes_id           : id of the record this supersedes (None if first)
    """
    id:                     str
    source_id:              str
    page_number:            int
    raw_passage_candidate:  str
    corrected_passage:      Optional[str]
    ocr_confidence:         float
    review_state:           ReviewState
    evidence_status:        EvidenceStatus
    supersedes_id:          Optional[str] = None
    entry_id:               str                                         = ""
    source_pdf:             str                                         = ""
    line_ids:               tuple[str, ...]                             = field(default_factory=tuple)
    offsets:                tuple[int, ...]                             = field(default_factory=tuple)
    bounding_box:           Optional[tuple[float, float, float, float]] = None
    context:                Optional[str]                               = None
    image_ref:              Optional[str]                               = None
    passage_checksum:       str                                         = ""


@dataclass(frozen=True)
class RootIdentityCandidate:
    """
    A candidate root identity extracted from a SourcePassage.
    Not verified — may contain OCR errors.

    id                  : stable identifier
    passage_id          : foreign key → SourcePassage.id
    candidate_letters   : raw extracted root letters (may contain OCR noise)
    normalized_letters  : Hamza-normalized for coverage check ONLY
                          (stored data is never modified)
    bab_letter          : corrected bab letter derived from first radical
    original_bab_letter : bab letter as found in source
    bab_correction_version : provenance of bab correction
    ocr_gate_flags      : dict of OCR confusion gate names → True/False
                          (True = flag raised = potential OCR error)
    review_state        : current review state
    evidence_status     : current evidence status
    supersedes_id       : None if first version
    """
    id:                         str
    passage_id:                 str
    candidate_letters:          str
    normalized_letters:         str
    bab_letter:                 str
    original_bab_letter:        str
    bab_correction_version:     str
    ocr_gate_flags:             tuple[tuple[str, bool], ...]
    review_state:               ReviewState
    evidence_status:            EvidenceStatus
    supersedes_id:              Optional[str] = None

    @property
    def has_ocr_flags(self) -> bool:
        return any(v for _, v in self.ocr_gate_flags)

    @property
    def flagged_gates(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.ocr_gate_flags if v)


@dataclass(frozen=True)
class RootIdentityCarrier:
    """
    A verified root identity — human-confirmed, may serve as authority.

    id                  : stable identifier
    candidate_id        : foreign key → RootIdentityCandidate.id
    verified_letters    : confirmed root letters (authoritative)
    root_class          : morphological class (from Hokom if known, else UNKNOWN)
    reviewer_type       : HUMAN_REVIEWER or above (never MACHINE_ONLY)
    reviewer_id         : reviewer identifier
    verified_at         : ISO-8601 timestamp
    review_state        : IDENTITY_VERIFIED or above
    evidence_status     : IDENTITY_VERIFIED_EVIDENCE or above
    supersedes_id       : None if first version
    """
    id:                 str
    candidate_id:       str
    verified_letters:   str
    root_class:         RootClass
    reviewer_type:      ReviewerType
    reviewer_id:        str
    verified_at:        str
    review_state:       ReviewState
    evidence_status:    EvidenceStatus
    supersedes_id:      Optional[str] = None

    def __post_init__(self) -> None:
        if self.reviewer_type == ReviewerType.MACHINE_ONLY:
            raise ValueError(
                "RootIdentityCarrier cannot be produced by MACHINE_ONLY reviewer. "
                "Machine operations produce RootIdentityCandidate only."
            )
        if self.evidence_status < EvidenceStatus.IDENTITY_VERIFIED_EVIDENCE:
            raise ValueError(
                f"RootIdentityCarrier requires evidence_status >= IDENTITY_VERIFIED_EVIDENCE, "
                f"got {self.evidence_status}"
            )


@dataclass(frozen=True)
class SourceRootClaim:
    """
    Ibn Faris's claim about a root as extracted from the source text.

    id                  : stable identifier
    passage_id          : foreign key → SourcePassage.id
    identity_id         : foreign key → RootIdentityCandidate.id or
                          RootIdentityCarrier.id (depending on review_state)
    claim_kind          : what kind of claim is being made
    origin_type         : SINGULAR / DUAL / TRIPLE / MULTIPLE / SOUND_ROOTS / NONE
    raw_claim_text      : verbatim excerpt of the claim from the passage
    review_state        : current review state
    evidence_status     : current evidence status
    extraction_method   : "MACHINE_OCR" / "HUMAN_EXTRACTION"
    supersedes_id       : None if first version
    """
    id:                 str
    passage_id:         str
    identity_id:        str
    claim_kind:         ClaimKind
    origin_type:        OriginType
    raw_claim_text:     str
    review_state:       ReviewState
    evidence_status:    EvidenceStatus
    extraction_method:  str
    supersedes_id:      Optional[str] = None

    @property
    def requires_segmentation(self) -> bool:
        """True if origin_type has multiple origins that must be split."""
        return self.origin_type in (
            OriginType.DUAL,
            OriginType.TRIPLE,
            OriginType.MULTIPLE,
        )


@dataclass(frozen=True)
class LexicalOriginCandidate:
    """
    One extracted lexical origin from a SourceRootClaim.

    For SINGULAR claims: one candidate per claim.
    For DUAL claims: two candidates (origin_index 0 and 1).
    For TRIPLE claims: three candidates (origin_index 0, 1, 2).
    For MULTIPLE claims: N candidates (N determined by extraction).

    id                  : stable identifier
    claim_id            : foreign key → SourceRootClaim.id
    identity_id         : foreign key → RootIdentityCandidate/Carrier.id
    origin_index        : 0-based index within the claim (0 for SINGULAR)
    origin_type         : the specific origin type for THIS candidate
                          (always SINGULAR after segmentation)
    origin_description  : brief description of this origin
    raw_origin_text     : verbatim excerpt for this origin from the passage
    review_state        : current review state
    evidence_status     : current evidence status
    extraction_method   : "MACHINE_OCR" / "HUMAN_EXTRACTION"
    supersedes_id       : None if first version
    """
    id:                 str
    claim_id:           str
    identity_id:        str
    origin_index:       int
    origin_type:        OriginType
    origin_description: str
    raw_origin_text:    str
    review_state:       ReviewState
    evidence_status:    EvidenceStatus
    extraction_method:  str
    supersedes_id:      Optional[str] = None


@dataclass(frozen=True)
class ReviewCertificate:
    """
    A human review certification for any record type.

    id                  : stable identifier
    target_id           : id of the record being reviewed
    target_type         : e.g. "RootIdentityCandidate", "SourceRootClaim"
    reviewer_type       : type of reviewer
    reviewer_id         : reviewer identifier
    review_state_before : state before this review
    review_state_after  : state after this review
    evidence_status_after : evidence status after this review
    notes               : reviewer's notes (may be empty)
    reviewed_at         : ISO-8601 timestamp
    supersedes_id       : None if first version (a review is never deleted,
                          only superseded by a new review)
    """
    id:                     str
    target_id:              str
    target_type:            str
    reviewer_type:          ReviewerType
    reviewer_id:            str
    review_state_before:    ReviewState
    review_state_after:     ReviewState
    evidence_status_after:  EvidenceStatus
    notes:                  str
    reviewed_at:            str
    supersedes_id:          Optional[str] = None

    def __post_init__(self) -> None:
        if self.reviewer_type == ReviewerType.MACHINE_ONLY:
            if self.review_state_after in HUMAN_REQUIRED_STATES:
                raise ValueError(
                    f"MACHINE_ONLY reviewer cannot set state {self.review_state_after}. "
                    f"Human-required states: {HUMAN_REQUIRED_STATES}"
                )


@dataclass(frozen=True)
class Residual:
    """
    An unresolved issue attached to a record, blocking state upgrade.

    id                  : stable identifier
    target_id           : id of the blocked record
    target_type         : type of the blocked record
    residual_type       : kind of unresolved issue
    description         : human-readable description
    blocking_until      : ReviewState that cannot be reached until resolved
    created_at          : ISO-8601 timestamp
    resolved_at         : ISO-8601 timestamp if resolved, else None
    resolved_by         : reviewer_id if resolved, else None
    resolution_notes    : notes when resolved
    supersedes_id       : None if first version
    """
    id:                 str
    target_id:          str
    target_type:        str
    residual_type:      ResidualType
    description:        str
    blocking_until:     ReviewState
    created_at:         str
    resolved_at:        Optional[str] = None
    resolved_by:        Optional[str] = None
    resolution_notes:   Optional[str] = None
    supersedes_id:      Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


@dataclass(frozen=True)
class TraceEvent:
    """
    An immutable trace event in the audit trail.

    Every operation (import/parse/correction/review/supersession) MUST
    produce a TraceEvent. Events are append-only — never deleted or modified.

    id                  : stable identifier
    kind                : TraceEventKind
    target_id           : id of the affected record
    target_type         : type of the affected record
    actor_type          : ReviewerType of the actor
    actor_id            : actor identifier (script name or reviewer id)
    occurred_at         : ISO-8601 timestamp
    summary             : brief human-readable description
    metadata            : arbitrary key-value pairs for debugging
    """
    id:             str
    kind:           TraceEventKind
    target_id:      str
    target_type:    str
    actor_type:     ReviewerType
    actor_id:       str
    occurred_at:    str
    summary:        str
    metadata:       tuple[tuple[str, str], ...] = field(default_factory=tuple)


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — LEGACY IMPORT BRIDGE TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LegacyCandidateImport:
    """
    Bridge record mapping a legacy root_entries JSONL entry to
    constitutional entity IDs.

    CRITICAL MAPPING RULES:
    • legacy review_status AUTO_AGREED   → initial_review_state = MACHINE_CANDIDATE
    • legacy review_status REVIEW_REQUIRED → initial_review_state = UNVERIFIED_REVIEW_REQUIRED
    • AUTO_AGREED NEVER maps to IDENTITY_VERIFIED, TEXT_VERIFIED, or LEXICALLY_REVIEWED
    • legacy heading_sample → SourcePassage.raw_passage_candidate (NOT a definition)
    • origin_count is informational only — not an evidence claim

    Fields:
    legacy_root_letters         : root letters from original JSONL
    legacy_review_status        : "AUTO_AGREED" or "REVIEW_REQUIRED"
    legacy_semantic_origin_type : SINGULAR / DUAL / etc. from OCR
    legacy_origin_count         : count from OCR (may be None)
    legacy_bab_letter           : bab letter as stored in JSONL
    legacy_corrected_bab_letter : corrected bab from maqayis_bab_corrector
    legacy_original_bab_letter  : original bab before correction
    legacy_correction_version   : "v1" or later
    legacy_source_pdfs          : PDFs this entry appears in
    initial_review_state        : ReviewState assigned on import
    initial_evidence_status     : always MACHINE_SOURCE_CLAIM_CANDIDATE
    candidate_id                : assigned RootIdentityCandidate.id
    passage_id                  : assigned SourcePassage.id
    claim_id                    : assigned SourceRootClaim.id
    import_trace_id             : TraceEvent.id for this import
    requires_segmentation       : True if DUAL/TRIPLE/MULTIPLE
    noise_entry                 : True if NOT_ROOT, CHAPTER_HEADER, CROSS_REFERENCE
    -- Real source provenance fields (§3/§4) --
    legacy_heading_text         : actual OCR heading text from root_heading_text field
    legacy_origin_text          : actual semantic origin text from semantic_origin_text field
    legacy_entry_id             : entry_id from JSONL (e.g. "01.pdf:p44:r001")
    legacy_source_pdf           : source_pdf field from JSONL (e.g. "01.pdf")
    legacy_pdf_page             : pdf_page field from JSONL
    legacy_line_ids             : line_ids referencing per-page OCR lines
    """
    legacy_root_letters:            str
    legacy_review_status:           str
    legacy_semantic_origin_type:    str
    legacy_origin_count:            Optional[int]
    legacy_bab_letter:              str
    legacy_corrected_bab_letter:    str
    legacy_original_bab_letter:     str
    legacy_correction_version:      str
    legacy_source_pdfs:             tuple[str, ...]
    initial_review_state:           ReviewState
    initial_evidence_status:        EvidenceStatus
    candidate_id:                   str
    passage_id:                     str
    claim_id:                       str
    import_trace_id:                str
    requires_segmentation:          bool
    noise_entry:                    bool
    # Real source provenance fields — default to empty for backward compat
    legacy_heading_text:            str               = ""
    legacy_origin_text:             Optional[str]     = None
    legacy_entry_id:                str               = ""
    legacy_source_pdf:              str               = ""
    legacy_pdf_page:                int               = 0
    legacy_line_ids:                tuple[str, ...]   = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Enforce the critical mapping rule: AUTO_AGREED → MACHINE_CANDIDATE only
        if self.legacy_review_status == "AUTO_AGREED":
            if self.initial_review_state not in (
                ReviewState.MACHINE_CANDIDATE,
            ):
                raise ValueError(
                    f"AUTO_AGREED must map to MACHINE_CANDIDATE, "
                    f"got {self.initial_review_state}. "
                    f"AUTO_AGREED MUST NEVER map to IDENTITY_VERIFIED, "
                    f"TEXT_VERIFIED, or LEXICALLY_REVIEWED."
                )
        # Enforce evidence ceiling
        if self.initial_evidence_status != EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE:
            raise ValueError(
                f"Legacy import initial_evidence_status must be "
                f"MACHINE_SOURCE_CLAIM_CANDIDATE, got {self.initial_evidence_status}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# § 4 — CONSTITUTIONAL LOOKUP RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ConstitutionalLookupResult:
    """
    Typed lookup result from the constitutional registry.

    Replaces the legacy LookupResult with 11-kind precision.
    Carries full evidence chain, not just entry data.

    kind                : LookupResultKind (11 options)
    root_letters        : queried root letters
    identity_candidate  : RootIdentityCandidate if found
    identity_carrier    : RootIdentityCarrier if IDENTITY_VERIFIED or above
    claims              : all SourceRootClaims for this root
    origin_candidates   : all LexicalOriginCandidates
    residuals           : open Residuals for this root
    evidence_status     : highest achieved EvidenceStatus
    review_state        : current ReviewState
    conflict_notes      : description of conflict if FOUND_CONFLICT_REVIEW_REQUIRED
    coverage_note       : description of coverage gap if MISSING_VOLUME_COVERAGE_GAP
    """
    kind:               LookupResultKind
    root_letters:       str
    identity_candidate: Optional[RootIdentityCandidate] = None
    identity_carrier:   Optional[RootIdentityCarrier]   = None
    claims:             tuple[SourceRootClaim, ...]      = field(default_factory=tuple)
    origin_candidates:  tuple[LexicalOriginCandidate, ...] = field(default_factory=tuple)
    residuals:          tuple[Residual, ...]             = field(default_factory=tuple)
    evidence_status:    EvidenceStatus = EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE
    review_state:       ReviewState    = ReviewState.UNREVIEWED
    conflict_notes:     Optional[str]  = None
    coverage_note:      Optional[str]  = None

    @property
    def found(self) -> bool:
        return self.kind in (
            LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY,
            LookupResultKind.FOUND_IDENTITY_CANDIDATE,
            LookupResultKind.FOUND_IDENTITY_VERIFIED,
            LookupResultKind.FOUND_TEXT_VERIFIED,
            LookupResultKind.FOUND_LEXICALLY_REVIEWED,
            LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED,
            LookupResultKind.FOUND_REVIEW_REQUIRED_UNRESOLVED,
        )

    @property
    def has_conflict(self) -> bool:
        return self.kind == LookupResultKind.FOUND_CONFLICT_REVIEW_REQUIRED

    @property
    def coverage_gap(self) -> bool:
        return self.kind == LookupResultKind.MISSING_VOLUME_COVERAGE_GAP

    @property
    def is_machine_only(self) -> bool:
        return self.kind in (
            LookupResultKind.FOUND_MACHINE_CANDIDATE_ONLY,
            LookupResultKind.FOUND_REVIEW_REQUIRED_UNRESOLVED,
        )

    @property
    def open_residuals(self) -> tuple[Residual, ...]:
        return tuple(r for r in self.residuals if not r.is_resolved)


# ═══════════════════════════════════════════════════════════════════════════════
# § 5 — TRANSITION CONTRACTS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Transition contracts define the preconditions and postconditions for each
# state upgrade. They are NOT abstract classes — they are documented as
# named contracts and enforced at runtime by the pipeline modules.
#
# TC-SI-01: Source → Identity
# ──────────────────────────
# PRE:  SourcePassage with review_state = MACHINE_CANDIDATE or SOURCE_LOCATED
# OP:   Extract RootIdentityCandidate from SourcePassage.raw_passage_candidate
# POST: RootIdentityCandidate with review_state = IDENTITY_CANDIDATE
#       TraceEvent(kind=IDENTITY_EXTRACTED, actor_type=MACHINE_ONLY)
#       Residuals emitted for any flagged OCR gates
#
# TC-II-02: Identity Candidate → Licensed Identity
# ─────────────────────────────────────────────────
# PRE:  RootIdentityCandidate with review_state = IDENTITY_CANDIDATE
#       Human reviewer licensed by Hokom's canonical_root
#       No open IDENTITY_CONFLICT Residuals
# OP:   Human creates RootIdentityCarrier with verified_letters
# POST: RootIdentityCarrier with review_state = IDENTITY_VERIFIED
#       evidence_status = IDENTITY_VERIFIED_EVIDENCE
#       TraceEvent(kind=IDENTITY_VERIFIED, actor_type=HUMAN_REVIEWER)
#       ReviewCertificate issued
#
# TC-IR-03: Identity → Claim
# ──────────────────────────
# PRE:  RootIdentityCandidate or RootIdentityCarrier (any review_state ≥ IDENTITY_CANDIDATE)
# OP:   Extract SourceRootClaim from SourcePassage
# POST: SourceRootClaim with review_state = TEXT_CANDIDATE (if machine)
#                         or TEXT_VERIFIED (if human)
#       TraceEvent(kind=ORIGIN_EXTRACTED, actor_type=MACHINE_ONLY or HUMAN_EXTRACTION)
#       If requires_segmentation: emit Residual(SEGMENTATION_REQUIRED)
#
# TC-RO-04: Claim → Origins
# ─────────────────────────
# PRE:  SourceRootClaim with origin_type in {DUAL, TRIPLE, MULTIPLE}
#       review_state ≥ TEXT_CANDIDATE
# OP:   Segment into N LexicalOriginCandidates (N = 2/3/N+)
# POST: N × LexicalOriginCandidate with review_state = ORIGIN_CANDIDATE
#       evidence_status = SOURCE_LOCATED_EVIDENCE (machine) or higher
#       TraceEvent(kind=ORIGIN_SEGMENTED, actor_type=actor)
#       Residual(SEGMENTATION_REQUIRED) resolved
#
# TC-OR-05: Origin Candidate → Reviewed
# ──────────────────────────────────────
# PRE:  LexicalOriginCandidate with review_state ≥ ORIGIN_CANDIDATE
#       Human reviewer
#       No open ORIGIN_CONFLICT Residuals
# OP:   Human reviews and certifies origin claim
# POST: LexicalOriginCandidate with review_state = LEXICALLY_REVIEWED
#       evidence_status = LEXICALLY_REVIEWED_EVIDENCE
#       ReviewCertificate issued
#       TraceEvent(kind=REVIEW_COMPLETED, actor_type=HUMAN_REVIEWER)
#
# ═══════════════════════════════════════════════════════════════════════════════

class TransitionContractViolation(Exception):
    """
    Raised when a pipeline operation violates a transition contract.
    Always includes the contract ID (e.g. "TC-SI-01") and violated rule.
    """
    def __init__(self, contract_id: str, rule: str, detail: str = "") -> None:
        self.contract_id = contract_id
        self.rule = rule
        self.detail = detail
        super().__init__(
            f"[{contract_id}] Transition contract violation: {rule}"
            + (f" — {detail}" if detail else "")
        )


def enforce_tc_si_01(passage: SourcePassage) -> None:
    """
    Enforce TC-SI-01: Source → Identity preconditions.
    Raises TransitionContractViolation if preconditions are not met.
    """
    if passage.review_state not in (
        ReviewState.MACHINE_CANDIDATE,
        ReviewState.SOURCE_LOCATED,
    ):
        raise TransitionContractViolation(
            "TC-SI-01",
            "SourcePassage must be in MACHINE_CANDIDATE or SOURCE_LOCATED state",
            f"actual state: {passage.review_state}",
        )


def enforce_tc_ii_02(
    candidate: RootIdentityCandidate,
    reviewer_type: ReviewerType,
    open_residuals: Sequence[Residual],
) -> None:
    """
    Enforce TC-II-02: Identity Candidate → Licensed Identity preconditions.
    """
    if candidate.review_state != ReviewState.IDENTITY_CANDIDATE:
        raise TransitionContractViolation(
            "TC-II-02",
            "RootIdentityCandidate must be in IDENTITY_CANDIDATE state",
            f"actual state: {candidate.review_state}",
        )
    if reviewer_type == ReviewerType.MACHINE_ONLY:
        raise TransitionContractViolation(
            "TC-II-02",
            "MACHINE_ONLY cannot license an identity — human reviewer required",
        )
    conflict_residuals = [
        r for r in open_residuals
        if r.residual_type == ResidualType.ROOT_IDENTITY_CONFLICT and not r.is_resolved
    ]
    if conflict_residuals:
        raise TransitionContractViolation(
            "TC-II-02",
            "Open IDENTITY_CONFLICT Residuals must be resolved before licensing",
            f"{len(conflict_residuals)} open conflict residuals",
        )


def enforce_tc_ir_03(identity_review_state: ReviewState) -> None:
    """
    Enforce TC-IR-03: Identity → Claim preconditions.
    """
    ordered_states = list(ReviewState)
    idx_identity_candidate = ordered_states.index(ReviewState.IDENTITY_CANDIDATE)
    idx_actual = ordered_states.index(identity_review_state)
    if idx_actual < idx_identity_candidate:
        raise TransitionContractViolation(
            "TC-IR-03",
            "Identity must be at IDENTITY_CANDIDATE or above to produce a claim",
            f"actual state: {identity_review_state}",
        )


def enforce_tc_ro_04(claim: SourceRootClaim) -> None:
    """
    Enforce TC-RO-04: Claim → Origins preconditions.
    """
    if not claim.requires_segmentation:
        raise TransitionContractViolation(
            "TC-RO-04",
            "Origin segmentation requires DUAL, TRIPLE, or MULTIPLE origin_type",
            f"actual origin_type: {claim.origin_type}",
        )
    ordered_states = list(ReviewState)
    idx_text_candidate = ordered_states.index(ReviewState.TEXT_CANDIDATE)
    idx_actual = ordered_states.index(claim.review_state)
    if idx_actual < idx_text_candidate:
        raise TransitionContractViolation(
            "TC-RO-04",
            "SourceRootClaim must be at TEXT_CANDIDATE or above for segmentation",
            f"actual state: {claim.review_state}",
        )


def enforce_tc_or_05(
    origin: LexicalOriginCandidate,
    reviewer_type: ReviewerType,
    open_residuals: Sequence[Residual],
) -> None:
    """
    Enforce TC-OR-05: Origin Candidate → Reviewed preconditions.
    """
    ordered_states = list(ReviewState)
    idx_origin_candidate = ordered_states.index(ReviewState.ORIGIN_CANDIDATE)
    idx_actual = ordered_states.index(origin.review_state)
    if idx_actual < idx_origin_candidate:
        raise TransitionContractViolation(
            "TC-OR-05",
            "LexicalOriginCandidate must be at ORIGIN_CANDIDATE or above",
            f"actual state: {origin.review_state}",
        )
    if reviewer_type == ReviewerType.MACHINE_ONLY:
        raise TransitionContractViolation(
            "TC-OR-05",
            "MACHINE_ONLY cannot certify an origin — human reviewer required",
        )
    conflict_residuals = [
        r for r in open_residuals
        if r.residual_type == ResidualType.ORIGIN_CLAIM_CONFLICT and not r.is_resolved
    ]
    if conflict_residuals:
        raise TransitionContractViolation(
            "TC-OR-05",
            "Open ORIGIN_CONFLICT Residuals must be resolved before certifying",
            f"{len(conflict_residuals)} open conflict residuals",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# § 6 — ACCOUNTING COUNTERS (enforced at module level)
# ═══════════════════════════════════════════════════════════════════════════════

# These counters must remain 0 in all production runs.
# They are verified by test_maqayis_constitutional.py acceptance gates.

# Machine operation must never produce IDENTITY_VERIFIED or above
MACHINE_PRODUCES_HUMAN_REQUIRED_STATE_COUNT: int = 0

# AUTO_AGREED must never map to VERIFIED state
AUTO_AGREED_MAPPED_TO_VERIFIED_COUNT: int = 0

# NONE review_status is NOT_EXTRACTED_OR_NOT_VERIFIED — never a negative semantic claim
NONE_INTERPRETED_AS_NEGATIVE_SEMANTIC_CLAIM_COUNT: int = 0

# REVIEW_REQUIRED must never produce positive origin evidence
REVIEW_REQUIRED_POSITIVE_ORIGIN_EVIDENCE_COUNT: int = 0

# Unknown roots must never be looked up (Maqayis only for Hokom-licensed roots)
MAQAYIS_LOOKUP_FROM_UNKNOWN_ROOT_COUNT: int = 0

# Constitutional evidence must never approve admission independently
CONSTITUTIONAL_EVIDENCE_APPROVED_ADMISSION_COUNT: int = 0

# Evidence must never be issued above machine ceiling by machine operation
MACHINE_EVIDENCE_ABOVE_CEILING_COUNT: int = 0

# NONE must not map to positive absence claim (لا أصل له) — §6
NONE_MAPPED_TO_POSITIVE_ABSENCE_CLAIM_COUNT: int = 0

# Registry failure must not be relabeled as NOT_FOUND — §7
REGISTRY_FAILURE_RELABELED_AS_NOT_FOUND_COUNT: int = 0

# Bare ء must be included in hamza normalization — §8
BARE_HAMZA_COVERAGE_FAILURE_COUNT: int = 0

# Unlicensed roots must never be looked up — §9
LOOKUP_FROM_UNKNOWN_ROOT_COUNT: int = 0
LOOKUP_FROM_DEFERRED_ROOT_COUNT: int = 0
LOOKUP_FROM_AMBIGUOUS_ROOT_COUNT: int = 0
LOOKUP_FROM_BLOCKED_ROOT_COUNT: int = 0

# Claim text must be real OCR text, not root letters — §4
CLAIM_WITH_ROOT_LETTERS_AS_CLAIM_TEXT_COUNT: int = 0

# Origin text must be real extracted text, not root letters — §5
ORIGIN_WITH_ROOT_AS_RAW_TEXT_COUNT: int = 0
MULTIPLE_FORCED_TO_THREE_COUNT: int = 0

# Acceptance gates must be computed, not hardcoded — §11
HARDCODED_ZERO_ACCEPTANCE_GATE_COUNT: int = 0

# Direct root-string lookup bypasses Hokom licensing — §12
DIRECT_LOOKUP_BYPASS_COUNT: int = 0

# NONE/NOT_EXTRACTED/UNKNOWN must not create origin candidates — §7
ORIGIN_NOT_EXTRACTED_AS_CANDIDATE_COUNT: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# § 7 — TYPED AUGMENTATION RESULT (§10)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HokomRootClaim:
    """
    Typed Hokom root directive and verdict.
    R11: Real typed Hokom root model — replaces SimpleNamespace in production.
    """
    canonical_root: tuple[str, ...]
    directive: str  # "ACCEPT" | "DEFER" | "BLOCK"
    verdict_reason: Optional[str] = None
    root_class: Optional[str] = None


@dataclass(frozen=True)
class MaqayisConstitutionalAugmentationResult:
    """
    Typed result from maqayis_constitutional_evidence_adapter.augment_evidence_from_bundle().

    Replaces the bare tuple[str, ...] return.
    Carries full metadata so the calling layer can inspect EvidenceStatus
    without string-parsing the evidence IDs.

    Fields
    ──────
    lookup_kind         : LookupResultKind from the constitutional registry
    evidence_ids        : tuple of Maqayis evidence ID strings
    evidence_status     : EvidenceStatus for all emitted IDs
    review_state        : ReviewState of the source lookup
    licensed            : True if the root was licensed by Hokom's canonical_root
    source_passage_ids  : IDs of SourcePassage records contributing evidence
    trace_ids           : IDs of TraceEvent records for this augmentation
    residual_ids        : IDs of open Residual records for this root
    coverage_status     : "COVERED" | "MISSING_VOLUME" | "NOT_FOUND" | "LOAD_FAILURE"
    failure_detail      : error detail if load failure, else None
    """
    lookup_kind:         LookupResultKind
    evidence_ids:        tuple[str, ...]
    evidence_status:     EvidenceStatus
    review_state:        ReviewState
    licensed:            bool
    source_passage_ids:  tuple[str, ...]
    trace_ids:           tuple[str, ...]
    residual_ids:        tuple[str, ...]
    coverage_status:     str
    failure_detail:      Optional[str] = None
    hokom_root_licensed:       bool = False
    source_candidate_found:    bool = False
    lexical_evidence_licensed: bool = False

    @classmethod
    def not_licensed(
        cls,
        reason: str,
        lookup_kind: LookupResultKind = LookupResultKind.NOT_FOUND_IN_COVERED_VOLUME,
    ) -> "MaqayisConstitutionalAugmentationResult":
        """Convenience constructor for rejected/unlicensed cases."""
        return cls(
            lookup_kind=lookup_kind,
            evidence_ids=(),
            evidence_status=EvidenceStatus.MACHINE_SOURCE_CLAIM_CANDIDATE,
            review_state=ReviewState.UNREVIEWED,
            licensed=False,
            source_passage_ids=(),
            trace_ids=(),
            residual_ids=(),
            coverage_status="NOT_LICENSED",
            failure_detail=reason,
            hokom_root_licensed=False,
            source_candidate_found=False,
            lexical_evidence_licensed=False,
        )

    @classmethod
    def from_lookup_result(
        cls,
        result: "ConstitutionalLookupResult",
        evidence_ids: tuple[str, ...],
    ) -> "MaqayisConstitutionalAugmentationResult":
        """Build from a ConstitutionalLookupResult.
        R10: only called when Hokom accepted, so hokom_root_licensed=True always.
        R13: populate passage_ids from all claims + identity_candidate.
             trace_ids from residuals as proxy (no trace events on lookup result).
        """
        if result.coverage_gap:
            cov = "MISSING_VOLUME"
        elif result.kind in (
            LookupResultKind.REGISTRY_LOAD_FAILURE,
            LookupResultKind.REGISTRY_PARTIAL_LOAD,
        ):
            cov = "LOAD_FAILURE"
        elif result.found:
            cov = "COVERED"
        else:
            cov = "NOT_FOUND"

        # R13: Collect passage_ids from identity_candidate AND all claims
        passage_ids_set: set[str] = set()
        if result.identity_candidate and hasattr(result.identity_candidate, "passage_id"):
            passage_ids_set.add(result.identity_candidate.passage_id)
        for c in result.claims:
            if hasattr(c, "passage_id"):
                passage_ids_set.add(c.passage_id)
        passage_ids = tuple(sorted(passage_ids_set))

        residual_ids = tuple(r.id for r in result.open_residuals)

        # R13: use residuals as trace_id proxy (no trace events on lookup result)
        trace_ids = tuple(r.id for r in result.residuals[:10])

        return cls(
            lookup_kind=result.kind,
            evidence_ids=evidence_ids,
            evidence_status=result.evidence_status,
            review_state=result.review_state,
            licensed=result.found,
            source_passage_ids=passage_ids,
            trace_ids=trace_ids,
            residual_ids=residual_ids,
            coverage_status=cov,
            failure_detail=result.conflict_notes or result.coverage_note,
            hokom_root_licensed=True,   # R10: only called after Hokom ACCEPT
            source_candidate_found=result.identity_candidate is not None or len(result.claims) > 0,
            lexical_evidence_licensed=len(evidence_ids) > 0,
        )
