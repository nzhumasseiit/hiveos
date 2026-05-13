import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple


def _db_path() -> str:
    return os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "hiveos.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hives (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              loc TEXT NOT NULL,
              topic TEXT NOT NULL,
              node TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hives_node ON hives(node);")
        conn.commit()
    finally:
        conn.close()


def list_hives() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, loc, topic, node FROM hives ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_hive(name: str, loc: str, topic: str, node: str) -> Dict[str, Any]:
    hive_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO hives (id, name, loc, topic, node) VALUES (?, ?, ?, ?, ?)",
            (hive_id, name, loc, topic, node),
        )
        conn.commit()
        return {"id": hive_id, "name": name, "loc": loc, "topic": topic, "node": node}
    finally:
        conn.close()


def delete_hive(hive_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM hives WHERE id = ?", (hive_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

