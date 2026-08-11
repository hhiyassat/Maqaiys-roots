"""
maqayis_wordnet_entity_layer.py — Layer D: طبقة الذات (Entity Ontology Layer)
MAQAYIS-CONSTITUTIONAL-SOURCE-LEXICON-PRODUCTION-01

Enriches the pipeline output with WordNet IS-A entity classification
for Arabic nouns found in the semantic analysis layers.

Constitutional constraints
──────────────────────────
  - ENTITY_CANDIDATE_ONLY: all classifications are candidates; none are
    licensed ontological facts without human review.
  - WordNet is a non-authoritative external source. Its classifications
    annotate, never override, Maqayis lexical claims.
  - is_human = True ONLY via person.n.01 hypernym path (NOT organism.n.01).
    Animals are is_animate but NOT is_human.
  - Layer D is never built for CHAPTER_HEADER or OCR_NOISE entries.
  - Layer D is a fail-open layer: any exception returns an empty profile
    without raising or blocking the pipeline.
  - Layer D does NOT produce Ifadah, Hukm, Manat, Tanzil, or AnswerAudit.
  - Layer D does NOT approve or reject Taaqol admission.
  - Layer D does NOT increase token rank.

Accounting counters (all must remain 0 in production)
──────────────────────────────────────────────────────
  ENTITY_CLASSIFICATION_AS_ONTOLOGICAL_FACT_COUNT = 0
  HUMAN_CLASSIFICATION_VIA_ORGANISM_COUNT         = 0
  LAYER_D_ON_NOISE_ENTRY_COUNT                    = 0
  LAYER_D_ADMISSION_DECISION_COUNT                = 0

Output structure (layer_d_entity_profile)
─────────────────────────────────────────
  {
    "_notice": "ENTITY_CANDIDATE_ONLY",
    "coverage_source": str,          # "arabic_synset_map.json" | "seed_only"
    "words_examined":  int,
    "words_classified": int,
    "entity_candidates": [           # one per Arabic word found in bundle
      {
        "word":          str,
        "source_layer":  str,        # "L3_nucleus"|"L3_branch"|"L3_component"
        "source_field":  str,        # field name in originating layer
        "synsets":       [str],      # WordNet synset IDs
        "categories": {
          "is_human":      bool,
          "is_animate":    bool,
          "is_artifact":   bool,
          "is_location":   bool,
          "is_abstraction": bool,
        },
        "hypernym_chain": [str],     # ENTITY_CANDIDATE_ONLY
        "evidence_ids":   [str],     # wordnet:class:*  wordnet:hypernym:*
        "classification_source": str # "wordnet"|"seed"|"unknown"
      }
    ],
    "selectional_restriction_checks": [   # populated when root is verbal
      {
        "verb":       str,
        "subject":    str,
        "verdict":    str,           # "VALID"|"INVALID"|"UNKNOWN"
        "valid":      bool,
        "evidence_ids": [str],
      }
    ],
    "entity_summary": {
      "human_count":      int,
      "animate_count":    int,
      "artifact_count":   int,
      "location_count":   int,
      "abstraction_count": int,
      "unknown_count":    int,
    },
  }
"""
from __future__ import annotations

import re
import sys
import pathlib
from typing import Any, Dict, List, Optional

# ── Accounting counters ───────────────────────────────────────────────────────
ENTITY_CLASSIFICATION_AS_ONTOLOGICAL_FACT_COUNT: int = 0
HUMAN_CLASSIFICATION_VIA_ORGANISM_COUNT:         int = 0
LAYER_D_ON_NOISE_ENTRY_COUNT:                    int = 0
LAYER_D_ADMISSION_DECISION_COUNT:                int = 0

# Label on every classification output
ENTITY_CANDIDATE_ONLY = "ENTITY_CANDIDATE_ONLY"

# ── WordNet bridge import (lazy to avoid hard dependency at import time) ──────
_bridge_path = pathlib.Path(__file__).resolve().parent.parent / "taaqol_integration"
if str(_bridge_path) not in sys.path:
    sys.path.insert(0, str(_bridge_path))

_bridge = None
_BRIDGE_SOURCE = "unavailable"

