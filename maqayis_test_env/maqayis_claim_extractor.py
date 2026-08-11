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
All claims carry origin_index (0 or 1).  Starts at 0; flips to 1 when a
SECOND_ORIG segment is encountered.  Allows callers to separate claims that
belong to the first vs. second origin of a DUAL entry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Import the segment types from the loader
# (done at call time to avoid circular imports)


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
# ═══════════════════════════════════════════════════════════════════════════════

# Arabic letter + diacritic range
_AR = r"[؀-ۿً-ْ]"

# ── USAGE patterns ────────────────────────────────────────────────────────────

# يقال X إذا Y — most informative: term + condition/definition
_USAGE_COND_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+(.{2,30}?)(?:\s*،\s*|\s+)إذا\s+(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# يقال له X — named form / technical term
_USAGE_NAMED_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+له\s+({ar}+(?:\s+{ar}+){{0,2}})".format(ar=_AR),
    re.UNICODE,
)

# يقال X : Y — form with colon definition
_USAGE_COLON_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+(.{2,25}?)\s*:\s*(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# يقال X (bare — just the form before comma or period)
_USAGE_FORM_RE = re.compile(
    r"(?:و|ف)?(?:ي|ب)قال\s+({ar}+(?:\s+{ar}+){{0,4}})\s*[.،]".format(ar=_AR),
    re.UNICODE,
)

# ── AUTHORITY patterns ────────────────────────────────────────────────────────

# قال NAME : TEXT  (name is 1–3 Arabic words)
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

# أصله / أصلها X
_ETYM_ORIGIN_RE = re.compile(
    r"أصل(?:ه|ها|هُ|ان)\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# سُمِّي X لأنّ Y  / لـ Y
_ETYM_NAMING_RE = re.compile(
    r"سُمِّي(?:ت)?\s+({ar}+(?:\s+{ar}+){{0,3}})\s+(?:لأنَّ?|لأنه|ل)\s*(.{{5,120}}?)(?:[.،؛]|$)".format(ar=_AR),
    re.UNICODE,
)

# لأنّه X
_ETYM_CAUSAL_RE = re.compile(
    r"لأنَّ?ه\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# كأنّه X
_ETYM_ANALOGY_RE = re.compile(
    r"كأنَّ?ه\s+(.{5,120}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# يدلّ على X
_ETYM_SEMANTIC_RE = re.compile(
    r"يدلُّ? على\s+(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# اشتقاقه / مشتق
_ETYM_DERIV_RE = re.compile(
    r"(?:اشتقاق(?:ه|ها)?|مشتق)\s+(?:من\s+)?(.{5,100}?)(?:[.،؛]|$)",
    re.UNICODE,
)

# ── PLURAL patterns ───────────────────────────────────────────────────────────

# والجمع / وجمعه X  (X = one or more Arabic words separated by و/أو)
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

# Strip trailing noise from authority names
_AUTH_TRAIL_RE = re.compile(r"[،:.؛\s]+$", re.UNICODE)

def _clean_authority(raw: str) -> str:
    name = _AUTH_TRAIL_RE.sub("", raw.strip())
    # Keep only last 3 words if very long
    words = name.split()
    return " ".join(words[:3]) if words else name


# ═══════════════════════════════════════════════════════════════════════════════
# § 3 — PER-TYPE EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_usage(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    """Extract from USAGE segments (يقال / يقولون / قيل)."""
    full = f"{seg_marker} {seg_text}"

    # 1. يقال له X — named form
    m = _USAGE_NAMED_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="USAGE_NAMED", segment_type="USAGE",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), origin_index=origin_idx,
        )

    # 2. يقال X إذا Y — conditional
    m = _USAGE_COND_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="USAGE_CONDITIONAL", segment_type="USAGE",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), definition=m.group(2).strip(),
            origin_index=origin_idx,
        )

    # 3. يقال X : Y — colon definition
    m = _USAGE_COLON_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="USAGE_FORM", segment_type="USAGE",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), definition=m.group(2).strip(),
            origin_index=origin_idx,
        )

    # 4. يقال X . — bare form
    m = _USAGE_FORM_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="USAGE_FORM", segment_type="USAGE",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), origin_index=origin_idx,
        )

    # Fallback
    return LexicalClaim(
        claim_type="RAW_SEGMENT", segment_type="USAGE",
        marker=seg_marker, raw_text=seg_text,
        origin_index=origin_idx,
    )


def _extract_authority(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    """Extract from AUTHORITY segments (قال X / قالوا)."""
    full = f"{seg_marker} {seg_text}"

    # قالوا : TEXT
    m = _AUTH_QALU_RE.search(full)
    if "قالوا" in full and m:
        return LexicalClaim(
            claim_type="AUTHORITY_CITATION", segment_type="AUTHORITY",
            marker=seg_marker, raw_text=seg_text,
            authority="قالوا", definition=m.group(1).strip()[:200],
            origin_index=origin_idx,
        )

    # قال NAME : TEXT
    m = _AUTH_NAMED_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="AUTHORITY_CITATION", segment_type="AUTHORITY",
            marker=seg_marker, raw_text=seg_text,
            authority=_clean_authority(m.group(1)),
            definition=m.group(2).strip()[:200],
            origin_index=origin_idx,
        )

    return LexicalClaim(
        claim_type="RAW_SEGMENT", segment_type="AUTHORITY",
        marker=seg_marker, raw_text=seg_text,
        origin_index=origin_idx,
    )


