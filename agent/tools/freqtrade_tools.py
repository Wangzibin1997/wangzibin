from agent.freqtrade_api import get_json


def get_status(*, args: dict, context: dict) -> dict:
    auth = (context or {}).get("freqtrade_auth")
    if auth is None:
        raise RuntimeError("Missing freqtrade_auth in context")
    return get_json(auth, "/api/v1/status")


def get_balance(*, args: dict, context: dict) -> dict:
    auth = (context or {}).get("freqtrade_auth")
    if auth is None:
        raise RuntimeError("Missing freqtrade_auth in context")
    return get_json(auth, "/api/v1/balance")


def get_trades(*, args: dict, context: dict) -> dict:
    auth = (context or {}).get("freqtrade_auth")
    if auth is None:
        raise RuntimeError("Missing freqtrade_auth in context")
    return get_json(auth, "/api/v1/trades")
