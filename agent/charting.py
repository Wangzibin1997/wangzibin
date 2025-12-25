from __future__ import annotations

import pandas as pd


def ohlcv_to_df(ohlcv: list) -> pd.DataFrame:
    """ccxt ohlcv -> DataFrame with columns [ts, open, high, low, close, volume]."""
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    if not df.empty:
        df["dt"] = pd.to_datetime(df["ts"], unit="ms")
    return df


def simple_indicators(df: pd.DataFrame) -> dict:
    """Lightweight indicators for LLM context / UI overlays."""
    if df.empty:
        return {}
    out: dict = {}
    close = df["close"].astype(float)
    out["last_close"] = float(close.iloc[-1])
    out["ema20"] = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    out["ema50"] = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    # RSI(14) minimal
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
    return out


def build_plotly_candles(df: pd.DataFrame, *, title: str = "") -> dict:
    """Return plotly figure JSON (so it can be stored as an artifact).

    We store JSON instead of figure object for sqlite-friendly persistence.
    """
    import plotly.graph_objects as go

    if df.empty:
        fig = go.Figure()
        if title:
            fig.update_layout(title=title)
        return fig.to_plotly_json()

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["dt"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="OHLC",
            )
        ]
    )

    # Overlay EMA20/EMA50
    close = df["close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    fig.add_trace(go.Scatter(x=df["dt"], y=ema20, mode="lines", name="EMA20"))
    fig.add_trace(go.Scatter(x=df["dt"], y=ema50, mode="lines", name="EMA50"))

    fig.update_layout(
        title=title or "Candles",
        xaxis_title="Time",
        yaxis_title="Price",
        height=520,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h"),
    )
    return fig.to_plotly_json()
