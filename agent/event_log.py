import json
import time
import uuid
from pathlib import Path

from sqlite_utils import Database

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agent" / "events.sqlite"


def new_session_id() -> str:
    return uuid.uuid4().hex


def append_event(
    session_id: str,
    event_type: str,
    data: dict | None = None,
    *,
    parent_id: int | None = None,
    ts: float | None = None,
) -> int:
    db = Database(DB_PATH)
    db["events"].create(
        {
            "id": int,
            "session_id": str,
            "ts": float,
            "type": str,
            "parent_id": int,
            "data_json": str,
        },
        pk="id",
        if_not_exists=True,
    )

    row = {
        "id": None,
        "session_id": session_id,
        "ts": float(time.time() if ts is None else ts),
        "type": event_type,
        "parent_id": parent_id,
        "data_json": json.dumps(data or {}, ensure_ascii=False),
    }
    db["events"].insert(row, alter=True)
    # sqlite-utils insert() may not return the inserted row reliably across versions.
    return int(db.conn.execute("select last_insert_rowid() ").fetchone()[0])


def list_sessions(*, limit: int = 50) -> list[dict]:
    db = Database(DB_PATH)
    if "events" not in db.table_names():
        return []
    rows = list(
        db.query(
            "select session_id, min(ts) as started_ts, max(ts) as last_ts, count(*) as n "
            "from events group by session_id order by last_ts desc limit ?",
            [limit],
        )
    )
    return [dict(r) for r in rows]


def load_events(session_id: str, *, limit: int = 2000) -> list[dict]:
    db = Database(DB_PATH)
    if "events" not in db.table_names():
        return []
    rows = list(
        db.query(
            "select id, session_id, ts, type, parent_id, data_json from events "
            "where session_id = ? order by id asc limit ?",
            [session_id, limit],
        )
    )
    out: list[dict] = []
    for r in rows:
        try:
            out.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "ts": r["ts"],
                    "type": r["type"],
                    "parent_id": r["parent_id"],
                    "data": json.loads(r["data_json"] or "{}"),
                }
            )
        except Exception:
            continue
    return out


def store_artifact(
    session_id: str,
    kind: str,
    content: dict,
    *,
    metadata: dict | None = None,
    ts: float | None = None,
) -> str:
    db = Database(DB_PATH)
    db["artifacts"].create(
        {
            "id": str,
            "session_id": str,
            "ts": float,
            "kind": str,
            "metadata_json": str,
            "content_json": str,
        },
        pk="id",
        if_not_exists=True,
    )

    artifact_id = uuid.uuid4().hex
    db["artifacts"].insert(
        {
            "id": artifact_id,
            "session_id": session_id,
            "ts": float(time.time() if ts is None else ts),
            "kind": kind,
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
            "content_json": json.dumps(content, ensure_ascii=False),
        },
        pk="id",
        alter=True,
    )
    return artifact_id


def load_artifact(artifact_id: str) -> dict | None:
    db = Database(DB_PATH)
    if "artifacts" not in db.table_names():
        return None
    try:
        r = db["artifacts"].get(artifact_id)
    except Exception:
        return None
    try:
        return {
            "id": r["id"],
            "session_id": r["session_id"],
            "ts": r["ts"],
            "kind": r["kind"],
            "metadata": json.loads(r.get("metadata_json") or "{}"),
            "content": json.loads(r.get("content_json") or "{}"),
        }
    except Exception:
        return None
