import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key_env: str
    api_url: str


def load_llm_config() -> LLMConfig:
    # First, try UI config in app/params.json
    params_path = Path(__file__).resolve().parents[2] / "app" / "params.json"
    try:
        with open(params_path, encoding="utf-8") as f:
            params = json.load(f)
            agent = params.get("agent", {})
            api_url = agent.get("llm_api_url", os.getenv("AGENT_LLM_API_URL", "https://api.anthropic.com"))
    except Exception:
        # Fallback to environment variables
        api_url = os.getenv("AGENT_LLM_API_URL", "https://api.anthropic.com")

    # Remaining config is still env-driven
    provider = os.getenv("AGENT_LLM_PROVIDER", "anthropic")
    model = os.getenv("AGENT_LLM_MODEL", "claude-3-5-sonnet-latest")
    api_key_env = os.getenv("AGENT_LLM_API_KEY_ENV", "ANTHROPIC_API_KEY")
    return LLMConfig(provider=provider, model=model, api_key_env=api_key_env, api_url=api_url)


def _get_api_key(cfg: LLMConfig) -> str | None:
    # First try params.json for key
    params_path = Path(__file__).resolve().parents[2] / "app" / "params.json"
    try:
        with open(params_path, encoding="utf-8") as f:
            params = json.load(f)
            agent = params.get("agent", {})
            if "llm_api_key" in agent:
                return agent.get("llm_api_key")
    except Exception:
        pass
    # Fallback to environment
    return os.getenv(cfg.api_key_env)


def llm_enabled() -> bool:
    return os.getenv("AGENT_LLM_ENABLED", "0") in ("1", "true", "TRUE")


def _get_api_key(cfg: LLMConfig) -> str | None:
    return os.getenv(cfg.api_key_env)


def call_llm_json(system: str, user: str) -> dict | None:
    """Best-effort JSON call. Returns dict or None if disabled/unconfigured."""
    cfg = load_llm_config()
    if not llm_enabled():
        return None

    api_key = _get_api_key(cfg)
    if not api_key:
        return None

    if cfg.provider != "anthropic":
        # Only anthropic supported in this project for now.
        return None

    from anthropic import Anthropic

    # Initialize client with potential custom URL
    if hasattr(Anthropic, "__init__") and hasattr(Anthropic.__init__, "parameters"):
        # Newer Anthropic SDK allows base_url parameter
        if "base_url" in Anthropic.__init__.__parameters__:
            client = Anthropic(api_key=api_key, base_url=cfg.api_url)
        else:
            client = Anthropic(api_key=api_key)
    else:
        # Fallback for older SDKs
        client = Anthropic(api_key=api_key)

    msg = client.messages.create(
        model=cfg.model,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join([b.text for b in msg.content if getattr(b, "type", None) == "text"])

    # Try parse JSON object from response
    import json

    try:
        return json.loads(text)
    except Exception:
        # attempt to extract first JSON block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None
