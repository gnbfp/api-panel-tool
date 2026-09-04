"""SQLite 存储层：API 密钥与 token 用量记录。
数据文件 data/panel.db 已被 .gitignore 排除，绝不进入 git 仓库。"""
import sqlite3, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB = DATA / "panel.db"


class DupError(Exception):
    pass


def _conn():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS keys(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id INTEGER NOT NULL REFERENCES keys(id),
                created_at REAL NOT NULL,
                tokens INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                url TEXT,
                model TEXT
            );
            """
        )


def add_key(name, value):
    init_db()
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO keys(name,value,active,created_at) VALUES(?,?,0,?)",
                (name, value, time.time()),
            )
    except sqlite3.IntegrityError:
        raise DupError(name)


def list_keys():
    init_db()
    with _conn() as c:
        return c.execute(
            "SELECT id,name,value,active,created_at FROM keys ORDER BY id"
        ).fetchall()


def find_key(name):
    init_db()
    with _conn() as c:
        return c.execute("SELECT * FROM keys WHERE name=?", (name,)).fetchone()


def delete_key(name):
    init_db()
    with _conn() as c:
        cur = c.execute("DELETE FROM keys WHERE name=?", (name,))
        if cur.rowcount == 0:
            raise KeyError(name)


def set_active(name):
    init_db()
    if find_key(name) is None:
        raise KeyError(name)
    with _conn() as c:
        c.execute("UPDATE keys SET active=0")
        c.execute("UPDATE keys SET active=1 WHERE name=?", (name,))


def get_active_key():
    init_db()
    with _conn() as c:
        return c.execute("SELECT * FROM keys WHERE active=1 LIMIT 1").fetchone()


def record_usage(key_id, tokens, latency_ms, url, model):
    init_db()
    with _conn() as c:
        c.execute(
            "INSERT INTO usage(key_id,created_at,tokens,latency_ms,url,model) VALUES(?,?,?,?,?,?)",
            (key_id, time.time(), int(tokens), int(latency_ms), url, model),
        )


def usage_report(key_name=None, days=None):
    init_db()
    where, args = "", []
    if key_name:
        where = "WHERE k.name=?"
        args.append(key_name)
    if days:
        where = (where + " AND" if where else "WHERE") + " u.created_at>=?"
        args.append(time.time() - days * 86400)
    sql = (
        "SELECT k.name AS key_name, COUNT(u.id) AS reqs, "
        "COALESCE(SUM(u.tokens),0) AS tokens, "
        "COALESCE(AVG(u.latency_ms),0) AS avg_lat "
        "FROM usage u JOIN keys k ON k.id=u.key_id "
        + where + " GROUP BY k.name ORDER BY tokens DESC"
    )
    with _conn() as c:
        rows = c.execute(sql, args).fetchall()
        tot = c.execute(
            "SELECT COUNT(*) reqs, COALESCE(SUM(tokens),0) tokens FROM usage u "
            "JOIN keys k ON k.id=u.key_id " + where,
            args,
        ).fetchone()
    return rows, tot
