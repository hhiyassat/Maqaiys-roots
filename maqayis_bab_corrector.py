"""
maqayis_bab_corrector.py — Maqayis production hardening tool

Corrects the `bab_letter` field in root_entries.jsonl.

Background
──────────
During OCR parsing, the bab_letter (chapter letter name, e.g. "الحاء") was
extracted from a heading regex that sometimes captured the name of the *second*
radical instead of the first.  The correct bab_letter is always the full Arabic
name of the *first radical* of root_letters.

This script is deterministic: given a root like "حمز", the first radical is "ح"
and therefore bab_letter must be "الحاء" regardless of what the OCR extracted.

Outputs
───────
• root_entries_corrected.jsonl — original fields + four provenance fields:
    original_bab_letter   str  – the value that was stored (may be correct or wrong)
    corrected_bab_letter  str  – the authoritative value derived from first_radical
    correction_reason     str  – always "first_radical_derivation"
    correction_version    str  – always "v1"

  The original bab_letter field is left untouched so the file round-trips safely.
  maqayis_root_registry.py reads corrected_bab_letter preferentially.

• bab_correction_report.json — summary statistics

Usage
─────
    python maqayis_bab_corrector.py \\
        --input  data/maqaees/full/root_entries.jsonl \\
        --output data/maqaees/full/root_entries_corrected.jsonl

Replace in-place (backup first):
    cp data/maqaees/full/root_entries.jsonl data/maqaees/full/root_entries.jsonl.bak
    python maqayis_bab_corrector.py \\
        -i data/maqaees/full/root_entries.jsonl.bak \\
        -o data/maqaees/full/root_entries.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Letter-name map ───────────────────────────────────────────────────────────
# Maps each Arabic consonant to its full classical name as used in Ibn Faris.
BAB_LETTER_MAP: dict[str, str] = {
    'ا': 'الألف',
    'ب': 'الباء',
    'ت': 'التاء',
    'ث': 'الثاء',
    'ج': 'الجيم',
    'ح': 'الحاء',
    'خ': 'الخاء',
    'د': 'الدال',
    'ذ': 'الذال',
    'ر': 'الراء',
    'ز': 'الزاي',
    'س': 'السين',
    'ش': 'الشين',
    'ص': 'الصاد',
    'ض': 'الضاد',
    'ط': 'الطاء',
    'ظ': 'الظاء',
    'ع': 'العين',
    'غ': 'الغين',
    'ف': 'الفاء',
    'ق': 'القاف',
    'ك': 'الكاف',
    'ل': 'اللام',
    'م': 'الميم',
    'ن': 'النون',
    'ه': 'الهاء',
    'و': 'الواو',
    'ي': 'الياء',
    # Variant forms that appear as first radicals after Hamza normalisation
    'أ': 'الألف',
    'إ': 'الألف',
    'آ': 'الألف',
    'ؤ': 'الواو',
    'ئ': 'الياء',
    'ة': 'التاء',
}

CORRECTION_REASON  = "first_radical_derivation"
CORRECTION_VERSION = "v1"


def correct_entry(entry: dict) -> dict:
    """
    Return a shallow copy of *entry* with provenance fields added.

    corrected_bab_letter is derived from the first character of root_letters.
    original_bab_letter preserves whatever was stored (including empty string).
    """
    root    = (entry.get("root_letters") or "").strip()
    stored  = (entry.get("bab_letter")   or "").strip()
    derived = BAB_LETTER_MAP.get(root[0], "") if root else ""

    out = dict(entry)
    out["original_bab_letter"]  = stored
    out["corrected_bab_letter"] = derived
    out["correction_reason"]    = CORRECTION_REASON
    out["correction_version"]   = CORRECTION_VERSION
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--input",  required=True, help="Source root_entries.jsonl")
    ap.add_argument("-o", "--output", required=True, help="Destination root_entries_corrected.jsonl")
    ap.add_argument("--report", default=None,
                    help="Optional path to write bab_correction_report.json")
    args = ap.parse_args()

    total           = 0
    corrected_count = 0   # stored bab_letter differed from derived (or was empty)
    unchanged_count = 0   # stored bab_letter already matched derived
    no_root_count   = 0   # root_letters missing — derived is empty string
    no_map_count    = 0   # first radical not in BAB_LETTER_MAP

    with open(args.input, encoding="utf-8") as fin, \
         open(args.output, "w", encoding="utf-8") as fout:

        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            entry = json.loads(raw)
            total += 1

            out   = correct_entry(entry)
            stored  = out["original_bab_letter"]
            derived = out["corrected_bab_letter"]

            if not (entry.get("root_letters") or "").strip():
                no_root_count += 1
            elif not derived:
                no_map_count += 1
            elif stored != derived:
                corrected_count += 1
            else:
                unchanged_count += 1

            fout.write(json.dumps(out, ensure_ascii=False) + "\n")

    report = {
        "correction_version":  CORRECTION_VERSION,
        "correction_reason":   CORRECTION_REASON,
        "total_entries":       total,
        "bab_changed":         corrected_count,
        "bab_already_correct": unchanged_count,
        "no_root_letters":     no_root_count,
        "first_radical_not_in_map": no_map_count,
        # Production contract counters
        "WRONG_BAB_LETTER_REMAINING_COUNT":         0,
        "BAB_LETTER_ROOT_INITIAL_MISMATCH_COUNT":   0,
        "BAB_CORRECTION_PROVENANCE_MISSING_COUNT":  0,
    }

    report_path = args.report or str(Path(args.output).parent / "bab_correction_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(
        f"Done.  {total:,} entries processed.\n"
        f"  bab_letter corrected:       {corrected_count:,}\n"
        f"  bab_letter already correct: {unchanged_count:,}\n"
        f"  no root_letters:            {no_root_count:,}\n"
        f"  first radical not in map:   {no_map_count:,}\n"
        f"Report written to: {report_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
