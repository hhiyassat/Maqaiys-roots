"""
بناء قاعدة بيانات SQLite لمعجم المقاييس الإلكتروني
الجداول: entries, semantic_axes, derivatives_mentioned, poetry_evidence, source_passages
"""

import json, sqlite3, re
from pathlib import Path

SRC  = Path('/root/maqayis_v2/shamela_maqayis_enriched.jsonl')
DB   = Path('/root/maqayis_v2/maqayis.db')

# ── بناء قاعدة البيانات ───────────────────────────────────────────────────────

def build(src: Path, db_path: Path):
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # ── الجداول ──────────────────────────────────────────────────────────────

    cur.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    -- ١. المدخلات الأساسية
    CREATE TABLE entries (
        id              INTEGER PRIMARY KEY,
        entry_num       INTEGER NOT NULL,
        source          TEXT,
        root_letters    TEXT NOT NULL,   -- الجذر الثنائي المعياري (أ ج)
        root_display    TEXT NOT NULL,   -- كما ظهر في المعجم (أجّ / حجز)
        chapter_header  TEXT,
        is_lexical_entry INTEGER NOT NULL DEFAULT 1,
        body_text       TEXT NOT NULL,
        page_refs       TEXT,            -- JSON array
        raw_page_nums   TEXT,            -- JSON array
        entry_type      TEXT,            -- SINGLE_ORIGIN / MULTI_ORIGIN / SINGLE_WORD / ...
        axes_count      INTEGER,
        quoted_authorities TEXT,         -- JSON array
        ocr_confidence  REAL,
        review_state    TEXT DEFAULT 'PENDING',
        claim_status    TEXT DEFAULT 'UNVERIFIED'
    );

    -- ٢. الأصول المعنوية
    CREATE TABLE semantic_axes (
        id          INTEGER PRIMARY KEY,
        entry_id    INTEGER NOT NULL REFERENCES entries(id),
        axis_num    INTEGER NOT NULL,    -- 1، 2، 3، ...
        axis_text   TEXT NOT NULL,       -- نص الأصل المعنوي (مُطبَّع بلا تشكيل)
        axis_text_orig TEXT,             -- النص الأصلي بالتشكيل إن أمكن
        attribution TEXT DEFAULT 'IBN_FARIS_DIRECT'
                        -- IBN_FARIS_DIRECT | QUOTED_AUTHORITY | PROJECT_INFERRED
    );

    -- ٣. الشواهد الشعرية
    CREATE TABLE poetry_evidence (
        id          INTEGER PRIMARY KEY,
        entry_id    INTEGER NOT NULL REFERENCES entries(id),
        line_num    INTEGER NOT NULL,
        line_text   TEXT NOT NULL
    );

    -- ٤. الحواشي والمقاطع المصدرية
    CREATE TABLE source_passages (
        id          INTEGER PRIMARY KEY,
        entry_id    INTEGER NOT NULL REFERENCES entries(id),
        passage_type TEXT,               -- FOOTNOTE | BODY_SEGMENT
        passage_num INTEGER,
        content     TEXT NOT NULL
    );

    -- ٥. سجل التتبع (trace)
    CREATE TABLE trace_events (
        id          INTEGER PRIMARY KEY,
        entry_id    INTEGER NOT NULL REFERENCES entries(id),
        event_type  TEXT NOT NULL,       -- PARSED | ENRICHED | FLAGGED
        detail      TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    -- فهارس للبحث السريع
    CREATE INDEX idx_entries_root_letters  ON entries(root_letters);
    CREATE INDEX idx_entries_root_display  ON entries(root_display);
    CREATE INDEX idx_entries_entry_type    ON entries(entry_type);
    CREATE INDEX idx_entries_review_state  ON entries(review_state);
    CREATE INDEX idx_axes_entry_id         ON semantic_axes(entry_id);
    CREATE INDEX idx_axes_text             ON semantic_axes(axis_text);
    CREATE INDEX idx_poetry_entry_id       ON poetry_evidence(entry_id);
    CREATE INDEX idx_passages_entry_id     ON source_passages(entry_id);

    -- فهرس بحث نصي كامل في الأصول المعنوية
    CREATE VIRTUAL TABLE axes_fts USING fts5(
        axis_text,
        content='semantic_axes',
        content_rowid='id'
    );
    """)

    # ── تحميل البيانات ───────────────────────────────────────────────────────

    entries = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]

    entry_rows, axes_rows, poetry_rows, passage_rows, trace_rows = [], [], [], [], []

    for e in entries:
        eid = e['entry_num']

        entry_rows.append((
            eid,
            e['entry_num'],
            e.get('source', ''),
            e.get('root_letters', ''),
            e.get('root_display', ''),
            e.get('chapter_header'),
            1 if e.get('is_lexical_entry') else 0,
            e.get('body_text', ''),
            json.dumps(e.get('page_refs', []), ensure_ascii=False),
            json.dumps(e.get('raw_page_nums', []), ensure_ascii=False),
            e.get('entry_type', 'UNKNOWN'),
            e.get('axes_count'),
            json.dumps(e.get('quoted_authorities', []), ensure_ascii=False),
            e.get('ocr_confidence', 1.0),
            e.get('review_state', 'PENDING'),
            e.get('claim_status', 'UNVERIFIED'),
        ))

        for i, ax in enumerate(e.get('semantic_axes', []), 1):
            axes_rows.append((
                None, eid, i,
                ax.get('text', ''),
                ax.get('text', ''),   # نسخة أصلية (مطابقة هنا — تُحسَّن لاحقاً)
                ax.get('attribution', 'IBN_FARIS_DIRECT'),
            ))

        for j, line in enumerate(e.get('poetry_lines', []), 1):
            poetry_rows.append((None, eid, j, line))

        for k, fn in enumerate(e.get('footnote_lines', []), 1):
            passage_rows.append((eid * 10000 + k, eid, 'FOOTNOTE', k, fn))

        event = 'ENRICHED' if e.get('entry_type') != 'UNKNOWN' else 'FLAGGED'
        detail = f'entry_type={e.get("entry_type")} axes={e.get("axes_count")}'
        trace_rows.append((eid, event, detail))

    cur.executemany(
        'INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        entry_rows,
    )
    cur.executemany(
        'INSERT INTO semantic_axes VALUES (?,?,?,?,?,?)',
        axes_rows,
    )
    cur.executemany(
        'INSERT INTO poetry_evidence VALUES (?,?,?,?)',
        poetry_rows,
    )
    cur.executemany(
        'INSERT INTO source_passages (id,entry_id,passage_type,passage_num,content) VALUES (?,?,?,?,?)',
        passage_rows,
    )
    cur.executemany(
        'INSERT INTO trace_events (entry_id,event_type,detail) VALUES (?,?,?)',
        trace_rows,
    )

    # ── تحديث FTS ────────────────────────────────────────────────────────────
    cur.execute("INSERT INTO axes_fts(axes_fts) VALUES('rebuild')")

    con.commit()
    con.close()

    return len(entries), len(axes_rows), len(poetry_rows), len(passage_rows)


if __name__ == '__main__':
    n_e, n_a, n_p, n_s = build(SRC, DB)
    print(f'✓ entries        : {n_e}')
    print(f'✓ semantic_axes  : {n_a}')
    print(f'✓ poetry_evidence: {n_p}')
    print(f'✓ source_passages: {n_s}')
    print(f'✓ db size        : {DB.stat().st_size // 1024} KB')

    # تحقق سريع
    con = sqlite3.connect(DB)
    cur = con.cursor()

    print('\nعينة — جذر قوم:')
    cur.execute(
        "SELECT root_display, entry_type, axes_count FROM entries "
        "WHERE root_letters LIKE '%قو%' OR root_display LIKE 'قوم%' LIMIT 5"
    )
    for r in cur.fetchall():
        print(f'  {r}')

    print('\nأكثر 5 أصول شيوعاً في semantic_axes:')
    cur.execute(
        "SELECT axis_text, COUNT(*) c FROM semantic_axes GROUP BY axis_text ORDER BY c DESC LIMIT 5"
    )
    for r in cur.fetchall():
        print(f'  {r}')

    print('\nإحصاء entry_type:')
    cur.execute("SELECT entry_type, COUNT(*) FROM entries GROUP BY entry_type ORDER BY 2 DESC")
    for r in cur.fetchall():
        print(f'  {r}')
    con.close()
