# مقاييس اللغة — Maqayis Roots

قاعدة بيانات وواجهة برمجية لـ **مقاييس اللغة** لابن فارس (ت 395هـ).  
تُغطّي **4,537 جذراً** لغوياً موثَّقاً، مع محاور دلالية ونصوص شاهدة.

---

## المتطلبات

- Python 3.9+
- SQLite (مدمج في Python)

---

## بناء قاعدة البيانات

قاعدة البيانات غير مُرفَقة في المستودع لحجمها. أنشِئها بأمرين:

```bash
python maqayis_v2/build_db.py    # يبني maqayis.db من النصوص المُستخرَجة
python maqayis_v2/enrich.py      # يُثري المدخلات بمحاور دلالية وأنماط صرفية
```

الملف الناتج: `maqayis_v2/maqayis.db` (SQLite، ~9 MB).

---

## API

### الاستيراد والتهيئة

```python
from maqayis_v2.maqayis_api import MaqayisAPI, root_summary

api = MaqayisAPI("maqayis_v2/maqayis.db")
```

---

### 1. البحث بالجذر — ROOT_LOOKUP

```python
result = api.query({
    'query_type': 'ROOT_LOOKUP',
    'root': 'كتب',
})

# result['found']         → True / False
# result['results']       → قائمة المدخلات
# result['canonical_root'] → الجذر القانوني
```

كل مدخلة في `results` تحتوي:

| الحقل | الوصف |
|---|---|
| `root_letters` | حروف الجذر |
| `root_display` | الجذر بشكل العرض |
| `entry_type` | نوع المدخلة |
| `semantic_axes` | المحاور الدلالية (قائمة) |
| `body_text` | النص الأصلي من المعجم |
| `poetry_lines` | الشواهد الشعرية |
| `axes_count` | عدد المحاور |

---

### 2. المحاور الدلالية — ROOT_SEMANTIC_ORIGINS

```python
result = api.query({
    'query_type': 'ROOT_SEMANTIC_ORIGINS',
    'root': 'قوم',
})

for entry in result['results']:
    for ax in entry['semantic_axes']:
        print(ax['axis_text'])
```

---

### 3. التحقق من وجود الجذر — ROOT_EXISTS

```python
result = api.query({
    'query_type': 'ROOT_EXISTS',
    'root': 'علم',
})

# result['found']          → True
# result['results']['canonical_root'] → 'علم'
# result['results']['entry_count']    → عدد المدخلات
```

---

### 4. الهوية القانونية للجذر — ROOT_CANONICAL_IDENTITY

```python
result = api.query({
    'query_type': 'ROOT_CANONICAL_IDENTITY',
    'root': 'رئس',   # بأي شكل إملائي
})

r = result['results']
# r['root_letters']  → الجذر القانوني
# r['root_display']  → شكل العرض
# r['ambiguous']     → True إذا كان للجذر أكثر من مدخلة
# r['is_geminate']   → True إذا كان الجذر ثنائياً
```

---

### 5. البحث عكسياً بالمفهوم — SEMANTIC_REVERSE_SEARCH

```python
result = api.query({
    'query_type': 'SEMANTIC_REVERSE_SEARCH',
    'concept': 'القوة والشدة',
})

for entry in result['results']:
    print(entry['root_letters'], entry['relevance_score'])
```

---

### 6. دليل الادعاء — CLAIM_TO_MAQAYIS_EVIDENCE

يبحث عن نص مُعيَّن داخل مدخلة جذر محدَّد:

```python
result = api.query({
    'query_type': 'CLAIM_TO_MAQAYIS_EVIDENCE',
    'root': 'قوم',
    'claim_text': 'القيام',
})

r = result['results']
# r['claim_status']  → 'CONFIRMED' / 'NOT_FOUND'
# r['evidence_text'] → المقطع الذي وُجد فيه النص
```

---

### 7. ملخص الجذر — دالة مساعدة

```python
from maqayis_v2.maqayis_api import root_summary

summary = root_summary("maqayis_v2/maqayis.db", "كتب")

# summary['found']   → True
# summary['root']    → 'كتب'
# summary['entries'] → قائمة تحتوي:
#   - root_display, entry_type, axes_count
#   - axes          → نصوص المحاور الدلالية
#   - evidence_text → مقتطف من المعجم
#   - ocr_confidence
```

