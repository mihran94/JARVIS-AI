"""Local history. Connections are short lived and safe across worker threads."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with self.connect() as source:
                version = source.execute('PRAGMA user_version').fetchone()[0]
                if version > 3:
                    raise RuntimeError('Database belongs to a newer JARVIS version.')
                if version < 3 and source.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'").fetchone():
                    prefix = 'history-pre-v02-' if version < 2 else 'history-pre-v03-'
                    backup_path = self.path.with_name(prefix + uuid.uuid4().hex + '.sqlite3')
                    backup = sqlite3.connect(backup_path)
                    try:
                        source.backup(backup)
                    finally:
                        backup.close()
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks(
                    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
                    kind TEXT, status TEXT, detail TEXT);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY, session TEXT, role TEXT, content TEXT);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
                    app TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS usage(
                    task_id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
                    provider TEXT, model TEXT, status TEXT, duration_ms INTEGER,
                    prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER);
                CREATE TABLE IF NOT EXISTS workflows(
                    id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL, summary TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS workflow_steps(
                    workflow_id TEXT NOT NULL REFERENCES workflows(id),
                    position INTEGER NOT NULL, app TEXT NOT NULL, status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(workflow_id, position));
                PRAGMA user_version=3;
            ''')
            db.execute("UPDATE tasks SET status='interrupted' WHERE status IN ('running','pending')")
            db.execute("UPDATE jobs SET status='interrupted', detail='Interrupted; not replayed automatically' "
                       "WHERE status IN ('reviewing','running')")
            db.execute("UPDATE workflows SET status='interrupted', "
                       "detail='Interrupted; workflow will not be replayed' "
                       "WHERE status IN ('reviewing','running')")
            db.execute("UPDATE workflow_steps SET status='interrupted' "
                       "WHERE status IN ('reviewing','running')")
            db.execute("UPDATE workflow_steps SET status='cancelled' "
                       "WHERE status='pending' AND workflow_id IN "
                       "(SELECT id FROM workflows WHERE status='interrupted')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def set(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', (key, json.dumps(value)))

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def task(self, kind, detail):
        ident = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO tasks(id,kind,status,detail) VALUES (?,?,?,?)',
                       (ident, kind, 'pending', detail))
        return ident

    def finish(self, ident, status, detail=None):
        with self.connect() as db:
            if detail is None:
                db.execute('UPDATE tasks SET status=? WHERE id=?', (status, ident))
            else:
                db.execute('UPDATE tasks SET status=?,detail=? WHERE id=?', (status, detail, ident))

    def tasks(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM tasks ORDER BY rowid DESC LIMIT 200')]

    def message(self, session, role, content):
        with self.connect() as db:
            db.execute('INSERT INTO messages(session,role,content) VALUES (?,?,?)',
                       (session, role, content))

    def messages(self, session):
        with self.connect() as db:
            return [dict(x) for x in db.execute(
                'SELECT role,content FROM messages WHERE session=? ORDER BY id', (session,))]

    def clear_messages(self, session):
        with self.connect() as db:
            db.execute('DELETE FROM messages WHERE session=?', (session,))

    def sessions(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''
                SELECT session, MIN(id) AS first_id, MAX(id) AS last_id,
                       substr((SELECT content FROM messages first_message
                               WHERE first_message.session=history.session AND role='user'
                               ORDER BY id LIMIT 1),1,60) AS title,
                       COUNT(*) AS count
                FROM messages history GROUP BY session ORDER BY last_id DESC LIMIT 100
            ''')]

    def record_usage(self, task_id, provider, model, status, metrics):
        with self.connect() as db:
            db.execute('''INSERT OR REPLACE INTO usage(
                task_id,provider,model,status,duration_ms,prompt_tokens,completion_tokens,total_tokens)
                VALUES (?,?,?,?,?,?,?,?)''',
                (task_id, provider, model, status, metrics.get('duration_ms', 0),
                 metrics.get('prompt_tokens'), metrics.get('completion_tokens'), metrics.get('total_tokens')))

    def usage_rows(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM usage ORDER BY rowid DESC LIMIT 200')]
