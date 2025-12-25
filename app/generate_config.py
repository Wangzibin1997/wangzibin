import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_config(params_path: Path, base_config_path: Path, out_config_path: Path) -> None:
    params = _load_json(params_path)
    base = _load_json(base_config_path)

    trading = params.get("trading", {})
    risk = params.get("risk", {})

    # Trading basics
    base["timeframe"] = trading.get("timeframe", base.get("timeframe", "1h"))
    # Make sure bot starts trading after launch (instead of staying in STOPPED state).
    base["initial_state"] = "running"
    base["max_open_trades"] = trading.get("max_open_trades", base.get("max_open_trades", 3))
    base["stake_currency"] = trading.get("stake_currency", base.get("stake_currency", "USDT"))
    base["tradable_balance_ratio"] = trading.get(
        "tradable_balance_ratio", base.get("tradable_balance_ratio", 0.95)
    )

    base["trading_mode"] = trading.get("trading_mode", base.get("trading_mode", "futures"))
    base["margin_mode"] = trading.get("margin_mode", base.get("margin_mode", "isolated"))
    base["leverage"] = trading.get("leverage", base.get("leverage", 10))

    pairs = trading.get("pairs")
    if pairs:
        base.setdefault("exchange", {})["pair_whitelist"] = pairs
        base["pairlists"] = [
            {
                "method": "StaticPairList",
                "pairs": pairs,
            }
        ]

    # Risk settings
    manual_unlock_only = bool(risk.get("manual_unlock_only", True))
    # Protections (config-driven)
    max_dd = float(risk.get("max_drawdown", 0.25))
    daily_loss = float(risk.get("daily_loss", 0.05))
    enabled = bool(risk.get("enabled", True))

    long_minutes = 60 * 24 * 300  # 300 days
    stop_duration = long_minutes if manual_unlock_only else 60 * 24

    if enabled:
        base["protections"] = [
            {
                "method": "MaxDrawdown",
                "lookback_period": 60 * 24 * 30,
                "trade_limit": 1,
                "stop_duration": stop_duration,
                "max_allowed_drawdown": max_dd,
            },
            {
                "method": "DailyEquityLossProtection",
                "lookback_period": 60,
                "stop_duration": stop_duration,
                "max_daily_loss": daily_loss,
            },
            {"method": "CooldownPeriod", "stop_duration": 60},
        ]
    else:
        base.pop("protections", None)

    out_config_path.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    params_path = root / "app" / "params.json"
    base_config_path = root / "user_data" / "config.json"
    out_config_path = root / "user_data" / "config.generated.json"
    generate_config(params_path, base_config_path, out_config_path)
    print(f"Wrote {out_config_path}")
