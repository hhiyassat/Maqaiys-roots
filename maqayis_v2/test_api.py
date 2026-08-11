#!/usr/bin/env python3
"""
اختبار سريع لـ maqayis_api من الطرفية
الاستخدام:
    python3 test_api.py                     # يشغّل كل الأمثلة
    python3 test_api.py حكم                 # ROOT_SEMANTIC_ORIGINS لجذر معيّن
    python3 test_api.py --concept المنع     # بحث عكسي
"""

import sys, json
from pathlib import Path

# ── تحديد مسار قاعدة البيانات ─────────────────────────────────────────────
HERE = Path(__file__).parent
DB   = HERE / 'maqayis.db'

sys.path.insert(0, str(HERE))
from maqayis_api import MaqayisAPI

api = MaqayisAPI(str(DB))

def pp(label: str, result: dict):
    """طباعة منسّقة."""
    print(f'\n{"═"*60}')
    print(f'  {label}')
    print(f'{"═"*60}')
    print(json.dumps(result, ensure_ascii=False, indent=2))

# ── وضع سطر الأوامر ───────────────────────────────────────────────────────
args = sys.argv[1:]

if args and args[0] == '--concept':
    concept = args[1] if len(args) > 1 else 'المنع'
    pp(f'CONCEPT_TO_ROOT_SEARCH — {concept}',
       api.query({'query_type': 'CONCEPT_TO_ROOT_SEARCH', 'concept': concept, 'limit': 20}))
    sys.exit()

if args and not args[0].startswith('--'):
    root = args[0]
    pp(f'ROOT_SEMANTIC_ORIGINS — {root}',
       api.query({'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': root}))
    sys.exit()

# ── الوضع الافتراضي: جولة كاملة ───────────────────────────────────────────
queries = [
    ('١. ROOT_SEMANTIC_ORIGINS — حكم',
     {'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': 'حكم'}),

    ('٢. CONCEPT_TO_ROOT_SEARCH — المنع',
     {'query_type': 'CONCEPT_TO_ROOT_SEARCH', 'concept': 'المنع', 'limit': 10}),

    ('٣. ROOT_ORIGIN_RELATIONS — شكر',
     {'query_type': 'ROOT_ORIGIN_RELATIONS', 'root': 'شكر'}),

    ('٤. SOURCE_EVIDENCE_LOOKUP — حكم',
     {'query_type': 'SOURCE_EVIDENCE_LOOKUP', 'root': 'حكم'}),

    ('٥. CLAIM_TO_MAQAYIS_EVIDENCE — قوم/القيام',
     {'query_type': 'CLAIM_TO_MAQAYIS_EVIDENCE', 'root': 'قوم', 'claim_text': 'القيام'}),

    ('٦. ROOT_EXISTS — عدل',
     {'query_type': 'ROOT_EXISTS', 'root': 'عدل'}),

    ('٧. TRACE_LOOKUP — حكم',
     {'query_type': 'TRACE_LOOKUP', 'root': 'حكم'}),

    ('٨. ROOT_SENSE_CANDIDATES — حد',
     {'query_type': 'ROOT_SENSE_CANDIDATES', 'root': 'حد'}),
]

for label, q in queries:
    pp(label, api.query(q))

api.close()
print(f'\n{"═"*60}')
print('  ✓ اكتملت كل الاستعلامات')
print(f'{"═"*60}\n')
