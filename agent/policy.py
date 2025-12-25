import json
import os
from dataclasses import dataclass


@dataclass
class PolicyDecision:
    allow: bool
    reason: str
    confidence: float | None = None
    max_position_ratio: float | None = None


def llm_policy_enabled() -> bool:
    return os.getenv("AGENT_LLM_ENABLED", "0") in ("1", "true", "TRUE")


def decide_entry(
    *,
    pair: str,
    side: str,
    timeframe: str,
    indicators: dict,
    recent_news: list[str] | None = None,
    memory_hits: list[dict] | None = None,
) -> PolicyDecision:
    """LLM-based veto / sizing decision. If LLM disabled/unavailable -> allow."""

    if not llm_policy_enabled():
        return PolicyDecision(allow=True, reason="LLM disabled")

    from agent.llm import call_llm_json

    system = (
        "You are a risk-focused crypto trading gatekeeper. "
        "You must output ONLY valid JSON with keys: allow(boolean), reason(string), confidence(number 0-1), max_position_ratio(number 0-1)."
    )

    user_obj = {
        "pair": pair,
        "side": side,
        "timeframe": timeframe,
        "indicators": indicators,
        "news": recent_news or [],
        "memory": memory_hits or [],
        "constraints": {
            "no_direct_instructions": True,
            "role": "veto_and_position_sizing_only",
        },
    }

    resp = call_llm_json(system=system, user=json.dumps(user_obj, ensure_ascii=False))
    if not resp:
        return PolicyDecision(allow=True, reason="LLM unavailable")

    try:
        allow = bool(resp.get("allow"))
        reason = str(resp.get("reason", ""))[:400]
        conf = resp.get("confidence")
        mpr = resp.get("max_position_ratio")
        conf_f = float(conf) if conf is not None else None
        mpr_f = float(mpr) if mpr is not None else None
        if mpr_f is not None:
            mpr_f = max(0.0, min(1.0, mpr_f))
        if conf_f is not None:
            conf_f = max(0.0, min(1.0, conf_f))
        return PolicyDecision(allow=allow, reason=reason, confidence=conf_f, max_position_ratio=mpr_f)
    except Exception:
        return PolicyDecision(allow=True, reason="LLM invalid JSON schema")
