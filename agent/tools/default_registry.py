from agent.tools import ccxt_tools, freqtrade_tools
from agent.tools.registry import ToolRegistry, ToolSpec


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()

    reg.register(
        ToolSpec(
            name="ccxt.fetch_balance",
            description="Fetch OKX balance (raw ccxt)",
            risk_level="low",
            requires_confirmation=False,
        ),
        ccxt_tools.fetch_balance,
    )
    reg.register(
        ToolSpec(
            name="ccxt.fetch_positions",
            description="Fetch OKX positions (raw ccxt)",
            risk_level="low",
            requires_confirmation=False,
        ),
        ccxt_tools.fetch_positions,
    )
    reg.register(
        ToolSpec(
            name="ccxt.fetch_open_orders",
            description="Fetch OKX open orders (raw ccxt)",
            risk_level="low",
            requires_confirmation=False,
        ),
        ccxt_tools.fetch_open_orders,
    )
    reg.register(
        ToolSpec(
            name="ccxt.fetch_ticker",
            description="Fetch ticker for a symbol",
            risk_level="low",
            requires_confirmation=False,
        ),
        ccxt_tools.fetch_ticker,
    )
    reg.register(
        ToolSpec(
            name="ccxt.fetch_ohlcv",
            description="Fetch OHLCV candles for a symbol",
            risk_level="low",
            requires_confirmation=False,
        ),
        ccxt_tools.fetch_ohlcv,
    )

    reg.register(
        ToolSpec(
            name="freqtrade.get_status",
            description="Fetch freqtrade open trades status",
            risk_level="low",
            requires_confirmation=False,
        ),
        freqtrade_tools.get_status,
    )
    reg.register(
        ToolSpec(
            name="freqtrade.get_balance",
            description="Fetch freqtrade computed balance",
            risk_level="low",
            requires_confirmation=False,
        ),
        freqtrade_tools.get_balance,
    )
    reg.register(
        ToolSpec(
            name="freqtrade.get_trades",
            description="Fetch freqtrade trades history",
            risk_level="low",
            requires_confirmation=False,
        ),
        freqtrade_tools.get_trades,
    )

    return reg