def _get_bridge():
    global _bridge, _BRIDGE_SOURCE
    if _bridge is not None:
        return _bridge
    try:
        import wordnet_arabic_bridge as _b
        _bridge = _b
        _BRIDGE_SOURCE = (
            "arabic_synset_map.json"
            if getattr(_b, "_FULL_MAP_AVAILABLE", False)
            else "seed_only"
        )
    except Exception:
        _bridge = None
        _BRIDGE_SOURCE = "unavailable"
    return _bridge


# ── Arabic harakat normalization ──────────────────────────────────────────────
_HARAKAT = re.compile(r"[ً-ِّْٰٕٟٓٔ]")
_AL = re.compile(r"^ال")

def _normalize(word: str) -> str:
    if not word:
        return ""
    word = _HARAKAT.sub("", word)
    word = _AL.sub("", word)
    return word.strip()


# ── Extract Arabic words from a MaqayisSourceBundle ──────────────────────────

def _extract_words(bundle) -> List[Dict[str, str]]:
    """
    Pull Arabic word candidates from all layers of the bundle.
    Returns list of {"word": str, "source_layer": str, "source_field": str}.
    Words are deduplicated (first occurrence wins for layer/field labelling).
    """
    seen: set = set()
    words: List[Dict[str, str]] = []

    def _add(text: Optional[str], layer: str, field: str) -> None:
        if not text:
            return
        # Split on whitespace to handle multi-word nucleus phrases
        for token in text.split():
            w = _normalize(token)
            if len(w) < 2:
                continue
            if w not in seen:
                seen.add(w)
                words.append({"word": w, "source_layer": layer, "source_field": field})

    # Layer 3 — lexical origin records: semantic_nucleus + gloss + components
    for origin in getattr(bundle, "origins", []):
        _add(origin.semantic_nucleus,      "L3_nucleus",   "semantic_nucleus")
        _add(origin.origin_gloss_candidate,"L3_nucleus",   "origin_gloss_candidate")
        for comp in getattr(origin, "semantic_components", []):
            _add(getattr(comp, "label", None), "L3_component", "component_label")

    # Layer 3 — branch records: surface forms
    for branch in getattr(bundle, "branches", []):
        _add(branch.source_lexical_form, "L3_branch", "source_lexical_form")
        _add(branch.normalized_form,     "L3_branch", "normalized_form")

    # Layer 2 — lexical claim graph: term nodes
    lcg = getattr(bundle, "lexical_claim_graph", None)
    if lcg is not None:
        for node in getattr(lcg, "term_nodes", []):
            _add(getattr(node, "term_text", None), "L2_term", "term_text")

    # Layer 4 — concept candidates: semantic_nucleus from GenusCandidateRecord
    ocp = getattr(bundle, "ontology_candidate_profile", None)
    if ocp is not None:
        for cc in getattr(ocp, "concept_candidates", []):
            for gc in getattr(cc, "genus_candidates", []):
                _add(getattr(gc, "semantic_nucleus", None), "L4_genus", "semantic_nucleus")

    return words


# ── Classify a single word via wordnet_arabic_bridge ─────────────────────────

def _classify_word(bridge, word: str, source_layer: str, source_field: str) -> Dict[str, Any]:
    """
    Classify one Arabic word. Returns a candidate record.
    Never raises.
    """
    try:
        result = bridge.classify(word)
        ev_ids = list(bridge.get_evidence_ids(word))

        return {
            "word":          word,
            "source_layer":  source_layer,
            "source_field":  source_field,
            "synsets":       result.get("synsets", []),
            "categories": {
                "is_human":       result.get("is_human", False),
                "is_animate":     result.get("is_animate", False),
                "is_artifact":    result.get("is_artifact", False),
                "is_location":    result.get("is_location", False),
                "is_abstraction": result.get("is_abstraction", False),
            },
            "hypernym_chain":         result.get("chain", []),    # ENTITY_CANDIDATE_ONLY
            "evidence_ids":           ev_ids,
            "classification_source":  result.get("source", "unknown"),
        }
    except Exception as exc:
        return {
            "word":          word,
            "source_layer":  source_layer,
            "source_field":  source_field,
            "synsets":       [],
            "categories":    {
                "is_human": False, "is_animate": False, "is_artifact": False,
                "is_location": False, "is_abstraction": False,
            },
            "hypernym_chain":        [],
            "evidence_ids":          [],
            "classification_source": f"error:{type(exc).__name__}",
        }


# ── Selectional restriction checks for verbal roots ──────────────────────────

