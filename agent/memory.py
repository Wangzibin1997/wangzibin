import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from sqlite_utils import Database

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agent" / "memory.sqlite"


@dataclass
class MemoryItem:
    key: str
    ts: float
    kind: str
    pair: str | None
    content: dict


def _stable_key(kind: str, pair: str | None, content: dict) -> str:
    raw = json.dumps({"kind": kind, "pair": pair, "content": content}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_memory(kind: str, content: dict, pair: str | None = None) -> str:
    db = Database(DB_PATH)
    db["memory"].create(
        {
            "key": str,
            "ts": float,
            "kind": str,
            "pair": str,
            "content_json": str,
        },
        pk="key",
        if_not_exists=True,
    )

    key = _stable_key(kind, pair, content)
    db["memory"].upsert(
        {
            "key": key,
            "ts": time.time(),
            "kind": kind,
            "pair": pair or "",
            "content_json": json.dumps(content, ensure_ascii=False),
        },
        pk="key",
    )
    return key


def search_memory(query: str, *, limit: int = 5, pair: str | None = None) -> list[dict]:
    # Lightweight retrieval: substring match over stored JSON.
    # (We can replace with embeddings later.)
    db = Database(DB_PATH)
    if "memory" not in db.table_names():
        return []

    q = f"%{query}%"
    if pair:
        rows = list(
            db.query(
                "select ts, kind, pair, content_json from memory where content_json like ? and pair = ? order by ts desc limit ?",
                [q, pair, limit],
            )
        )
    else:
        rows = list(
            db.query(
                "select ts, kind, pair, content_json from memory where content_json like ? order by ts desc limit ?",
                [q, limit],
            )
        )

    out: list[dict] = []
    for r in rows:
        try:
            out.append(
                {
                    "ts": r["ts"],
                    "kind": r["kind"],
                    "pair": r["pair"],
                    "content": json.loads(r["content_json"]),
                }
            )
        except Exception:
            continue
    return out
