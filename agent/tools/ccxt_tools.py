from __future__ import annotations


def _get_exchange_from_context(context: dict):
    # context expects: {"exchange": ccxt_instance}
    ex = (context or {}).get("exchange")
    if ex is None:
        raise RuntimeError("Missing ccxt exchange in context")
    return ex


def fetch_balance(*, args: dict, context: dict) -> dict:
    ex = _get_exchange_from_context(context)
    return ex.fetch_balance()


def fetch_positions(*, args: dict, context: dict) -> list:
    ex = _get_exchange_from_context(context)
    return ex.fetch_positions()


def fetch_open_orders(*, args: dict, context: dict) -> list:
    ex = _get_exchange_from_context(context)
    symbol = args.get("symbol")
    if symbol:
        return ex.fetch_open_orders(symbol)
    return ex.fetch_open_orders()


def fetch_ticker(*, args: dict, context: dict) -> dict:
    ex = _get_exchange_from_context(context)
    symbol = args.get("symbol")
    if not symbol:
        raise RuntimeError("symbol is required")
    return ex.fetch_ticker(symbol)


def fetch_ohlcv(*, args: dict, context: dict) -> list:
    ex = _get_exchange_from_context(context)
    symbol = args.get("symbol")
    timeframe = args.get("timeframe")
    limit = int(args.get("limit") or 200)
    if not symbol:
        raise RuntimeError("symbol is required")
    if not timeframe:
        raise RuntimeError("timeframe is required")
    return ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