def _selectional_checks(bridge, bundle) -> List[Dict[str, Any]]:
    """
    When the bundle's root_letters appear in VERB_SELECTIONAL_RESTRICTIONS,
    check compatibility against the entity candidates already in the bundle.

    Only checks verbs already defined in the bridge.
    Never raises.
    """
    checks: List[Dict[str, Any]] = []
    try:
        sr = getattr(bridge, "VERB_SELECTIONAL_RESTRICTIONS", {})
        if not sr:
            return checks

        ri = getattr(bundle, "root_identity", None)
        root = ""
        if ri is not None:
            root = getattr(ri, "candidate_letters", "") or ""

        if not root or root not in sr:
            return checks

        # Extract entity words from origins to use as subjects
        subjects = []
        for origin in getattr(bundle, "origins", []):
            n = getattr(origin, "semantic_nucleus", None)
            if n:
                for tok in n.split():
                    w = _normalize(tok)
                    if len(w) >= 2:
                        subjects.append(w)

        for subject in subjects[:5]:  # cap at 5 checks per bundle
            try:
                r = bridge.check_verb_subject(root, subject)
                checks.append({
                    "verb":        root,
                    "subject":     subject,
                    "verdict":     r.get("verdict", "UNKNOWN"),
                    "valid":       r.get("valid", None),
                    "evidence_ids": list(r.get("evidence_ids", ())),
                })
            except Exception:
                pass
    except Exception:
        pass
    return checks


# ── Entity summary ────────────────────────────────────────────────────────────

def _summarize(candidates: List[Dict]) -> Dict[str, int]:
    human = animate = artifact = location = abstraction = unknown = 0
    for c in candidates:
        cats = c.get("categories", {})
        if cats.get("is_human"):          human += 1
        elif cats.get("is_animate"):      animate += 1
        if cats.get("is_artifact"):       artifact += 1
        if cats.get("is_location"):       location += 1
        if cats.get("is_abstraction"):    abstraction += 1
        if not any(cats.values()):        unknown += 1
    return {
        "human_count":       human,
        "animate_count":     animate,
        "artifact_count":    artifact,
        "location_count":    location,
        "abstraction_count": abstraction,
        "unknown_count":     unknown,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def build_layer_d(bundle) -> Dict[str, Any]:
    """
    Build the Layer D (طبقة الذات) entity profile for a MaqayisSourceBundle.

    Returns a JSON-serializable dict ready for inclusion in the pipeline output
    under the key "layer_d_entity_profile".

    Never raises. Returns minimal profile on any failure.

    Constitutional constraint:
      "_notice": "ENTITY_CANDIDATE_ONLY" is always present in output.
      ENTITY_CLASSIFICATION_AS_ONTOLOGICAL_FACT_COUNT must remain 0.
    """
    # Guard: do not build for CHAPTER_HEADER or OCR_NOISE
    entry_kind = getattr(bundle, "entry_kind", None)
    if entry_kind is not None:
        kind_val = getattr(entry_kind, "value", str(entry_kind))
        if kind_val in ("CHAPTER_HEADER", "OCR_NOISE"):
            # LAYER_D_ON_NOISE_ENTRY_COUNT remains 0
            return {
                "_notice":     ENTITY_CANDIDATE_ONLY,
                "_skipped":    True,
                "_skip_reason": f"entry_kind={kind_val}",
            }

    bridge = _get_bridge()
    if bridge is None:
        return {
            "_notice":     ENTITY_CANDIDATE_ONLY,
            "_skipped":    True,
            "_skip_reason": "wordnet_arabic_bridge unavailable",
        }

    # Extract candidate words from all layers
    word_records = _extract_words(bundle)

    # Classify each word
    candidates: List[Dict] = []
    for rec in word_records:
        c = _classify_word(bridge, rec["word"], rec["source_layer"], rec["source_field"])
        candidates.append(c)

    # Selectional restriction checks (verbal roots only)
    sr_checks = _selectional_checks(bridge, bundle)

    classified = sum(
        1 for c in candidates
        if any(c.get("categories", {}).values())
    )

    return {
        "_notice":        ENTITY_CANDIDATE_ONLY,
        "coverage_source": _BRIDGE_SOURCE,
        "words_examined":  len(candidates),
        "words_classified": classified,
        "entity_candidates": candidates,
        "selectional_restriction_checks": sr_checks,
        "entity_summary": _summarize(candidates),
    }
