"""
maqayis_pipeline_api.py
═══════════════════════
Public Python API for the Maqayis Constitutional Knowledge Extraction Pipeline.

Entry point
───────────
    from maqayis_pipeline_api import analyze_root

    result = analyze_root("كتب")
    # → returns dict  (always)
    # → writes  output/maqayis_كتب.json  (default)

Function signature
──────────────────
    analyze_root(
        root_letters: str,
        *,
        entries_jsonl: str | Path | None = None,
        lines_jsonl:   str | Path | None = None,
        output_path:   str | Path | None = AUTO,  # None disables file write
        output_dir:    str | Path        = "output",
    ) -> dict

Constitutional constraints (preserved from schema)
───────────────────────────────────────────────────
    - All Layer 4 output is ONTOLOGY_CANDIDATE_ONLY.
    - Machine code never sets IDENTITY_VERIFIED, TEXT_VERIFIED, LEXICALLY_REVIEWED.
    - Layer 4 is blocked when any BLOCKING_RESIDUAL is present.
    - Maqayis is a lexical source — not an ontological authority.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

# ── Path resolution ─────────────────────────────────────────────────────────
_THIS_DIR    = pathlib.Path(__file__).resolve().parent   # pipeline/taaqol_integration/
_PROJECT_ROOT = _THIS_DIR.parent.parent                  # hokom-maqayis-v1/

from .maqayis_source_schema import (
    BLOCKING_RESIDUALS,
    ONTOLOGY_CANDIDATE_ONLY,
    WORK_ID,
    AUTHOR_ID,
    SCHEMA_VERSION,
)
from .maqayis_body_loader import MaqayisBodyLoader
from .maqayis_source_evidence_builder import SourceEvidenceBuilder
from .maqayis_claim_extractor import (
    extract_claims_from_entry,
    build_lexical_claim_graph_from_entry,
)
from .maqayis_semantic_origin_graph_builder import (
    build_semantic_origin_graph,
    attach_layer3_to_bundle,
)
from .maqayis_ontology_candidate_builder import attach_layer4_to_bundle
from .maqayis_wordnet_entity_layer import build_layer_d

# ── Default data paths — resolved via git worktree chain if needed ───────────
def _find_data_dir(start: pathlib.Path) -> pathlib.Path:
    """
    Search for data/maqaees/full/ starting from `start` and walking up.
    If not found locally, follow the .git file (worktree link) to the main
    repo and try there too.
    """
    # 1. Try from start upward
    candidate = start
    for _ in range(4):
        d = candidate / "data" / "maqaees" / "full"
        if d.is_dir():
            return d
        candidate = candidate.parent

    # 2. Follow worktree link: hokom-maqayis-v1/.git → hokom/.git/worktrees/…
    git_ref = start / ".git"
    if git_ref.is_file():
        # .git file contains: "gitdir: /path/to/hokom/.git/worktrees/hokom-maqayis-v1"
        text = git_ref.read_text().strip()
        if text.startswith("gitdir:"):
            gitdir = pathlib.Path(text.split(":", 1)[1].strip())
            # gitdir == hokom/.git/worktrees/hokom-maqayis-v1
            # main repo == gitdir.parent.parent
            main_repo = gitdir.parent.parent.parent  # hokom/
            d = main_repo / "data" / "maqaees" / "full"
            if d.is_dir():
                return d

    # 3. Sibling named "hokom" (common local layout)
    sibling = start.parent / "hokom" / "data" / "maqaees" / "full"
    if sibling.is_dir():
        return sibling

    return start  # fallback — caller will get FileNotFoundError with a clear path

_DATA_DIR        = _find_data_dir(_PROJECT_ROOT)
_DEFAULT_ENTRIES = _DATA_DIR / "root_entries_corrected.jsonl"
_DEFAULT_LINES   = _DATA_DIR / "lines.jsonl"

# ── Sentinel for "write to auto path" ──────────────────────────────────────
_AUTO = object()


# ═══════════════════════════════════════════════════════════════════════════
# §1 — SERIALIZATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _enum_val(v: Any) -> Any:
    """Return .value for enums, else the value unchanged."""
    return v.value if hasattr(v, "value") else v


def _ser_source_evidence(se) -> dict:
    if se is None:
        return {}
    best = se.best_text()
    raw  = se.raw_ocr_text
    d: dict = {
        "line_ids":       se.line_ids,
        "page_number":    se.page_number,
        "ocr_confidence": se.ocr_confidence,
        "text":           best,
    }
    # Show raw OCR only when it differs from best text — flags normalization regressions
    if raw and raw != best:
        d["text_raw_ocr"] = raw
    if se.human_corrected_text:
        d["human_corrected_text"] = se.human_corrected_text
    return d


def _ser_root_identity(ri) -> dict:
    if ri is None:
        return {}
    return {
        "source_root_candidate":    ri.source_root_candidate,
        "source_bab_letter":        ri.source_bab_letter,
        "corrected_bab_letter":     ri.corrected_bab_letter,
        "heading_type":             _enum_val(ri.heading_type),
        "root_identity_match":      _enum_val(ri.root_identity_match),
        "is_resolved":              ri.is_resolved(),
        "match_confidence":         ri.match_confidence,
        "correction_review_state":  _enum_val(ri.correction_review_state),
        "hokom_canonical_root_ref": ri.hokom_canonical_root_ref,
    }


def _ser_extraction_meta(em) -> dict:
    if em is None:
        return {}
    return {
        "extraction_method":     _enum_val(em.extraction_method),
        "review_state":          _enum_val(em.review_state),
        "evidence_status":       _enum_val(em.evidence_status),
        "extraction_confidence": em.extraction_confidence,
        "residuals":             [_enum_val(r) for r in em.residuals],
        # blocking_residuals omitted — computable as residuals ∩ BLOCKING_RESIDUALS
        # is_ontology_buildable omitted — canonical answer is layer_4 status
    }


def _ser_claim_node(cn) -> dict:
    d: dict = {
        "claim_type":         cn.claim_type,
        "raw_text":           cn.raw_text,
        "assertion_strength": _enum_val(cn.assertion_strength),
        "origin_index":       cn.origin_index,
    }
    # Only include when present — avoids noise in most claims
    if cn.term:
        d["term"] = cn.term
    if cn.definition:
        d["definition"] = cn.definition
    if cn.authority:
        d["authority"] = cn.authority
    return d


def _ser_term_node(tn) -> dict:
    return {
        "term_node_id":   tn.term_node_id,
        "surface_form":   tn.surface_form,
        "normalized_form": tn.normalized_form,
        "frequency":      tn.frequency,
    }


def _ser_authority_node(an) -> dict:
    return {
        "authority_node_id": an.authority_node_id,
        "name_in_source":    an.name_in_source,
        "scholar_id":        an.scholar_id,
    }


def _ser_graph_edge(e) -> dict:
    return {
        "edge_id":   e.edge_id,
        "edge_type": _enum_val(e.edge_type),
        "source_id": e.source_id,
        "target_id": e.target_id,
        "weight":    e.weight,
    }


def _ser_lexical_claim_graph(lcg) -> dict:
    if lcg is None:
        return {}
    # graph_id / entry_id omitted — internal IDs, entry_id already in parent
    d: dict = {
        "claim_nodes": [_ser_claim_node(c) for c in lcg.claim_nodes],
    }
    if lcg.term_nodes:
        d["term_nodes"] = [_ser_term_node(t) for t in lcg.term_nodes]
    if lcg.authority_nodes:
        d["authority_nodes"] = [_ser_authority_node(a) for a in lcg.authority_nodes]
    if lcg.evidence_nodes:
        d["evidence_nodes"] = [{"text": en.text} for en in lcg.evidence_nodes]
    if lcg.edges:
        d["edges"] = [_ser_graph_edge(e) for e in lcg.edges]
    return d


def _ser_root_origin_node(ron) -> dict:
    # node_id omitted — internal graph ID
    return {
        "origin_index": ron.origin_index,
        "raw_text":     ron.raw_text,
    }


def _ser_semantic_origin_graph(sog) -> dict:
    if sog is None:
        return {}
    # graph_id / entry_id omitted — internal IDs; validate_dag omitted (result in attach_layer3)
    d: dict = {
        "root_origin_nodes": [_ser_root_origin_node(n) for n in sog.root_origin_nodes],
    }
    if sog.branch_nodes:
        d["branch_nodes"] = [
            {"branch_index": n.branch_index, "raw_text": n.raw_text}
            for n in sog.branch_nodes
        ]
    if sog.exception_nodes:
        d["exception_nodes"] = [
            {"raw_text": n.raw_text} for n in sog.exception_nodes
        ]
    if sog.cross_ref_nodes:
        d["cross_ref_nodes"] = [
            {"target_root": getattr(n, "target_root", None) or getattr(n, "target_entry_id", None)}
            for n in sog.cross_ref_nodes
        ]
    if sog.edges:
        d["edges"] = [_ser_graph_edge(e) for e in sog.edges]
    return d


def _ser_lexical_origin_record(o) -> dict:
    # origin_id omitted — internal ID
    d: dict = {
        "origin_index":    o.origin_index,
        "origin_type":     _enum_val(o.origin_type),
        "raw_origin_text": o.raw_origin_text,
        "semantic_nucleus": o.semantic_nucleus,
        "gloss_method":    _enum_val(o.gloss_method),
    }
    # Only emit candidate fields when they carry actual information (not UNKNOWN)
    sk = _enum_val(o.semantic_kind_candidate)
    if sk and sk != "UNKNOWN":
        d["semantic_kind_candidate"] = sk
    al = _enum_val(o.abstraction_level)
    if al and al != "UNKNOWN":
        d["abstraction_level"] = al
    tp = _enum_val(o.temporal_profile_candidate)
    if tp and tp != "UNKNOWN":
        d["temporal_profile_candidate"] = tp
    # Skip origin_gloss_candidate when identical to semantic_nucleus (redundant)
    gloss = o.origin_gloss_candidate
    if gloss and gloss != o.semantic_nucleus:
        d["origin_gloss_candidate"] = gloss
    return d


def _ser_branch_record(b) -> dict:
    # branch_id / origin_id omitted — internal IDs
    return {
        "origin_index":              b.origin_index,
        "branch_index":              b.branch_index,
        "source_lexical_form":       b.source_lexical_form,
        "branch_relation_to_origin": _enum_val(b.branch_relation_to_origin),
        "relation_explicitness":     _enum_val(b.relation_explicitness),
        "semantic_distance_candidate": _enum_val(b.semantic_distance_candidate),
    }


def _ser_concept_candidate(cc) -> dict:
    g = cc.genus_candidate
    return {
        "candidate_id":   cc.candidate_id,
        "notice":         ONTOLOGY_CANDIDATE_ONLY,
        "genus_candidate": {
            "genus_nucleus": g.genus_nucleus,
            "genus_kind":    _enum_val(g.genus_kind),
            "upper_kind_candidate": _enum_val(g.upper_kind_candidate),
            "gradability":   _enum_val(g.gradability),
            "persistence":   _enum_val(g.persistence),
        } if g else None,
        "differentia_candidates": [
            {
                "differentia_text": d.differentia_text,
                "property_type":    _enum_val(d.property_type),
                "attribution_mode": _enum_val(d.attribution_mode),
            }
            for d in (cc.differentia_candidates or [])
        ],
        "property_candidates": [
            {
                "property_type": _enum_val(p.property_type),
                "property_text": p.property_text,
                "explicitness":  _enum_val(p.explicitness),
            }
            for p in (cc.property_candidates or [])
        ],
        "relation_candidates": [
            {
                "relation_kind":  _enum_val(r.relation_kind),
                "related_root":   r.related_root,
                "explicitness":   _enum_val(r.explicitness),
            }
            for r in (cc.relation_candidates or [])
        ],
        "opposition_candidates": [
            {
                "opposition_type":   _enum_val(o.opposition_type),
                "opposing_root":     o.opposing_root,
                "opposition_basis":  o.opposition_basis,
            }
            for o in (cc.opposition_candidates or [])
        ],
    }


def _ser_ontology_profile(ocp) -> dict:
    if ocp is None:
        return {
            "status":  "BLOCKED",
            "notice":  ONTOLOGY_CANDIDATE_ONLY,
            "reason":  "blocking residual present — human review required",
            "profile": None,
        }
    return {
        "status":  "BUILT",
        "notice":  ONTOLOGY_CANDIDATE_ONLY,
        "label":   ocp.label,
        "profile_id": ocp.profile_id,
        "concept_candidates": [_ser_concept_candidate(cc) for cc in ocp.concept_candidates],
    }


def _bundle_to_dict(bundle, entry: dict) -> dict:
    """Serialize a MaqayisSourceBundle to a plain JSON-serializable dict."""
    em  = bundle.extraction_meta
    ri  = bundle.root_identity
    se  = bundle.source_evidence
    lcg = bundle.lexical_claim_graph
    sog = bundle.semantic_origin_graph
    ocp = bundle.ontology_candidate_profile

    # layer_summary: strip fields that are canonical elsewhere to avoid repetition.
    # residuals       → canonical in layer_1_extraction_meta
    # ontology_*      → canonical in layer_4_ontology_candidate_profile
    raw_summary = bundle.layer_summary()
    summary = {k: v for k, v in raw_summary.items()
               if k not in ("residuals", "ontology_buildable", "ontology_candidate_profile")}

    # entry: show bab_letter correction as a single annotated field
    bab_raw  = entry.get("bab_letter") or ""
    bab_corr = entry.get("corrected_bab_letter") or ""
    entry_section: dict = {
        "entry_id":    bundle.entry_id,
        "root_letters": entry.get("root_letters"),
        "entry_kind":  bundle.entry_kind.value,
        "bab_letter":  bab_corr or bab_raw,
    }
    if bab_corr and bab_raw and bab_corr != bab_raw:
        entry_section["bab_letter_corrected_from"] = bab_raw
    entry_section["body_lines"]   = len(entry.get("body_line_ids") or [])
    entry_section["poetry_lines"] = len(entry.get("poetry_line_ids") or [])

    result: dict = {
        "_schema": {
            "work_id":         WORK_ID,
            "author_id":       AUTHOR_ID,
            "schema_version":  SCHEMA_VERSION,
            "pipeline_run_id": str(uuid.uuid4()),
            "generated_at":    datetime.now(timezone.utc).isoformat(),
            "notice":          ONTOLOGY_CANDIDATE_ONLY,
        },
        "entry":               entry_section,
        "layer_summary":       summary,
        "layer_1_source_evidence": _ser_source_evidence(se),
        "layer_1_root_identity":   _ser_root_identity(ri),
        "layer_1_extraction_meta": _ser_extraction_meta(em),
        "layer_2_lexical_claim_graph": _ser_lexical_claim_graph(lcg),
        "layer_3_semantic_origin_graph": _ser_semantic_origin_graph(sog),
        "layer_3_lexical_origin_records": [
            _ser_lexical_origin_record(o) for o in bundle.origins
        ],
    }
    # Only include branch_records when there are actual branches
    if bundle.branches:
        result["layer_3_branch_records"] = [
            _ser_branch_record(b) for b in bundle.branches
        ]
    result["layer_4_ontology_candidate_profile"] = _ser_ontology_profile(ocp)
    # Layer D — طبقة الذات (entity ontology classification — fail-open)
    result["layer_d_entity_profile"] = build_layer_d(bundle)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# §2 — PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def analyze_root(
    root_letters: str,
    *,
    entries_jsonl: Union[str, pathlib.Path, None] = None,
    lines_jsonl:   Union[str, pathlib.Path, None] = None,
    output_path:   Union[str, pathlib.Path, None, object] = _AUTO,
    output_dir:    Union[str, pathlib.Path] = "output",
) -> Dict[str, Any]:
    """
    Run the full constitutional pipeline (Layers 1-4 + D) on a single Arabic root.

    Layers
    ──────
    1. SourceEvidence          — provenance, text strata, OCR quality
    2. LexicalClaimGraph       — assertion structure (who said what)
    3. SemanticOriginGraph     — meaning structure (branches, nucleus)
    4. OntologyCandidateProfile — candidate ontological interpretation
    D. EntityProfile (طبقة الذات) — WordNet IS-A entity classification
       for Arabic nouns found in the semantic layers.
       Output key: "layer_d_entity_profile"
       Notice: ENTITY_CANDIDATE_ONLY — not a licensed ontological fact.

    Parameters
    ──────────
    root_letters : str
        Arabic root letters, e.g. "كتب" or "ض ر ب".
    entries_jsonl : path to root_entries_corrected.jsonl (auto-discovered if None)
    lines_jsonl   : path to lines.jsonl                  (auto-discovered if None)
    output_path   : explicit output path for the JSON file.
                    Pass None to disable file writing.
                    Default (_AUTO) → output/<root>.json
    output_dir    : directory for auto-named output files (default: "output").

    Returns
    ───────
    dict  — full serialized MaqayisSourceBundle (JSON-serializable)

    Raises
    ──────
    ValueError   if no entry is found for the given root.
    FileNotFoundError if entries_jsonl or lines_jsonl cannot be resolved.
    """
    # ── Resolve data paths ──────────────────────────────────────────────────
    entries_path = pathlib.Path(entries_jsonl) if entries_jsonl else _DEFAULT_ENTRIES
    lines_path   = pathlib.Path(lines_jsonl)   if lines_jsonl   else _DEFAULT_LINES

    if not entries_path.exists():
        raise FileNotFoundError(f"entries_jsonl not found: {entries_path}")
    if not lines_path.exists():
        raise FileNotFoundError(f"lines_jsonl not found: {lines_path}")

    # ── Normalize root (strip spaces) ───────────────────────────────────────
    root_norm = root_letters.replace(" ", "").strip()

    # ── Find entry ──────────────────────────────────────────────────────────
    entry: Optional[dict] = None
    with open(entries_path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("root_letters", "").replace(" ", "").strip() == root_norm:
                entry = e
                break

    if entry is None:
        raise ValueError(
            f"No entry found for root '{root_letters}' in {entries_path}"
        )

    # ── Build pipeline objects ──────────────────────────────────────────────
    loader  = MaqayisBodyLoader(str(lines_path))
    builder = SourceEvidenceBuilder(
        lines_jsonl=str(lines_path),
        entries_jsonl=str(entries_path),
    )

    # Layer 1
    bundle = builder.build_bundle(entry)

    # Layer 2
    lcg = build_lexical_claim_graph_from_entry(entry, loader)
    bundle.lexical_claim_graph = lcg

    # Layer 3
    claims = extract_claims_from_entry(entry, loader)
    sog, origins, branches = build_semantic_origin_graph(entry, claims)
    attach_layer3_to_bundle(bundle, sog, origins, branches)

    # Layer 4
    attach_layer4_to_bundle(bundle)

    # ── Serialize ───────────────────────────────────────────────────────────
    result = _bundle_to_dict(bundle, entry)

    # ── Write JSON file ─────────────────────────────────────────────────────
    if output_path is _AUTO:
        out_dir = pathlib.Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_root = root_norm.replace("/", "_")
        output_path = out_dir / f"maqayis_{safe_root}.json"

    if output_path is not None:
        out_p = pathlib.Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        result["_output_path"] = str(out_p.resolve())

    return result


# ═══════════════════════════════════════════════════════════════════════════
# §3 — CLI  (python maqayis_pipeline_api.py كتب)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Maqayis constitutional pipeline — single root analysis"
    )
    parser.add_argument("root", help="Arabic root letters, e.g. كتب")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output JSON path (default: output/maqayis_<root>.json)"
    )
    parser.add_argument(
        "--entries", default=None, help="Path to root_entries_corrected.jsonl"
    )
    parser.add_argument(
        "--lines", default=None, help="Path to lines.jsonl"
    )
    args = parser.parse_args()

    result = analyze_root(
        args.root,
        entries_jsonl=args.entries,
        lines_jsonl=args.lines,
        output_path=args.output if args.output else _AUTO,
    )

    out_p = result.get("_output_path", "—")
    ls    = result.get("layer_summary", {})
    em    = result.get("layer_1_extraction_meta", {})

    ld = result.get("layer_d_entity_profile", {})
    ld_summary = ld.get("entity_summary", {})
    ld_words   = ld.get("words_examined", 0)
    ld_clsfd   = ld.get("words_classified", 0)
    ld_skipped = ld.get("_skipped", False)

    print(f"\nالجذر          : {result['entry']['root_letters']}")
    print(f"entry_id       : {result['entry']['entry_id']}")
    print(f"entry_kind     : {ls.get('entry_kind')}")
    print(f"root_id_match  : {ls.get('root_identity_match')}")
    print(f"origins        : {ls.get('origins')}")
    print(f"branches       : {ls.get('branches')}")
    print(f"residuals      : {em.get('residuals')}")
    print(f"ontology       : {'BLOCKED' if not ls.get('ontology_candidate_profile') else 'BUILT'}")
    if ld_skipped:
        print(f"layer_d        : SKIPPED ({ld.get('_skip_reason', '')})")
    else:
        print(f"layer_d (D)    : {ld_clsfd}/{ld_words} مصنَّفة  "
              f"[إنسان:{ld_summary.get('human_count',0)} "
              f"حيوان:{ld_summary.get('animate_count',0)} "
              f"موقع:{ld_summary.get('location_count',0)} "
              f"صناعي:{ld_summary.get('artifact_count',0)} "
              f"مجرد:{ld_summary.get('abstraction_count',0)}]")
    print(f"ملف الإخراج    : {out_p}\n")
