import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS_PATH = ROOT / "app" / "params.json"


def load_runtime_news_summaries() -> list[str]:
    try:
        params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rt = params.get("runtime") or {}
    summaries = rt.get("news_summaries") or []
    if isinstance(summaries, list):
        return [str(s) for s in summaries][:20]
    return []
