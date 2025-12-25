import json
import time

from agent import charting
from agent.event_log import append_event, load_artifact, load_events, new_session_id, store_artifact
from agent.planner import plan_turn
from agent.tools.default_registry import build_default_registry


def ensure_session(session_id: str | None) -> str:
    if session_id:
        return session_id
    sid = new_session_id()
    append_event(sid, "session_started", {})
    return sid


def user_message(session_id: str, text: str, *, context: dict | None = None) -> dict:
    append_event(session_id, "user_message", {"text": text, "context": context or {}})

    planned = plan_turn(user_message=text, context=context or {})

    append_event(session_id, "assistant_message", {"text": planned.get("assistant_message", "")})
    append_event(session_id, "plan_created", {"plan": planned.get("plan", [])})

    tool_calls = planned.get("tool_calls") or []
    for tc in tool_calls:
        if isinstance(tc, dict):
            append_event(session_id, "tool_call_proposed", tc)

    if planned.get("questions"):
        append_event(session_id, "questions", {"questions": planned.get("questions")})

    return planned


def list_pending_tool_calls(session_id: str) -> list[dict]:
    events = load_events(session_id)
    proposed: dict[str, dict] = {}
    approved: set[str] = set()
    finished: set[str] = set()

    for e in events:
        t = e.get("type")
        data = e.get("data") or {}
        if t == "tool_call_proposed":
            call_id = data.get("call_id")
            if call_id:
                proposed[call_id] = data
        elif t == "tool_call_approved":
            call_id = data.get("call_id")
            if call_id:
                approved.add(call_id)
        elif t == "tool_call_finished":
            call_id = data.get("call_id")
            if call_id:
                finished.add(call_id)

    pending = []
    for call_id, tc in proposed.items():
        if call_id in approved or call_id in finished:
            continue
        pending.append(tc)
    return pending


def approve_tool_call(session_id: str, call_id: str) -> None:
    append_event(session_id, "tool_call_approved", {"call_id": call_id})


def execute_approved_tool_calls(session_id: str, *, context: dict) -> list[dict]:
    """Exec all approved-but-not-finished tool calls. Returns list of ToolResult dicts."""
    events = load_events(session_id)
    proposed: dict[str, dict] = {}
    approved: set[str] = set()
    finished: set[str] = set()

    for e in events:
        t = e.get("type")
        data = e.get("data") or {}
        if t == "tool_call_proposed":
            call_id = data.get("call_id")
            if call_id:
                proposed[call_id] = data
        elif t == "tool_call_approved":
            call_id = data.get("call_id")
            if call_id:
                approved.add(call_id)
        elif t == "tool_call_finished":
            call_id = data.get("call_id")
            if call_id:
                finished.add(call_id)

    reg = build_default_registry()
    results: list[dict] = []

    for call_id in sorted(approved):
        if call_id in finished:
            continue
        tc = proposed.get(call_id)
        if not tc:
            continue

        tool = tc.get("tool")
        args = tc.get("args") or {}
        if not tool:
            continue

        spec = reg.spec(tool)
        append_event(session_id, "tool_call_started", {"call_id": call_id, "tool": tool, "args": args})

        started = time.time()
        try:
            out = reg.execute(tool, args, context=context)
            res = {
                "call_id": call_id,
                "tool": tool,
                "ok": True,
                "result": out,
                "started_ts": started,
                "ended_ts": time.time(),
            }

            # If this is candles, generate chart artifact.
            if tool == "ccxt.fetch_ohlcv" and isinstance(out, list):
                df = charting.ohlcv_to_df(out)
                inds = charting.simple_indicators(df)
                fig_json = charting.build_plotly_candles(
                    df,
                    title=f"{args.get('symbol','')} {args.get('timeframe','')}"
                )
                artifact_id = store_artifact(
                    session_id,
                    kind="chart",
                    content={"plotly": fig_json, "indicators": inds, "symbol": args.get("symbol"), "timeframe": args.get("timeframe")},
                    metadata={"tool_call_id": call_id},
                )
                append_event(session_id, "chart_created", {"artifact_id": artifact_id, "call_id": call_id})
                res["chart_artifact_id"] = artifact_id

        except Exception as e:
            res = {
                "call_id": call_id,
                "tool": tool,
                "ok": False,
                "error": str(e),
                "started_ts": started,
                "ended_ts": time.time(),
            }

        append_event(session_id, "tool_call_finished", res)
        results.append(res)

    return results


def get_latest_chart(session_id: str) -> dict | None:
    events = load_events(session_id)
    artifact_id = None
    for e in reversed(events):
        if e.get("type") == "chart_created":
            artifact_id = (e.get("data") or {}).get("artifact_id")
            if artifact_id:
                break
    if not artifact_id:
        return None
    return load_artifact(artifact_id)
