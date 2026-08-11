"""
معجم المقاييس الإلكتروني — واجهة الاستفسار
==============================================
العائلات السبع:

1. ROOT_LOOKUP              — بحث مباشر بالجذر
2. ROOT_QUALIFICATION       — الوجود والاكتمال وحالة المراجعة
3. SEMANTIC_REVERSE_SEARCH  — من مفهوم إلى جذور
4. CLAIM_EVIDENCE           — هل الادعاء مدعوم؟
5. ROOT_ORIGIN_RELATIONS    — تعدد الأصول والتداخل
6. SOURCE_AND_PROVENANCE    — النص الخام والصفحة وصاحب القول
7. TRACE_AND_INTEGRITY      — مسار المعالجة والأخطاء

الاستخدام:
    api = MaqayisAPI('/path/to/maqayis.db')
    result = api.query({
        'caller': 'HOKOM',
        'query_type': 'ROOT_SEMANTIC_ORIGINS',
        'root': 'قوم',
    })
"""

import sqlite3, json, re
from pathlib import Path
from typing import Any

# ── التطبيع ────────────────────────────────────────────────────────────────────

def _norm(t: str) -> str:
    t = re.sub(r'[ً-ْٰٱ]', '', t)           # حذف التشكيل
    t = re.sub(r'[أإآ]', 'ا', t)             # توحيد الألف
    t = re.sub(r'ى', 'ي', t)                  # ألف مقصورة
    t = re.sub(r'ة', 'ه', t)                  # تاء مربوطة
    t = re.sub(r'\s+', ' ', t.strip())
    return t

def _norm_root(root: str) -> str:
    """يطبّع الجذر للبحث — يزيل المسافات والتشكيل."""
    return _norm(root.replace(' ', ''))

# ── بنية الجواب المعياري ───────────────────────────────────────────────────────

def _envelope(
    found: bool,
    query_status: str,
    canonical_root: str | None,
    results: Any,
    *,
    source_entry_ids: list = None,
    review_state: str = None,
    confidence: float = None,
    partial_load: bool = False,
    malformed_line_count: int = 0,
    residuals: list = None,
    error: str = None,
) -> dict:
    return {
        'found': found,
        'query_status': query_status,
        'canonical_root': canonical_root,
        'results': results,
        'source_entry_ids': source_entry_ids or [],
        'review_state': review_state,
        'confidence': confidence,
        'partial_load': partial_load,
        'malformed_line_count': malformed_line_count,
        'residuals': residuals or [],
        'error': error,
    }

# ── الـ API ────────────────────────────────────────────────────────────────────