---

### 8. إحصاءات قاعدة البيانات

```python
stats = api.stats()
# {
#   'total_entries': 4537,
#   'total_axes': ...,
#   'total_poetry_lines': ...,
#   'entry_types': {'root': ..., 'branch': ...},
# }
```

---

### أنواع الاستعلامات المتاحة

| query_type | الوصف |
|---|---|
| `ROOT_LOOKUP` | بحث مباشر بالجذر مع كامل المدخلة |
| `ROOT_SEMANTIC_ORIGINS` | المحاور الدلالية لجذر |
| `ROOT_EXISTS` | هل الجذر موجود في المقاييس؟ |
| `ROOT_CANONICAL_IDENTITY` | الهوية القانونية والإملاء الأصلي |
| `SEMANTIC_REVERSE_SEARCH` | بحث عكسي بالمفهوم |
| `CONCEPT_TO_ROOT_SEARCH` | من مفهوم إلى جذر |
| `CLAIM_TO_MAQAYIS_EVIDENCE` | هل ادعاء مُعيَّن موثَّق في مدخلة؟ |
| `ROOT_MEANING_EVIDENCE_RETRIEVAL` | استرجاع دليل المعنى |
| `ROOT_ORIGIN_RELATIONS` | علاقات الأصول بين الجذور |
| `DERIVATIVE_TO_ORIGIN_ATTESTATION` | إسناد المشتق إلى أصله |
| `SOURCE_EVIDENCE_LOOKUP` | البحث في مصادر المعجم |
| `ROOT_SENSE_CANDIDATES` | مرشَّحات المعاني لجذر |
| `RECORD_INTEGRITY_LOOKUP` | سلامة السجل |
| `TRACE_LOOKUP` | تتبع المدخلة |

---

## بنية الاستجابة

كل استجابة تُعيد:

```json
{
  "found": true,
  "query_status": "OK",
  "canonical_root": "كتب",
  "results": { ... },
  "source_entry_ids": [42]
}
```

---

## هيكل المشروع

| المجلد / الملف | الوصف |
|---|---|
| `maqayis_v2/maqayis_api.py` | الـ API الرئيسية — ابدأ من هنا |
| `maqayis_v2/build_db.py` | بناء قاعدة البيانات من النصوص |
| `maqayis_v2/enrich.py` | إثراء المدخلات بمحاور دلالية |
| `maqayis_v2/enrich_patterns.py` | أنماط الإثراء الصرفي |
| `maqayis_v2/maqayis_v2_adapter.py` | محوِّل التوافق |
| `maqayis_pipeline/` | خطوط معالجة: استخراج الادعاءات، الرسم الدلالي |
| `maqayis_root_registry.py` | سجل الجذور الموثَّقة (4,537 جذر) |
| `maqayis_viewer.html` | واجهة تصفح تفاعلية (افتحها في المتصفح) |
| `maqayis_viewer_v2.html` | واجهة v2 المُحسَّنة |
| `output/` | مخرجات JSON — مثال: `output/maqayis_كتب.json` |
| `shamela_scraper/` | أداة استخراج النصوص من الشاملة |
| `maqayis_test_env/` | بيئة الاختبار والعقود |

---

## مثال كامل

```python
from maqayis_v2.maqayis_api import MaqayisAPI

api = MaqayisAPI("maqayis_v2/maqayis.db")

# تحقق من وجود جذر
r = api.query({'query_type': 'ROOT_EXISTS', 'root': 'علم'})
print(r['found'])  # True

# استرجع محاوره الدلالية
r = api.query({'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': 'علم'})
for entry in r['results']:
    for ax in entry['semantic_axes']:
        print(ax['axis_text'])

# ابحث عن جذر بمفهوم
r = api.query({'query_type': 'SEMANTIC_REVERSE_SEARCH', 'concept': 'البيان والوضوح'})

api.close()
```

---

## المصدر

نصوص مقاييس اللغة من موقع الشاملة (shamela.ws) — للاستخدام الأكاديمي البحثي فقط.