def _extract_etymology(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    """Extract from ETYMOLOGY segments (أصله / لأنّه / كأنّه / سُمِّي / يدلّ على)."""
    full = f"{seg_marker} {seg_text}"

    # سُمِّي X لأنّ Y
    m = _ETYM_NAMING_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_NAMING", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), definition=m.group(2).strip(),
            origin_index=origin_idx,
        )

    # أصله X
    m = _ETYM_ORIGIN_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_ORIGIN", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip(), origin_index=origin_idx,
        )

    # يدلّ على X
    m = _ETYM_SEMANTIC_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_SEMANTIC", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip(), origin_index=origin_idx,
        )

    # لأنّه X
    m = _ETYM_CAUSAL_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_CAUSAL", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip(), origin_index=origin_idx,
        )

    # كأنّه X
    m = _ETYM_ANALOGY_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_CAUSAL", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip(), origin_index=origin_idx,
        )

    # اشتقاقه
    m = _ETYM_DERIV_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="ETYMOLOGY_ORIGIN", segment_type="ETYMOLOGY",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip(), origin_index=origin_idx,
        )

    return LexicalClaim(
        claim_type="RAW_SEGMENT", segment_type="ETYMOLOGY",
        marker=seg_marker, raw_text=seg_text,
        origin_index=origin_idx,
    )


def _extract_plural(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    """Extract from PLURAL segments (والجمع / وجمعه)."""
    full = f"{seg_marker} {seg_text}"
    m = _PLURAL_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="PLURAL_FORM", segment_type="PLURAL",
            marker=seg_marker, raw_text=seg_text,
            term=m.group(1).strip(), origin_index=origin_idx,
        )
    return LexicalClaim(
        claim_type="RAW_SEGMENT", segment_type="PLURAL",
        marker=seg_marker, raw_text=seg_text,
        origin_index=origin_idx,
    )


def _extract_hadith(seg_marker: str, seg_text: str, origin_idx: int) -> LexicalClaim:
    """Extract from HADITH segments."""
    full = f"{seg_marker} {seg_text}"
    m = _HADITH_RE.search(full)
    if m:
        return LexicalClaim(
            claim_type="HADITH_EVIDENCE", segment_type="HADITH",
            marker=seg_marker, raw_text=seg_text,
            definition=m.group(1).strip()[:200], origin_index=origin_idx,
        )
    return LexicalClaim(
        claim_type="HADITH_EVIDENCE", segment_type="HADITH",
        marker=seg_marker, raw_text=seg_text,
        definition=seg_text[:200], origin_index=origin_idx,
    )


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
    list[LexicalClaim] — ordered list of extracted claims.
        origin_index tracks which origin (0 or 1) a claim belongs to.
    """
    claims: list[LexicalClaim] = []
    origin_idx = 0

    for seg in segments:
        stype  = seg.type
        marker = seg.marker
        text   = seg.text

        # Track origin boundary (DUAL entries)
        if stype == "SECOND_ORIG":
            origin_idx = 1
            claims.append(LexicalClaim(
                claim_type="ORIGIN_BOUNDARY",
                segment_type="SECOND_ORIG",
                marker=marker, raw_text=text,
                origin_index=origin_idx,
            ))
            continue

        if stype == "USAGE":
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
            claims.append(LexicalClaim(
                claim_type="BRANCH_ITEM",
                segment_type="BRANCH",
                marker=marker, raw_text=text,
                origin_index=origin_idx,
            ))

        elif stype == "EXCEPTION":
            claims.append(LexicalClaim(
                claim_type="EXCEPTION_NOTE",
                segment_type="EXCEPTION",
                marker=marker, raw_text=text,
                origin_index=origin_idx,
            ))

        elif stype == "INTRO":
            claims.append(LexicalClaim(
                claim_type="INTRO_EXAMPLE",
                segment_type="INTRO",
                marker=marker, raw_text=text,
                origin_index=origin_idx,
            ))

        else:
            # CONTINUATION or any unrecognised type
            claims.append(LexicalClaim(
                claim_type="RAW_SEGMENT",
                segment_type=stype,
                marker=marker, raw_text=text,
                origin_index=origin_idx,
            ))

    return claims


def extract_claims_from_entry(entry: dict, loader) -> list[LexicalClaim]:
    """
    Convenience wrapper: segment + extract in one call.

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
    Return a dict summarising the claims for one entry:
      total, by_type counts, usage_terms, plural_forms, authorities, hadiths.
    """
    from collections import Counter
    by_type    = Counter(c.claim_type for c in claims)
    usage      = [c.term for c in claims if c.claim_type in ("USAGE_CONDITIONAL","USAGE_FORM","USAGE_NAMED") and c.term]
    plurals    = [c.term for c in claims if c.claim_type == "PLURAL_FORM" and c.term]
    auths      = [c.authority for c in claims if c.claim_type == "AUTHORITY_CITATION" and c.authority]
    hadiths    = [c.definition for c in claims if c.claim_type == "HADITH_EVIDENCE" and c.definition]
    etym       = [c.definition for c in claims if c.claim_type.startswith("ETYMOLOGY") and c.definition]

    return {
        "total":        len(claims),
        "by_type":      dict(by_type),
        "usage_terms":  usage,
        "plural_forms": plurals,
        "authorities":  list(dict.fromkeys(auths)),   # deduplicated, ordered
        "hadiths":      hadiths,
        "etymology":    etym,
        "dual_entry":   any(c.claim_type == "ORIGIN_BOUNDARY" for c in claims),
    }
