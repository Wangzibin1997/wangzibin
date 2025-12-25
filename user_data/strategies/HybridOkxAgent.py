# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame

import os
from typing import Dict, Optional, Union, Tuple

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,  # @informative decorator
    # Hyperopt Parameters
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    # timeframe helpers
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    # Strategy helper functions
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
    AnnotationType,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
from technical import qtpylib


class HybridOkxAgent(IStrategy):
    protections = []

    def order_filled(self, pair: str, trade: Trade, order, current_time: datetime, **kwargs) -> None:
        try:
            from agent.memory import add_memory

            add_memory(
                kind="order_filled",
                pair=pair,
                content={
                    "pair": pair,
                    "is_short": bool(getattr(trade, "is_short", False)),
                    "amount": float(getattr(order, "amount", 0.0) or 0.0),
                    "price": float(getattr(order, "price", 0.0) or 0.0),
                    "side": str(getattr(order, "ft_order_side", "")),
                    "reason": str(getattr(order, "ft_order_tag", "")),
                    "ts": current_time.isoformat(),
                },
            )
        except Exception:
            pass

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if os.getenv("AGENT_LLM_ENABLED", "0") not in ("1", "true", "TRUE"):
            return True

        # Keep this lightweight: only use already computed indicators.
        try:
            df = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            row = df.iloc[-1]
            indicators = {
                "rsi": float(row.get("rsi", 0.0)),
                "adx": float(row.get("adx", 0.0)),
                "bb_percent": float(row.get("bb_percent", 0.0)),
                "ema20": float(row.get("ema20", 0.0)) if "ema20" in row else None,
                "ema50": float(row.get("ema50", 0.0)) if "ema50" in row else None,
            }
        except Exception:
            indicators = {}

        try:
            from agent.policy import decide_entry
            from agent.runtime import load_runtime_news_summaries

            from agent.memory import search_memory

            decision = decide_entry(
                pair=pair,
                side=side,
                timeframe=self.timeframe,
                indicators=indicators,
                recent_news=load_runtime_news_summaries(),
                memory_hits=search_memory(pair, limit=3, pair=pair),
            )
            return bool(decision.allow)
        except Exception:
            return True

    """
    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/latest/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """
    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    # Mid/low frequency timeframe
    timeframe = "1h"

    # Futures: allow shorting
    can_short: bool = True

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        "0": 0.03
    }

    # Hard stoploss (risk layer will further constrain)
    stoploss = -0.08

    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # Strategy parameters
    buy_rsi = IntParameter(10, 40, default=30, space="buy")
    sell_rsi = IntParameter(60, 90, default=70, space="sell")# Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False
    }

    # Optional order time in force.
    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC"
    }
    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            "main_plot": {
                "tema": {},
                "sar": {"color": "white"},
            },
            "subplots": {
                # Subplots - each dict defines one additional plot
                "MACD": {
                    "macd": {"color": "blue"},
                    "macdsignal": {"color": "orange"},
                },
                "RSI": {
                    "rsi": {"color": "red"},
                }
            }
        }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        These pair/interval combinations are non-tradeable, unless they are part
        of the whitelist as well.
        For more information, please consult the documentation
        :return: List of tuples in the format (pair, interval)
            Sample: return [("ETH/USDT", "5m"),
                            ("BTC/USDT", "15m"),
                            ]
        """
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """
        # Momentum Indicators
        # ------------------------------------

        # ADX
        dataframe["adx"] = ta.ADX(dataframe)

        # # Plus Directional Indicator / Movement
        # dataframe["plus_dm"] = ta.PLUS_DM(dataframe)
        # dataframe["plus_di"] = ta.PLUS_DI(dataframe)

        # # Minus Directional Indicator / Movement
        # dataframe["minus_dm"] = ta.MINUS_DM(dataframe)
        # dataframe["minus_di"] = ta.MINUS_DI(dataframe)

        # # Aroon, Aroon Oscillator
        # aroon = ta.AROON(dataframe)
        # dataframe["aroonup"] = aroon["aroonup"]
        # dataframe["aroondown"] = aroon["aroondown"]
        # dataframe["aroonosc"] = ta.AROONOSC(dataframe)

        # # Awesome Oscillator
        # dataframe["ao"] = qtpylib.awesome_oscillator(dataframe)

        # # Keltner Channel
        # keltner = qtpylib.keltner_channel(dataframe)
        # dataframe["kc_upperband"] = keltner["upper"]
        # dataframe["kc_lowerband"] = keltner["lower"]
        # dataframe["kc_middleband"] = keltner["mid"]
        # dataframe["kc_percent"] = (
        #     (dataframe["close"] - dataframe["kc_lowerband"]) /
        #     (dataframe["kc_upperband"] - dataframe["kc_lowerband"])
        # )
        # dataframe["kc_width"] = (
        #     (dataframe["kc_upperband"] - dataframe["kc_lowerband"]) / dataframe["kc_middleband"]
        # )

        # # Ultimate Oscillator
        # dataframe["uo"] = ta.ULTOSC(dataframe)

        # # Commodity Channel Index: values [Oversold:-100, Overbought:100]
        # dataframe["cci"] = ta.CCI(dataframe)

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe)

        # # Inverse Fisher transform on RSI: values [-1.0, 1.0] (https://goo.gl/2JGGoy)
        # rsi = 0.1 * (dataframe["rsi"] - 50)
        # dataframe["fisher_rsi"] = (np.exp(2 * rsi) - 1) / (np.exp(2 * rsi) + 1)

        # # Inverse Fisher transform on RSI normalized: values [0.0, 100.0] (https://goo.gl/2JGGoy)
        # dataframe["fisher_rsi_norma"] = 50 * (dataframe["fisher_rsi"] + 1)

        # # Stochastic Slow
        # stoch = ta.STOCH(dataframe)
        # dataframe["slowd"] = stoch["slowd"]
        # dataframe["slowk"] = stoch["slowk"]

        # Stochastic Fast
        stoch_fast = ta.STOCHF(dataframe)
        dataframe["fastd"] = stoch_fast["fastd"]
        dataframe["fastk"] = stoch_fast["fastk"]

        # # Stochastic RSI
        # Please read https://github.com/freqtrade/freqtrade/issues/2961 before using this.
        # STOCHRSI is NOT aligned with tradingview, which may result in non-expected results.
        # stoch_rsi = ta.STOCHRSI(dataframe)
        # dataframe["fastd_rsi"] = stoch_rsi["fastd"]
        # dataframe["fastk_rsi"] = stoch_rsi["fastk"]

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # MFI
        dataframe["mfi"] = ta.MFI(dataframe)

        # # ROC
        # dataframe["roc"] = ta.ROC(dataframe)

        # Overlap Studies
        # ------------------------------------

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["bb_percent"] = (
            (dataframe["close"] - dataframe["bb_lowerband"]) /
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
        )
        dataframe["bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        )

        # Bollinger Bands - Weighted (EMA based instead of SMA)
        # weighted_bollinger = qtpylib.weighted_bollinger_bands(
        #     qtpylib.typical_price(dataframe), window=20, stds=2
        # )
        # dataframe["wbb_upperband"] = weighted_bollinger["upper"]
        # dataframe["wbb_lowerband"] = weighted_bollinger["lower"]
        # dataframe["wbb_middleband"] = weighted_bollinger["mid"]
        # dataframe["wbb_percent"] = (
        #     (dataframe["close"] - dataframe["wbb_lowerband"]) /
        #     (dataframe["wbb_upperband"] - dataframe["wbb_lowerband"])
        # )
        # dataframe["wbb_width"] = (
        #     (dataframe["wbb_upperband"] - dataframe["wbb_lowerband"]) / dataframe["wbb_middleband"]
        # )

        # # EMA - Exponential Moving Average
        # dataframe["ema3"] = ta.EMA(dataframe, timeperiod=3)
        # dataframe["ema5"] = ta.EMA(dataframe, timeperiod=5)
        # dataframe["ema10"] = ta.EMA(dataframe, timeperiod=10)
        # dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        # dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        # dataframe["ema100"] = ta.EMA(dataframe, timeperiod=100)

        # # SMA - Simple Moving Average
        # dataframe["sma3"] = ta.SMA(dataframe, timeperiod=3)
        # dataframe["sma5"] = ta.SMA(dataframe, timeperiod=5)
        # dataframe["sma10"] = ta.SMA(dataframe, timeperiod=10)
        # dataframe["sma21"] = ta.SMA(dataframe, timeperiod=21)
        # dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        # dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)

        # Parabolic SAR
        dataframe["sar"] = ta.SAR(dataframe)

        # TEMA - Triple Exponential Moving Average
        dataframe["tema"] = ta.TEMA(dataframe, timeperiod=9)

        # Cycle Indicator
        # ------------------------------------
        # Hilbert Transform Indicator - SineWave
        hilbert = ta.HT_SINE(dataframe)
        dataframe["htsine"] = hilbert["sine"]
        dataframe["htleadsine"] = hilbert["leadsine"]

        # Pattern Recognition - Bullish candlestick patterns
        # ------------------------------------
        # # Hammer: values [0, 100]
        # dataframe["CDLHAMMER"] = ta.CDLHAMMER(dataframe)
        # # Inverted Hammer: values [0, 100]
        # dataframe["CDLINVERTEDHAMMER"] = ta.CDLINVERTEDHAMMER(dataframe)
        # # Dragonfly Doji: values [0, 100]
        # dataframe["CDLDRAGONFLYDOJI"] = ta.CDLDRAGONFLYDOJI(dataframe)
        # # Piercing Line: values [0, 100]
        # dataframe["CDLPIERCING"] = ta.CDLPIERCING(dataframe) # values [0, 100]
        # # Morningstar: values [0, 100]
        # dataframe["CDLMORNINGSTAR"] = ta.CDLMORNINGSTAR(dataframe) # values [0, 100]
        # # Three White Soldiers: values [0, 100]
        # dataframe["CDL3WHITESOLDIERS"] = ta.CDL3WHITESOLDIERS(dataframe) # values [0, 100]

        # Pattern Recognition - Bearish candlestick patterns
        # ------------------------------------
        # # Hanging Man: values [0, 100]
        # dataframe["CDLHANGINGMAN"] = ta.CDLHANGINGMAN(dataframe)
        # # Shooting Star: values [0, 100]
        # dataframe["CDLSHOOTINGSTAR"] = ta.CDLSHOOTINGSTAR(dataframe)
        # # Gravestone Doji: values [0, 100]
        # dataframe["CDLGRAVESTONEDOJI"] = ta.CDLGRAVESTONEDOJI(dataframe)
        # # Dark Cloud Cover: values [0, 100]
        # dataframe["CDLDARKCLOUDCOVER"] = ta.CDLDARKCLOUDCOVER(dataframe)
        # # Evening Doji Star: values [0, 100]
        # dataframe["CDLEVENINGDOJISTAR"] = ta.CDLEVENINGDOJISTAR(dataframe)
        # # Evening Star: values [0, 100]
        # dataframe["CDLEVENINGSTAR"] = ta.CDLEVENINGSTAR(dataframe)

        # Pattern Recognition - Bullish/Bearish candlestick patterns
        # ------------------------------------
        # # Three Line Strike: values [0, -100, 100]
        # dataframe["CDL3LINESTRIKE"] = ta.CDL3LINESTRIKE(dataframe)
        # # Spinning Top: values [0, -100, 100]
        # dataframe["CDLSPINNINGTOP"] = ta.CDLSPINNINGTOP(dataframe) # values [0, -100, 100]
        # # Engulfing: values [0, -100, 100]
        # dataframe["CDLENGULFING"] = ta.CDLENGULFING(dataframe) # values [0, -100, 100]
        # # Harami: values [0, -100, 100]
        # dataframe["CDLHARAMI"] = ta.CDLHARAMI(dataframe) # values [0, -100, 100]
        # # Three Outside Up/Down: values [0, -100, 100]
        # dataframe["CDL3OUTSIDE"] = ta.CDL3OUTSIDE(dataframe) # values [0, -100, 100]
        # # Three Inside Up/Down: values [0, -100, 100]
        # dataframe["CDL3INSIDE"] = ta.CDL3INSIDE(dataframe) # values [0, -100, 100]

        # # Chart type
        # # ------------------------------------
        # # Heikin Ashi Strategy
        # heikinashi = qtpylib.heikinashi(dataframe)
        # dataframe["ha_open"] = heikinashi["open"]
        # dataframe["ha_close"] = heikinashi["close"]
        # dataframe["ha_high"] = heikinashi["high"]
        # dataframe["ha_low"] = heikinashi["low"]

        # Retrieve best bid and best ask from the orderbook
        # ------------------------------------
        """
        # first check if dataprovider is available
        if self.dp:
            if self.dp.runmode.value in ("live", "dry_run"):
                ob = self.dp.orderbook(metadata["pair"], 1)
                dataframe["best_bid"] = ob["bids"][0][0]
                dataframe["best_ask"] = ob["asks"][0][0]
        """

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Trend regime
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)

        uptrend = dataframe["ema20"] > dataframe["ema50"]
        downtrend = dataframe["ema20"] < dataframe["ema50"]

        # Mean-reversion signals (BB + RSI)
        mr_long = (dataframe["rsi"] < 30) & (dataframe["close"] < dataframe["bb_lowerband"])
        mr_short = (dataframe["rsi"] > 70) & (dataframe["close"] > dataframe["bb_upperband"])

        # Breakout signals (Donchian-ish)
        hh = dataframe["high"].rolling(20).max()
        ll = dataframe["low"].rolling(20).min()
        bo_long = dataframe["close"] > hh.shift(1)
        bo_short = dataframe["close"] < ll.shift(1)

        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (uptrend & (mr_long | bo_long))
                    | (downtrend & bo_long)
                )
            ),
            "enter_long",
        ] = 1

        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (downtrend & (mr_short | bo_short))
                    | (uptrend & bo_short)
                )
            ),
            "enter_short",
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on partial mean reversion / loss of momentum.
        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (dataframe["close"] >= dataframe["bb_middleband"])
                    | (dataframe["rsi"] > 55)
                )
            ),
            "exit_long",
        ] = 1

        dataframe.loc[
            (
                (dataframe["volume"] > 0)
                & (
                    (dataframe["close"] <= dataframe["bb_middleband"])
                    | (dataframe["rsi"] < 45)
                )
            ),
            "exit_short",
        ] = 1

        return dataframe