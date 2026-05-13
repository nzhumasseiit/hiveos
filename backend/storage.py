import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from config import get_settings


def _db_path() -> str:
    path = get_settings().db_path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(os.path.dirname(__file__), path))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hives (
              id TEXT PRIMARY KEY,
              owner_username TEXT NOT NULL DEFAULT 'admin',
              client_id TEXT NOT NULL DEFAULT 'default',
              name TEXT NOT NULL,
              location TEXT NOT NULL DEFAULT '',
              loc TEXT NOT NULL DEFAULT '',
              topic TEXT NOT NULL,
              node TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'unknown',
              last_seen TEXT,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            """
        )
        _ensure_column(conn, "hives", "owner_username", "TEXT NOT NULL DEFAULT 'admin'")
        _ensure_column(conn, "hives", "client_id", "TEXT NOT NULL DEFAULT 'default'")
        _ensure_column(conn, "hives", "location", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "hives", "status", "TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, "hives", "last_seen", "TEXT")
        conn.execute(
            """
            UPDATE hives
            SET location = CASE WHEN location = '' THEN loc ELSE location END
            WHERE location = '' OR location IS NULL;
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
              id TEXT PRIMARY KEY,
              hive_id TEXT NOT NULL,
              device_id TEXT NOT NULL,
              sensor_type TEXT NOT NULL,
              protocol TEXT NOT NULL DEFAULT 'unknown',
              status TEXT NOT NULL DEFAULT 'unknown',
              last_seen TEXT,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              FOREIGN KEY(hive_id) REFERENCES hives(id) ON DELETE CASCADE,
              UNIQUE(hive_id, device_id, sensor_type)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hives_owner ON hives(owner_username);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hives_client ON hives(client_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hives_node ON hives(node);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_hive ON devices(hive_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_device ON devices(device_id);")
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")


def list_hives(owner_username: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        params: Tuple[Any, ...] = ()
        where = ""
        if owner_username:
            where = "WHERE owner_username = ?"
            params = (owner_username,)
        rows = conn.execute(
            f"""
            SELECT id, owner_username, client_id, name, location, loc, topic, node, status, last_seen
            FROM hives
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
        hives = []
        for row in rows:
            item = dict(row)
            item["loc"] = item["location"] or item["loc"]
            hives.append(item)
        return hives
    finally:
        conn.close()


def create_hive(
    name: str,
    location: str,
    topic: str,
    node: str,
    owner_username: str,
    client_id: str = "default",
) -> Dict[str, Any]:
    hive_id = uuid.uuid4().hex
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO hives (id, owner_username, client_id, name, location, loc, topic, node)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (hive_id, owner_username, client_id, name, location, location, topic, node),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO devices (id, hive_id, device_id, sensor_type, protocol)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, hive_id, node, "environment", "mixed"),
        )
        conn.commit()
        return {
            "id": hive_id,
            "owner_username": owner_username,
            "client_id": client_id,
            "name": name,
            "location": location,
            "loc": location,
            "topic": topic,
            "node": node,
            "status": "unknown",
            "last_seen": None,
        }
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


def hive_exists(hive_id: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT 1 FROM hives WHERE id = ?", (hive_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def touch_device(hive_id: str, device_id: str, sensor_type: str, protocol: str = "unknown") -> None:
    conn = _connect()
    try:
        now_sql = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
        conn.execute(
            f"""
            INSERT INTO devices (id, hive_id, device_id, sensor_type, protocol, status, last_seen)
            VALUES (?, ?, ?, ?, ?, 'online', {now_sql})
            ON CONFLICT(hive_id, device_id, sensor_type)
            DO UPDATE SET status = 'online', last_seen = {now_sql}, protocol = excluded.protocol
            """,
            (uuid.uuid4().hex, hive_id, device_id, sensor_type, protocol),
        )
        conn.execute(
            f"UPDATE hives SET status = 'online', last_seen = {now_sql} WHERE id = ?",
            (hive_id,),
        )
        conn.commit()
    finally:
        conn.close()


def list_devices(hive_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        params: Tuple[Any, ...] = ()
        where = ""
        if hive_id:
            where = "WHERE hive_id = ?"
            params = (hive_id,)
        rows = conn.execute(
            f"""
            SELECT id, hive_id, device_id, sensor_type, protocol, status, last_seen
            FROM devices
            {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
