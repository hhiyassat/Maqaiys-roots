"""
maqayis_v2_adapter.py — Hokom/Taaqol integration bridge
=========================================================
يربط معجم المقاييس الإلكتروني (v2) بـ Hokom pipeline.

المسار الثابت لقاعدة البيانات:
    ~/maqayis/maqayis.db

الاستخدام:
    from pipeline.taaqol_integration.maqayis_v2_adapter import (
        get_root_claims,
        get_evidence_ids,
        check_claim,
        find_roots_by_concept,
    )

    # ١. ادعاءات الجذر (المحاور الدلالية)
    claims = get_root_claims('حكم')
    # → [{'claim_text': 'المنع', 'evidence': '...', ...}]

    # ٢. evidence IDs للـ EvidenceContract
    ids = get_evidence_ids('حكم')
    # → ('maqayis:v2:حكم:axis:1:المنع', ...)

    # ٣. اختبار ادعاء محدد
    result = check_claim('حكم', 'المنع')
    # → 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'NOT_SUPPORTED'

    # ٤. بحث عكسي: من مفهوم إلى جذور
    roots = find_roots_by_concept('المنع')
    # → [{'root_display': 'حكم', 'matched_axis': 'المنع'}, ...]

Fail-open contract:
    كل الدوال تلتقط الأخطاء وتعيد قيمة فارغة — خطأ في المعجم
    لا يوقف الـ pipeline أبداً.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# ── مسار قاعدة البيانات ───────────────────────────────────────────────────────
_DB_PATH = Path.home() / 'maqayis' / 'maqayis.db'
_API_PATH = Path.home() / 'maqayis'

# أضف مسار المعجم لـ Python path
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

# ── تحميل الـ API ─────────────────────────────────────────────────────────────
try:
    from maqayis_api import MaqayisAPI, root_claims as _root_claims_fn
    _API_AVAILABLE = True
except ImportError:
    _API_AVAILABLE = False


def _api() -> Optional['MaqayisAPI']:
    """يعيد instance من MaqayisAPI أو None إن لم تكن قاعدة البيانات موجودة."""
    if not _API_AVAILABLE:
        return None
    if not _DB_PATH.exists():
        return None
    return MaqayisAPI(str(_DB_PATH))


# ── الدوال الرئيسية ───────────────────────────────────────────────────────────

def get_root_claims(root: str) -> list[dict]:
    """
    يعيد ادعاءات ابن فارس عن الجذر (المحاور الدلالية + الدليل).

    المخرج: قائمة من:
        {
            'root_display' : str,
            'claim_text'   : str | None,   # المحور الدلالي
            'claim_rank'   : int,           # ١، ٢، ٣...
            'claim_type'   : str,           # SEMANTIC_AXIS | RAW_TEXT_ONLY
            'source'       : str,           # IBN_FARIS_DIRECT
            'evidence'     : str,           # النص الأصلي من المعجم
        }
    """
    try:
        if not _API_AVAILABLE or not _DB_PATH.exists():
            return []
        result = _root_claims_fn(str(_DB_PATH), root)
        return result.get('claims', [])
    except Exception:
        return []


def get_evidence_ids(root: str) -> tuple[str, ...]:
    """
    يعيد evidence IDs للـ EvidenceContract بصيغة:
        maqayis:v2:{root}:axis:{n}:{axis_text}
        maqayis:v2:{root}:type:{entry_type}

    متوافق مع النمط القديم لكن بمعلومات أغنى.
    """
    try:
        claims = get_root_claims(root)
        if not claims:
            return ()
        ids: list[str] = []
        for c in claims:
            if c.get('claim_text'):
                ax = c['claim_text'][:40].replace(' ', '_')
                ids.append(f"maqayis:v2:{root}:axis:{c['claim_rank']}:{ax}")
        # نوع المدخلة (SINGLE_ORIGIN / MULTI_ORIGIN / ...)
        api = _api()
        if api:
            r = api.query({'query_type': 'ROOT_EXISTS', 'root': root})
            api.close()
            statuses = (r.get('results') or {}).get('entry_statuses', [])
            if statuses:
                ids.append(f"maqayis:v2:{root}:type:{statuses[0]}")
        return tuple(ids)
    except Exception:
        return ()


def check_claim(root: str, claim_text: str) -> str:
    """
    يتحقق إذا كان ابن فارس يدعم ادعاءً معيناً لجذر معيّن.

    المخرج: 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'NOT_SUPPORTED' | 'ERROR'
    """
    try:
        api = _api()
        if not api:
            return 'ERROR'
        r = api.query({
            'query_type': 'CLAIM_TO_MAQAYIS_EVIDENCE',
            'root': root,
            'claim_text': claim_text,
        })
        api.close()
        return (r.get('results') or {}).get('claim_status', 'NOT_SUPPORTED')
    except Exception:
        return 'ERROR'


def find_roots_by_concept(concept: str, limit: int = 20) -> list[dict]:
    """
    بحث عكسي: من مفهوم إلى الجذور التي تشاركه.

    المخرج: قائمة من:
        {
            'root_display' : str,
            'root_letters' : str,
            'matched_axis' : str | None,
            'match_type'   : str,
        }
    """
    try:
        api = _api()
        if not api:
            return []
        r = api.query({
            'query_type': 'CONCEPT_TO_ROOT_SEARCH',
            'concept': concept,
            'limit': limit,
        })
        api.close()
        return r.get('results') or []
    except Exception:
        return []


def get_root_summary(root: str) -> Optional[dict]:
    """
    ملخص شامل للجذر: الأصول + المحاور + الدليل.

    المخرج:
        {
            'found'   : bool,
            'root'    : str,
            'entries' : [
                {
                    'root_display'  : str,
                    'entry_type'    : str,
                    'axes_count'    : int,
                    'axes'          : [str, ...],
                    'evidence_text' : str,
                    'ocr_confidence': float,
                }
            ]
        }
    """
    try:
        if not _API_AVAILABLE or not _DB_PATH.exists():
            return None
        from maqayis_api import root_summary
        return root_summary(str(_DB_PATH), root)
    except Exception:
        return None


# ── اختبار سريع ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import json

    print(f'قاعدة البيانات: {_DB_PATH}')
    print(f'متاحة: {_DB_PATH.exists()}')
    print()

    for root in ['حكم', 'كتب', 'حد', 'قوم']:
        print(f'══ {root} ══')
        claims = get_root_claims(root)
        for c in claims[:2]:
            print(f'  ادعاء: {c["claim_text"]}')
        ids = get_evidence_ids(root)
        print(f'  IDs: {ids}')
        print(f'  check "المنع": {check_claim(root, "المنع")}')
        print()

    print('بحث عكسي — المنع:')
    for r in find_roots_by_concept('المنع', limit=5):
        print(f'  {r["root_display"]} ← {r.get("matched_axis", "")}')
