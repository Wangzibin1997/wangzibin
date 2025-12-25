import json
import uuid

from agent.llm import call_llm_json


def plan_turn(*, user_message: str, context: dict | None = None) -> dict:
    """Return structured plan + proposed tool calls.

    Output schema (best-effort):
    {
      "assistant_message": str,
      "plan": [{"step_id": str, "title": str, "status": "planned"|"done"|"blocked"}],
      "tool_calls": [{"call_id": str, "tool": str, "args": dict, "reason": str, "risk": "low"|"medium"|"high"}],
      "questions": [str]
    }
    """

    system = (
        "你是一个交易Agent的大脑(Planner)。你必须只输出 JSON，不要输出任何多余文本。\n"
        "你的目标：基于用户任务与上下文，输出：解释(assistant_message)、计划(plan)、建议的工具调用(tool_calls)、需要澄清的问题(questions)。\n"
        "规则：\n"
        "- tool_calls 仅能使用工具白名单里的名字(例如: ccxt.fetch_ohlcv, ccxt.fetch_balance, ccxt.fetch_positions, ccxt.fetch_open_orders, ccxt.fetch_ticker, freqtrade.get_status, freqtrade.get_balance, freqtrade.get_trades)。\n"
        "- 所有 tool_calls 都是‘建议’，不能假设已经执行。\n"
        "- risk 字段必须是 low/medium/high。\n"
        "- 如果不需要工具调用，tool_calls 为空数组。\n"
        "输出 JSON schema:\n"
        "{\n"
        '  "assistant_message": "...",\n'
        '  "plan": [{"step_id":"1","title":"...","status":"planned"}],\n'
        '  "tool_calls": [{"call_id":"tc_...","tool":"ccxt.fetch_ohlcv","args":{},"reason":"...","risk":"low"}],\n'
        '  "questions": ["..."]\n'
        "}\n"
    )

    payload = {"user_message": user_message, "context": context or {}}
    resp = call_llm_json(system=system, user=json.dumps(payload, ensure_ascii=False)) or {}

    # Best-effort normalization
    out = {
        "assistant_message": str(resp.get("assistant_message") or ""),
        "plan": resp.get("plan") if isinstance(resp.get("plan"), list) else [],
        "tool_calls": resp.get("tool_calls") if isinstance(resp.get("tool_calls"), list) else [],
        "questions": resp.get("questions") if isinstance(resp.get("questions"), list) else [],
    }

    for tc in out["tool_calls"]:
        if isinstance(tc, dict) and not tc.get("call_id"):
            tc["call_id"] = f"tc_{uuid.uuid4().hex[:8]}"
        if isinstance(tc, dict) and not isinstance(tc.get("args"), dict):
            tc["args"] = {}
        if isinstance(tc, dict) and tc.get("risk") not in {"low", "medium", "high"}:
            tc["risk"] = "low"

    return out