class MaqayisAPI:
    """واجهة الاستفسار الرئيسية لمعجم المقاييس الإلكتروني."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._con: sqlite3.Connection | None = None

    def _db(self) -> sqlite3.Connection:
        if self._con is None:
            self._con = sqlite3.connect(self._db_path, check_same_thread=False)
            self._con.row_factory = sqlite3.Row
        return self._con

    def close(self):
        if self._con:
            self._con.close()
            self._con = None

    # ──────────────────────────────────────────────────────────────────────────
    # الدالة الرئيسية
    # ──────────────────────────────────────────────────────────────────────────

    def query(self, request: dict) -> dict:
        qt = request.get('query_type', '')
        handlers = {
            # العائلة ١: بحث مباشر
            'ROOT_LOOKUP':              self._root_lookup,
            'ROOT_SEMANTIC_ORIGINS':    self._root_semantic_origins,
            # العائلة ٢: التأهيل
            'ROOT_EXISTS':              self._root_exists,
            'ROOT_CANONICAL_IDENTITY':  self._root_canonical_identity,
            'ROOT_EXISTENCE_AND_QUALIFICATION': self._root_exists,
            'ENTRY_QUALIFICATION':      self._entry_qualification,
            # العائلة ٣: بحث عكسي
            'SEMANTIC_REVERSE_SEARCH':  self._semantic_reverse_search,
            'CONCEPT_TO_ROOT_SEARCH':   self._concept_to_root_search,
            # العائلة ٤: الدليل على الادعاء
            'CLAIM_TO_MAQAYIS_EVIDENCE': self._claim_evidence,
            'ROOT_MEANING_EVIDENCE_RETRIEVAL': self._root_meaning_evidence,
            'CLAIM_EVIDENCE':           self._claim_evidence,
            # العائلة ٥: علاقات الأصول
            'ROOT_ORIGIN_RELATIONS':    self._root_origin_relations,
            'ROOT_INTERNAL_CONFLICT_LOOKUP': self._root_conflict,
            'DERIVATIVE_TO_ORIGIN_ATTESTATION': self._derivative_attestation,
            # العائلة ٦: المصدر والنسب
            'SOURCE_EVIDENCE_LOOKUP':   self._source_evidence,
            'CLAIM_ATTRIBUTION_LOOKUP': self._claim_attribution,
            'ROOT_SENSE_CANDIDATES':    self._root_sense_candidates,
            # العائلة ٧: التتبع والسلامة
            'RECORD_INTEGRITY_LOOKUP':  self._record_integrity,
            'TRACE_LOOKUP':             self._trace_lookup,
            'ASSERTION_PROVENANCE_CHECK': self._assertion_provenance,
        }
        handler = handlers.get(qt)
        if not handler:
            return _envelope(False, 'UNKNOWN_QUERY_TYPE', None, None,
                             error=f'query_type غير معروف: {qt}')
        try:
            return handler(request)
        except Exception as exc:
            return _envelope(False, 'ERROR', None, None, error=str(exc))

    # ──────────────────────────────────────────────────────────────────────────
    # ١. ROOT_LOOKUP — بحث مباشر بالجذر
    # ──────────────────────────────────────────────────────────────────────────

    def _find_entries(self, root: str) -> list[sqlite3.Row]:
        """يبحث عن مدخلات الجذر بأشكاله المختلفة."""
        nr = _norm_root(root)
        con = self._db()
        cur = con.cursor()
        # بحث مباشر
        cur.execute(
            "SELECT * FROM entries WHERE "
            "replace(replace(root_letters,' ',''),'ا','أ') = ? OR "
            "replace(replace(root_display,' ',''),'ا','أ') LIKE ? "
            "ORDER BY entry_num",
            (nr, nr + '%'),
        )
        rows = cur.fetchall()
        if not rows:
            # بحث مرن بعد تطبيع
            cur.execute(
                "SELECT * FROM entries WHERE "
                "instr(replace(root_letters,' ',''), ?) > 0 "
                "ORDER BY entry_num LIMIT 20",
                (nr[:3],),
            )
            rows = cur.fetchall()
        return rows

    def _entry_to_dict(self, row: sqlite3.Row) -> dict:
        eid = row['id']
        cur = self._db().cursor()
        cur.execute("SELECT * FROM semantic_axes WHERE entry_id=? ORDER BY axis_num", (eid,))
        axes = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT line_text FROM poetry_evidence WHERE entry_id=? ORDER BY line_num", (eid,))
        poetry = [r['line_text'] for r in cur.fetchall()]
        return {
            'entry_id':       eid,
            'entry_num':      row['entry_num'],
            'root_letters':   row['root_letters'],
            'root_display':   row['root_display'],
            'entry_type':     row['entry_type'],
            'axes_count':     row['axes_count'],
            'semantic_axes':  axes,
            'body_text':      row['body_text'],
            'poetry_lines':   poetry,
            'page_refs':      json.loads(row['page_refs'] or '[]'),
            'quoted_authorities': json.loads(row['quoted_authorities'] or '[]'),
            'ocr_confidence': row['ocr_confidence'],
            'review_state':   row['review_state'],
        }

    def _root_lookup(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [], error=f'الجذر {root!r} غير موجود')
        entries = [self._entry_to_dict(r) for r in rows]
        cr = entries[0]['root_letters'] if entries else None
        return _envelope(True, 'OK', cr, entries,
                         source_entry_ids=[e['entry_id'] for e in entries],
                         review_state=entries[0]['review_state'] if entries else None,
                         confidence=entries[0]['ocr_confidence'] if entries else None)

    def _root_semantic_origins(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [],
                             error=f'الجذر {root!r} غير موجود')

        results = []
        for row in rows:
            eid = row['id']
            cur = self._db().cursor()
            cur.execute("SELECT * FROM semantic_axes WHERE entry_id=? ORDER BY axis_num", (eid,))
            axes = [dict(r) for r in cur.fetchall()]
            results.append({
                'root_letters': row['root_letters'],
                'root_display': row['root_display'],
                'entry_type':   row['entry_type'],
                'axes_count':   row['axes_count'],
                'semantic_axes': axes,
                'body_excerpt': row['body_text'][:300] + ('…' if len(row['body_text']) > 300 else ''),
                'page_refs':    json.loads(row['page_refs'] or '[]'),
                'ocr_confidence': row['ocr_confidence'],
            })

        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows],
                         review_state=rows[0]['review_state'],
                         confidence=min(r['ocr_confidence'] for r in rows))

    # ──────────────────────────────────────────────────────────────────────────
    # ٢. ROOT_QUALIFICATION — التأهيل
    # ──────────────────────────────────────────────────────────────────────────

    def _root_exists(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        found = len(rows) > 0
        result = {
            'found': found,
            'canonical_root': rows[0]['root_letters'] if found else None,
            'entry_count': len(rows),
            'entry_statuses': [r['entry_type'] for r in rows],
            'review_states':  [r['review_state'] for r in rows],
        }
        return _envelope(found, 'OK' if found else 'NOT_FOUND',
                         rows[0]['root_letters'] if found else None,
                         result,
                         source_entry_ids=[r['id'] for r in rows])

    def _root_canonical_identity(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None,
                             {'found': False, 'canonical_root': None})
        r0 = rows[0]
        return _envelope(True, 'OK', r0['root_letters'], {
            'root_letters':  r0['root_letters'],
            'root_display':  r0['root_display'],
            'entry_type':    r0['entry_type'],
            'is_geminate':   len(r0['root_letters'].replace(' ','')) == 2,
            'ambiguous':     len(rows) > 1,
            'all_entries':   [{'entry_id': r['id'], 'root_letters': r['root_letters'],
                                'root_display': r['root_display']} for r in rows],
        }, source_entry_ids=[r['id'] for r in rows])

    def _entry_qualification(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, {'entry_status': 'ABSENT'})
        results = []
        for row in rows:
            results.append({
                'entry_id':      row['id'],
                'root_letters':  row['root_letters'],
                'root_display':  row['root_display'],
                'entry_type':    row['entry_type'],
                'axes_count':    row['axes_count'],
                'ocr_confidence': row['ocr_confidence'],
                'review_state':  row['review_state'],
                'claim_status':  row['claim_status'],
                'has_body':      bool(row['body_text']),
                'source_available': True,
            })
        avg_conf = sum(r['ocr_confidence'] or 1.0 for r in results) / len(results)
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows],
                         confidence=round(avg_conf, 2),
                         partial_load=any(r['entry_type'] == 'UNKNOWN' for r in results))

    # ──────────────────────────────────────────────────────────────────────────
    # ٣. SEMANTIC_REVERSE_SEARCH — من مفهوم إلى جذور
    # ──────────────────────────────────────────────────────────────────────────

    def _semantic_reverse_search(self, req: dict) -> dict:
        concept = req.get('concept_id') or req.get('claim_text') or ''
        return self._concept_to_root_search({**req, 'concept': concept})

    def _concept_to_root_search(self, req: dict) -> dict:
        concept = req.get('concept') or req.get('claim_text') or req.get('concept_id') or ''
        if not concept:
            return _envelope(False, 'MISSING_PARAM', None, [],
                             error='يجب تقديم concept أو claim_text')

        nc = _norm(concept)
        con = self._db()
        cur = con.cursor()

        # بحث في axes_fts أولاً (أسرع وأدق)
        try:
            cur.execute(
                "SELECT sa.entry_id, sa.axis_text, sa.attribution "
                "FROM axes_fts ft "
                "JOIN semantic_axes sa ON ft.rowid = sa.id "
                "WHERE axes_fts MATCH ? "
                "LIMIT 50",
                (concept,),
            )
            fts_rows = cur.fetchall()
        except Exception:
            fts_rows = []

        # بحث عادي في axis_text
        cur.execute(
            "SELECT sa.entry_id, sa.axis_text, sa.attribution, e.root_letters, e.root_display "
            "FROM semantic_axes sa JOIN entries e ON sa.entry_id = e.id "
            "WHERE sa.axis_text LIKE ? OR sa.axis_text LIKE ? "
            "ORDER BY sa.entry_id LIMIT 50",
            (f'%{nc}%', f'%{concept}%'),
        )
        direct_rows = cur.fetchall()

        # بحث في body_text (LIKE — أبطأ لكن شامل)
        cur.execute(
            "SELECT e.id, e.root_letters, e.root_display, e.entry_type "
            "FROM entries e "
            "WHERE e.body_text LIKE ? "
            "LIMIT 30",
            (f'%{concept}%',),
        )
        body_rows = cur.fetchall()

        # تجميع النتائج مع تصنيف المصدر
        seen = set()
        results = []

        for row in direct_rows:
            eid = row['entry_id']
            if eid in seen: continue
            seen.add(eid)
            results.append({
                'entry_id':     eid,
                'root_letters': row['root_letters'],
                'root_display': row['root_display'],
                'match_type':   'ROOT_EXPLICITLY_LINKED_BY_IBN_FARIS'
                                if row['attribution'] == 'IBN_FARIS_DIRECT'
                                else 'ROOT_LINKED_BY_QUOTED_AUTHORITY',
                'matched_axis': row['axis_text'],
            })

        for row in body_rows:
            eid = row['id']
            if eid in seen: continue
            seen.add(eid)
            results.append({
                'entry_id':     eid,
                'root_letters': row['root_letters'],
                'root_display': row['root_display'],
                'match_type':   'ROOT_SEMANTICALLY_SIMILAR',
                'matched_axis': None,
            })

        return _envelope(bool(results), 'OK' if results else 'NOT_FOUND',
                         None, results,
                         source_entry_ids=[r['entry_id'] for r in results])

    # ──────────────────────────────────────────────────────────────────────────
    # ٤. CLAIM_EVIDENCE — الدليل على الادعاء
    # ──────────────────────────────────────────────────────────────────────────

    def _claim_evidence(self, req: dict) -> dict:
        root = req.get('root', '')
        claim = req.get('claim_text', '')
        filters = req.get('filters', {})

        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None,
                             {'claim_status': 'NOT_SUPPORTED', 'reason': 'الجذر غير موجود'},
                             error=f'الجذر {root!r} غير موجود')

        nc = _norm(claim)
        con = self._db()
        cur = con.cursor()

        evidence = []
        claim_status = 'NOT_SUPPORTED'

        for row in rows:
            eid = row['id']
            # فحص في الأصول المعنوية
            cur.execute(
                "SELECT * FROM semantic_axes WHERE entry_id=? ORDER BY axis_num", (eid,)
            )
            axes = cur.fetchall()

            for ax in axes:
                ax_norm = _norm(ax['axis_text'])
                if nc and (nc in ax_norm or ax_norm in nc or
                           any(w in ax_norm for w in nc.split() if len(w) > 2)):
                    evidence.append({
                        'entry_id':   eid,
                        'root_letters': row['root_letters'],
                        'source_type': 'SEMANTIC_AXIS',
                        'text':        ax['axis_text'],
                        'attribution': ax['attribution'],
                        'claim_support': 'SUPPORTED',
                    })
                    claim_status = 'SUPPORTED'

            # فحص في body_text
            if claim and claim in row['body_text']:
                if not any(e['entry_id'] == eid for e in evidence):
                    evidence.append({
                        'entry_id':   eid,
                        'root_letters': row['root_letters'],
                        'source_type': 'BODY_TEXT',
                        'text':        _excerpt(row['body_text'], claim),
                        'attribution': 'IBN_FARIS_DIRECT',
                        'claim_support': 'PARTIALLY_SUPPORTED',
                    })
                    if claim_status == 'NOT_SUPPORTED':
                        claim_status = 'PARTIALLY_SUPPORTED'

        # تطبيق الفلاتر
        if filters.get('author_position') == 'ADOPTED_BY_IBN_FARIS':
            evidence = [e for e in evidence if e['attribution'] == 'IBN_FARIS_DIRECT']

        if not evidence and rows:
            claim_status = 'NOT_SUPPORTED'

        return _envelope(bool(evidence), 'OK',
                         rows[0]['root_letters'], {
                             'claim_status':  claim_status,
                             'claim_text':    claim,
                             'evidence':      evidence,
                             'entries_checked': len(rows),
                         },
                         source_entry_ids=[r['id'] for r in rows],
                         confidence=min(r['ocr_confidence'] for r in rows))

    def _root_meaning_evidence(self, req: dict) -> dict:
        """يعيد الشواهد المرشحة من body_text لمعنى بعينه."""
        root = req.get('root', '')
        concept = req.get('concept_id') or req.get('claim_text') or ''
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])

        results = []
        for row in rows:
            excerpt = _excerpt(row['body_text'], concept) if concept else row['body_text'][:200]
            results.append({
                'entry_id':    row['id'],
                'root_letters': row['root_letters'],
                'body_excerpt': excerpt,
                'page_refs':   json.loads(row['page_refs'] or '[]'),
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    # ──────────────────────────────────────────────────────────────────────────
    # ٥. ROOT_ORIGIN_RELATIONS — علاقات الأصول
    # ──────────────────────────────────────────────────────────────────────────

    def _root_origin_relations(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])

        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT * FROM semantic_axes WHERE entry_id=? ORDER BY axis_num", (row['id'],))
            axes = [dict(r) for r in cur.fetchall()]
            has_conflict = len(axes) > 1
            results.append({
                'entry_id':     row['id'],
                'root_letters': row['root_letters'],
                'axes_count':   row['axes_count'],
                'semantic_axes': axes,
                'has_multiple_origins': has_conflict,
                'generalization_scope': (
                    'FULL' if row['entry_type'] == 'SINGLE_ORIGIN'
                    else 'PARTIAL' if has_conflict
                    else 'UNKNOWN'
                ),
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    def _root_conflict(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, {'conflict': False})
        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT COUNT(*) FROM semantic_axes WHERE entry_id=?", (row['id'],))
            ax_count = cur.fetchone()[0]
            results.append({
                'entry_id':    row['id'],
                'axes_count':  ax_count,
                'has_conflict': ax_count > 1,
                'entry_type':  row['entry_type'],
                'residuals':   row['entry_type'] == 'UNKNOWN',
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    def _derivative_attestation(self, req: dict) -> dict:
        """يبحث عن ذِكر مشتق بعينه في مداخل جذر."""
        root = req.get('root', '')
        lemma = req.get('lemma', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        results = []
        for row in rows:
            if lemma and lemma in row['body_text']:
                results.append({
                    'entry_id':    row['id'],
                    'root_letters': row['root_letters'],
                    'lemma_found': True,
                    'excerpt':     _excerpt(row['body_text'], lemma),
                })
        return _envelope(bool(results), 'OK' if results else 'NOT_FOUND',
                         rows[0]['root_letters'] if rows else None, results,
                         source_entry_ids=[r['id'] for r in rows])

    # ──────────────────────────────────────────────────────────────────────────
    # ٦. SOURCE_AND_PROVENANCE — المصدر والنسب
    # ──────────────────────────────────────────────────────────────────────────

    def _source_evidence(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT * FROM source_passages WHERE entry_id=? ORDER BY passage_num", (row['id'],))
            passages = [dict(r) for r in cur.fetchall()]
            results.append({
                'entry_id':    row['id'],
                'root_letters': row['root_letters'],
                'body_text':   row['body_text'],
                'page_refs':   json.loads(row['page_refs'] or '[]'),
                'source':      row['source'],
                'passages':    passages,
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    def _claim_attribution(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT attribution, axis_text FROM semantic_axes WHERE entry_id=?", (row['id'],))
            axes = cur.fetchall()
            authorities = json.loads(row['quoted_authorities'] or '[]')
            results.append({
                'entry_id':    row['id'],
                'root_letters': row['root_letters'],
                'axes_attributions': [
                    {'axis': a['axis_text'], 'attribution': a['attribution']} for a in axes
                ],
                'quoted_authorities': authorities,
                'note': ('المداخل التي لا يُصرَّح فيها بنسب هي من كلام ابن فارس مباشرةً'
                         if not authorities else None),
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    def _root_sense_candidates(self, req: dict) -> dict:
        """يعيد الأصول المعنوية المرشحة للمقارنة بالسياق."""
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT * FROM semantic_axes WHERE entry_id=? ORDER BY axis_num", (row['id'],))
            axes = [dict(r) for r in cur.fetchall()]
            results.append({
                'entry_id':     row['id'],
                'root_letters': row['root_letters'],
                'sense_candidates': [
                    {'axis_num': ax['axis_num'],
                     'text': ax['axis_text'],
                     'attribution': ax['attribution']}
                    for ax in axes
                ],
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    def _assertion_provenance(self, req: dict) -> dict:
        """يتحقق هل الأصل المعنوي صريح من ابن فارس أم مستنبط."""
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        results = []
        for row in rows:
            cur = self._db().cursor()
            cur.execute("SELECT * FROM semantic_axes WHERE entry_id=?", (row['id'],))
            axes = cur.fetchall()
            results.append({
                'entry_id':    row['id'],
                'root_letters': row['root_letters'],
                'axes': [{
                    'text': ax['axis_text'],
                    'attribution': ax['attribution'],
                    'provenance': (
                        'EXPLICIT_IBN_FARIS'   if ax['attribution'] == 'IBN_FARIS_DIRECT' else
                        'QUOTED_AUTHORITY'      if ax['attribution'] == 'QUOTED_AUTHORITY' else
                        'PROJECT_NORMALIZATION'
                    ),
                } for ax in axes],
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    # ──────────────────────────────────────────────────────────────────────────
    # ٧. TRACE_AND_INTEGRITY — التتبع والسلامة
    # ──────────────────────────────────────────────────────────────────────────

    def _record_integrity(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None,
                             {'integrity': 'ABSENT', 'malformed': 0})
        results = []
        for row in rows:
            results.append({
                'entry_id':        row['id'],
                'root_letters':    row['root_letters'],
                'entry_type':      row['entry_type'],
                'axes_extracted':  row['entry_type'] != 'UNKNOWN',
                'ocr_confidence':  row['ocr_confidence'],
                'review_state':    row['review_state'],
                'partial_load':    row['entry_type'] == 'UNKNOWN',
                'malformed_lines': 0,  # يُحسَّب مستقبلاً
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows],
                         partial_load=any(r['partial_load'] for r in results))

    def _trace_lookup(self, req: dict) -> dict:
        root = req.get('root', '')
        rows = self._find_entries(root)
        if not rows:
            return _envelope(False, 'NOT_FOUND', None, [])
        con = self._db()
        cur = con.cursor()
        results = []
        for row in rows:
            cur.execute(
                "SELECT * FROM trace_events WHERE entry_id=? ORDER BY id", (row['id'],)
            )
            events = [dict(r) for r in cur.fetchall()]
            results.append({
                'entry_id':    row['id'],
                'root_letters': row['root_letters'],
                'trace_events': events,
            })
        return _envelope(True, 'OK', rows[0]['root_letters'], results,
                         source_entry_ids=[r['id'] for r in rows])

    # ──────────────────────────────────────────────────────────────────────────
    # أدوات مساعدة
    # ──────────────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """إحصاءات عامة عن قاعدة البيانات."""
        cur = self._db().cursor()
        cur.execute("SELECT COUNT(*) FROM entries")
        n_e = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM semantic_axes")
        n_a = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM poetry_evidence")
        n_p = cur.fetchone()[0]
        cur.execute("SELECT entry_type, COUNT(*) FROM entries GROUP BY entry_type")
        types = dict(cur.fetchall())
        return {
            'total_entries': n_e,
            'total_axes': n_a,
            'total_poetry_lines': n_p,
            'entry_types': types,
            'source': 'shamela_21710',
        }


def _excerpt(text: str, keyword: str, window: int = 150) -> str:
    """يستخرج مقطعاً من النص حول الكلمة المطلوبة."""
    pos = text.find(keyword)
    if pos < 0:
        return text[:window]
    start = max(0, pos - 60)
    end = min(len(text), pos + window)
    excerpt = text[start:end]
    if start > 0:
        excerpt = '…' + excerpt
    if end < len(text):
        excerpt += '…'
    return excerpt


# ── دالة الملخص الشامل ────────────────────────────────────────────────────────

def root_summary(db_path: str | Path, root: str) -> dict:
    """
    يعيد ملخصاً شاملاً لجذر واحد بثلاثة عناصر:
      - الأصول      : عدد الأصول ونوع المدخلة
      - المحاور     : نصوص الأصول الدلالية
      - الدليل      : النص الأصلي من المعجم
    """
    api = MaqayisAPI(db_path)
    r = api.query({'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': root})
    api.close()

    if not r['found']:
        return {'found': False, 'root': root, 'error': 'الجذر غير موجود في المعجم'}

    entries = []
    for e in r['results']:
        entries.append({
            'root_display'  : e['root_display'],
            'entry_type'    : e['entry_type'],
            'axes_count'    : e['axes_count'],
            'axes'          : [a['axis_text'] for a in e['semantic_axes']],
            'evidence_text' : e['body_excerpt'],
            'ocr_confidence': e['ocr_confidence'],
        })

    return {
        'found'   : True,
        'root'    : root,
        'entries' : entries,
    }


# ── اختبار سريع ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    DB = Path('/root/maqayis_v2/maqayis.db')
    api = MaqayisAPI(DB)

    print('=' * 60)
    print('إحصاءات المعجم:')
    print(json.dumps(api.stats(), ensure_ascii=False, indent=2))

    print('\n' + '=' * 60)
    print('ROOT_SEMANTIC_ORIGINS — جذر قوم:')
    r = api.query({'caller': 'HOKOM', 'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': 'قوم'})
    print(f'  found={r["found"]} status={r["query_status"]} canonical={r["canonical_root"]}')
    for entry in r['results']:
        print(f'  [{entry["root_display"]}] type={entry["entry_type"]}')
        for ax in entry['semantic_axes']:
            print(f'    → {ax["axis_text"]}')

    print('\n' + '=' * 60)
    print('CLAIM_TO_MAQAYIS_EVIDENCE — "الاعتدال" في قوم:')
    r2 = api.query({
        'caller': 'TAAQOL',
        'query_type': 'CLAIM_TO_MAQAYIS_EVIDENCE',
        'root': 'قوم',
        'claim_text': 'القيام',
    })
    print(f'  claim_status={r2["results"]["claim_status"]}')
    for ev in r2['results']['evidence']:
        print(f'  [{ev["source_type"]}] {ev["text"][:60]}')

    print('\n' + '=' * 60)
    print('CONCEPT_TO_ROOT_SEARCH — مفهوم "الصوت":')
    r3 = api.query({
        'caller': 'TAAQOL',
        'query_type': 'CONCEPT_TO_ROOT_SEARCH',
        'concept': 'صوت',
    })
    print(f'  نتائج: {len(r3["results"])}')
    for res in r3['results'][:5]:
        mt = res['match_type']
        ax = res.get('matched_axis', '')[:40] if res.get('matched_axis') else ''
        print(f'  [{res["root_display"]}] {mt} → {ax}')

    print('\n' + '=' * 60)
    print('ROOT_EXISTS — جذر كتب:')
    r4 = api.query({'caller': 'HOKOM', 'query_type': 'ROOT_EXISTS', 'root': 'كتب'})
    print(f'  {json.dumps(r4["results"], ensure_ascii=False, indent=2)}')

    api.close()


def root_claims(db_path, root: str) -> dict:
    """
    عكس CLAIM_TO_MAQAYIS_EVIDENCE —
    بدلاً من: "هل المعجم يدعم ادعائي؟"
    يجيب  : "ماذا يدّعي المعجم عن هذا الجذر؟"
    """
    api = MaqayisAPI(db_path)
    r = api.query({'query_type': 'ROOT_SEMANTIC_ORIGINS', 'root': root})
    api.close()

    if not r['found']:
        return {'found': False, 'root': root, 'claims': []}

    claims = []
    for e in r['results']:
        for ax in e['semantic_axes']:
            claims.append({
                'root_display' : e['root_display'],
                'claim_text'   : ax['axis_text'],
                'claim_rank'   : ax['axis_num'],
                'claim_type'   : 'SEMANTIC_AXIS',
                'source'       : 'IBN_FARIS_DIRECT',
                'evidence'     : e['body_excerpt'][:300],
            })
        # إذا لا محاور مستخرجة — أعد النص الخام كادعاء مفتوح
        if not e['semantic_axes'] and e['body_excerpt']:
            claims.append({
                'root_display' : e['root_display'],
                'claim_text'   : None,
                'claim_rank'   : 0,
                'claim_type'   : 'RAW_TEXT_ONLY',
                'source'       : 'IBN_FARIS_DIRECT',
                'evidence'     : e['body_excerpt'][:300],
            })

    return {
        'found'  : True,
        'root'   : root,
        'claims' : claims,
    }
