import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from freqtrade.constants import Config, LongShort
from freqtrade.plugins.protections import IProtection, ProtectionReturn

logger = logging.getLogger(__name__)


class DailyEquityLossProtection(IProtection):
    """
    Daily equity loss protection.

    Uses current wallet total value (including open trades PnL) to compute a daily drawdown.
    Day boundary is evaluated in local timezone by using datetime.now().astimezone().

    NOTE: This only blocks NEW entries. It does not force-close open trades.
    """

    has_global_stop: bool = True
    has_local_stop: bool = False

    def __init__(self, config: Config, protection_config: dict[str, Any]) -> None:
        super().__init__(config, protection_config)
        self._max_daily_loss = float(protection_config.get("max_daily_loss", 0.05))
        self._equity_at_day_start: float | None = None
        self._day_key: str | None = None

    def short_desc(self) -> str:
        return (
            f"{self.name} - Daily equity loss protection, locks when daily loss is > "
            f"{self._max_daily_loss:.2%}."
        )

    def _reason(self, loss: float) -> str:
        return f"Daily equity loss {loss:.2%} passed {self._max_daily_loss:.2%}, locking {self.unlock_reason_time_element}."

    def _current_day_key(self) -> str:
        # Local timezone day boundary
        now_local = datetime.now().astimezone()
        return now_local.strftime("%Y-%m-%d")

    def _get_current_equity(self) -> float | None:
        # Protection has access to the full bot config. Wallet is not directly available here.
        # Freqtrade stores wallet information in config['wallet'] at runtime.
        wallet = self._config.get("wallet")
        if not wallet:
            return None

        # Best-effort compatibility across wallet implementations.
        for attr in ("get_total", "total"):  # get_total() or property
            if hasattr(wallet, attr):
                v = getattr(wallet, attr)
                return float(v() if callable(v) else v)

        for key in ("total", "total_value", "total_wallet"):
            if isinstance(wallet, dict) and key in wallet:
                return float(wallet[key])

        return None

    def _check(self, date_now: datetime) -> ProtectionReturn | None:
        day_key = self._current_day_key()

        equity = self._get_current_equity()
        if equity is None:
            return None

        if self._day_key != day_key or self._equity_at_day_start is None:
            self._day_key = day_key
            self._equity_at_day_start = equity
            return None

        start = self._equity_at_day_start
        if start <= 0:
            return None

        loss = max(0.0, (start - equity) / start)

        if loss > self._max_daily_loss:
            self.log_once(
                f"Trading stopped due to daily equity loss {loss:.2%} > {self._max_daily_loss:.2%}.",
                logger.warning,
            )
            # date_now may be UTC. calculate_lock_end uses trade dates for stop_duration.
            # We'll lock until now + stop_duration.
            until = date_now
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
            until = until + timedelta(minutes=self._stop_duration)
            return ProtectionReturn(lock=True, until=until, reason=self._reason(loss))

        return None

    def global_stop(self, date_now: datetime, side: LongShort) -> ProtectionReturn | None:
        return self._check(date_now)

    def stop_per_pair(self, pair: str, date_now: datetime, side: LongShort) -> ProtectionReturn | None:
        return None
