import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
# Make sure local packages (agent/, app/) are importable when running `streamlit run app/ui.py`
sys.path.insert(0, str(ROOT))

from agent.freqtrade_api import get_json, load_api_auth_from_config
from generate_config import generate_config


def _load_exchange_credentials(config_path: Path) -> dict:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    ex = cfg.get("exchange") or {}
    return {
        "name": ex.get("name"),
        "key": ex.get("key"),
        "secret": ex.get("secret"),
        "password": ex.get("password"),
        "ccxt_config": ex.get("ccxt_config") or {},
    }

PARAMS_PATH = ROOT / "app" / "params.json"
BASE_CONFIG_PATH = ROOT / "user_data" / "config.json"
GEN_CONFIG_PATH = ROOT / "user_data" / "config.generated.json"


def load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))


def save_params(p: dict) -> None:
    PARAMS_PATH.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


st.set_page_config(page_title="OKX Trading Agent", layout="wide")

st.title("OKX Trading Agent 控制台（本地）")

if not BASE_CONFIG_PATH.exists():
    st.error(f"缺少 {BASE_CONFIG_PATH}")
    st.stop()

params = load_params()

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.subheader("交易参数")
    trading = params.setdefault("trading", {})
    trading["timeframe"] = st.selectbox(
        "Timeframe",
        ["15m", "1h", "4h"],
        index=["15m", "1h", "4h"].index(trading.get("timeframe", "1h")),
    )
    trading["max_open_trades"] = st.number_input(
        "最大同时持仓数", min_value=1, max_value=20, value=int(trading.get("max_open_trades", 3))
    )
    trading["tradable_balance_ratio"] = st.slider(
        "可用资金比例", min_value=0.1, max_value=1.0, value=float(trading.get("tradable_balance_ratio", 0.95))
    )
    trading["leverage"] = st.slider(
        "最大杠杆（上限）", min_value=1, max_value=10, value=int(trading.get("leverage", 10))
    )

with col2:
    st.subheader("交易对")
    pairs = trading.get("pairs", [])
    default_pairs = ["BTC/USDT:USDT", "BNB/USDT:USDT", "SOL/USDT:USDT", "WLD/USDT:USDT", "TRUMP/USDT:USDT"]
    selected = st.multiselect("启用交易对", options=default_pairs, default=pairs or default_pairs)
    trading["pairs"] = selected

with col3:
    st.subheader("风控参数")
    risk = params.setdefault("risk", {})
    risk["enabled"] = st.checkbox("启用硬风控(推荐)", value=bool(risk.get("enabled", True)))
    risk["max_drawdown"] = st.slider(
        "最大回撤熔断（比例）", min_value=0.05, max_value=0.50, value=float(risk.get("max_drawdown", 0.25)), step=0.01
    )
    risk["daily_loss"] = st.slider(
        "日亏熔断（比例）", min_value=0.01, max_value=0.20, value=float(risk.get("daily_loss", 0.05)), step=0.01
    )
    risk["manual_unlock_only"] = st.checkbox("熔断后必须手动解除", value=bool(risk.get("manual_unlock_only", True)))

with st.expander("新闻 (白名单抓取)", expanded=False):
    news = params.setdefault("news", {})
    news_enabled = st.checkbox("启用新闻", value=bool(news.get("enabled", True)))
    news["enabled"] = news_enabled
    allow_domains = news.get("allow_domains", [])
    allow_domains_str = st.text_area(
        "允许域名（每行一个）",
        "\n".join(allow_domains) if allow_domains else "coindesk.com\nwublock123.com\nfollowin.io",
        height=90,
    )
    news["allow_domains"] = [d.strip() for d in allow_domains_str.splitlines() if d.strip()]

    urls_str = st.text_area("待抓取 URL（每行一个）", "\n".join(news.get("urls", [])), height=90)
    news["urls"] = [u.strip() for u in urls_str.splitlines() if u.strip()]
    if st.button("抓取并摘要(本地)"):
        from agent.news import fetch_and_summarize

        urls = [u.strip() for u in urls_str.splitlines() if u.strip()]
        summaries = fetch_and_summarize(urls, news["allow_domains"])
        params.setdefault("runtime", {})["news_summaries"] = summaries
        if summaries:
            st.text_area("摘要输出", "\n\n---\n\n".join(summaries), height=260)
        else:
            st.warning("没有抓到内容（可能域名不在白名单，或 URL 不可访问）")

st.divider()

left, right = st.columns([1, 2])

with left:
    if st.button("保存参数"):
        save_params(params)
        st.success("已保存到 app/params.json")

    if st.button("生成 config.generated.json"):
        save_params(params)
        generate_config(PARAMS_PATH, BASE_CONFIG_PATH, GEN_CONFIG_PATH)
        st.success(f"已生成 {GEN_CONFIG_PATH}")

    st.caption("说明：bot 实盘建议使用 config.generated.json 启动。风控阈值来自本页面参数。")

with right:
    st.subheader("本地命令")
    st.code(
        f"streamlit run {ROOT / 'app' / 'ui.py'}\n"
        f"python {ROOT / 'app' / 'generate_config.py'}\n"
        f"freqtrade trade --userdir {ROOT / 'user_data'} -c {GEN_CONFIG_PATH}\n",
        language="bash",
    )

st.divider()

st.subheader("Bot 控制")


def _safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _df(obj) -> "pd.DataFrame":
    if obj is None:
        return pd.DataFrame()
    if isinstance(obj, list):
        return pd.DataFrame(obj)
    if isinstance(obj, dict):
        return pd.DataFrame([obj])
    return pd.DataFrame([{"value": obj}])


def _redact(s: str | None) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "***"
    return s[:4] + "..." + s[-4:]


def _okx_balance_table(bal: dict, *, exchange=None, dust_usdt: float = 0.5) -> pd.DataFrame:
    # ccxt balance shape: {'free': {...}, 'used': {...}, 'total': {...}, 'info': ...}
    free = bal.get("free") or {}
    used = bal.get("used") or {}
    total = bal.get("total") or {}

    # Optional USDT valuation via tickers.
    tickers = {}
    if exchange is not None:
        try:
            tickers = exchange.fetch_tickers()
        except Exception:
            tickers = {}

    def _to_usdt(ccy: str, amount: float) -> float | None:
        if amount == 0:
            return 0.0
        if ccy.upper() == "USDT":
            return float(amount)
        if not tickers:
            return None
        # Try direct markets first.
        for sym in (f"{ccy}/USDT:USDT", f"{ccy}/USDT"):
            t = tickers.get(sym)
            last = (t or {}).get("last") if isinstance(t, dict) else None
            if last:
                return float(amount) * float(last)
        # Try inverse markets.
        for sym in (f"USDT/{ccy}:USDT", f"USDT/{ccy}"):
            t = tickers.get(sym)
            last = (t or {}).get("last") if isinstance(t, dict) else None
            if last:
                return float(amount) / float(last)
        return None

    rows = []
    for ccy in sorted(set(list(free.keys()) + list(used.keys()) + list(total.keys()))):
        try:
            f = float(free.get(ccy) or 0)
            u = float(used.get(ccy) or 0)
            t = float(total.get(ccy) or 0)
        except Exception:
            continue
        if f == 0 and u == 0 and t == 0:
            continue
        value_usdt = _to_usdt(ccy, t)
        rows.append({"currency": ccy, "free": f, "used": u, "total": t, "value_usdt": value_usdt})

    df = pd.DataFrame(rows)
    if not df.empty:
        # Drop dust by USDT valuation when possible.
        if "value_usdt" in df.columns:
            df = df[(df["value_usdt"].isna()) | (df["value_usdt"] >= dust_usdt)]
        df = df.sort_values(by=("value_usdt" if "value_usdt" in df.columns else "total"), ascending=False)
    return df


def _okx_orders_table(orders: list) -> pd.DataFrame:
    rows = []
    for o in orders or []:
        if not isinstance(o, dict):
            continue
        rows.append(
            {
                "symbol": o.get("symbol"),
                "type": o.get("type"),
                "side": o.get("side"),
                "price": o.get("price"),
                "amount": o.get("amount"),
                "filled": o.get("filled"),
                "remaining": o.get("remaining"),
                "status": o.get("status"),
                "id": o.get("id"),
                "timestamp": o.get("timestamp"),
            }
        )
    return pd.DataFrame(rows)


def _okx_positions_table(positions: list) -> pd.DataFrame:
    rows = []
    for p in positions or []:
        if not isinstance(p, dict):
            continue
        rows.append(
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "contracts": p.get("contracts"),
                "contractSize": p.get("contractSize"),
                "entryPrice": p.get("entryPrice"),
                "markPrice": p.get("markPrice"),
                "unrealizedPnl": p.get("unrealizedPnl"),
                "leverage": p.get("leverage"),
                "marginMode": p.get("marginMode"),
                "liquidationPrice": p.get("liquidationPrice"),
                "collateral": p.get("collateral"),
            }
        )
    return pd.DataFrame(rows)

PID_PATH = ROOT / "app" / "bot.pid"
LOG_PATH = ROOT / "app" / "bot.log"


def _pid_is_running(pid: int) -> bool:
    try:
        # signal 0 does not kill, only checks existence
        import os

        os.kill(pid, 0)
        return True
    except Exception:
        return False


def get_bot_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    if _pid_is_running(pid):
        return pid

    # Stale pidfile - clean it up so UI won't report "running".
    try:
        PID_PATH.unlink()
    except Exception:
        pass
    return None


bot_pid = get_bot_pid()

c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    if GEN_CONFIG_PATH.exists():
        st.success("配置：已生成")
    else:
        st.warning("配置：未生成")

with c2:
    if bot_pid:
        st.success(f"运行中 PID={bot_pid}")
    else:
        st.info("未运行")

with c3:
    start_disabled = (not GEN_CONFIG_PATH.exists()) or bool(bot_pid)
    stop_disabled = not bool(bot_pid)

    if st.button("启动 bot", disabled=start_disabled):
        cmd = [
            "freqtrade",
            "trade",
            "--userdir",
            str(ROOT / "user_data"),
            "-c",
            str(GEN_CONFIG_PATH),
            "--logfile",
            str(LOG_PATH),
        ]
        p = subprocess.Popen(cmd)
        PID_PATH.write_text(str(p.pid), encoding="utf-8")
        st.success(f"已启动 PID={p.pid} (如果 API 仍连接失败，请看下方 bot.log)")
        time.sleep(1)
        st.rerun()

    if st.button("停止 bot", disabled=stop_disabled):
        pid = bot_pid
        if pid:
            import os
            import signal

            try:
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                st.error(f"停止失败: {e}")
            else:
                st.success("已发送停止信号")
            time.sleep(1)
            st.rerun()

st.divider()

st.subheader("Agent Console（WIP）")

# 说明：这里优先展示“可观测性”(资产/持仓/委托/成交) + Agent 交互(对话/计划/工具确认/回放)。

from agent.agent_core import (
    approve_tool_call,
    ensure_session,
    execute_approved_tool_calls,
    get_latest_chart,
    list_pending_tool_calls,
    user_message,
)
from agent.event_log import list_sessions, load_events

agent_col1, agent_col2, agent_col3, agent_col4, agent_col5 = st.columns([1, 1, 2, 1, 1])
with agent_col1:
    api_enabled = st.toggle("启用 API 仪表盘", value=True)
with agent_col2:
    api_config_choice = st.selectbox("API 配置来源", ["config.generated.json", "config.json"], index=0)
with agent_col3:
    agent_enabled = st.toggle("启用 Agent 对话", value=True)
    params = load_params()
    agent_conf = params.setdefault("agent", {})
    agent_conf["llm_api_url"] = st.text_input("API 完整地址", value=str(agent_conf.get("llm_api_url", "https://api.anthropic.com")), placeholder="https://api.anthropic.com")
    agent_conf["llm_model"] = st.text_input("模型名称", value=str(agent_conf.get("llm_model", "claude-3-5-sonnet-latest")), placeholder="claude-3-5-sonnet-latest")
    agent_conf["llm_api_key"] = st.text_input("API 秘钥", value=str(agent_conf.get("llm_api_key", "")), placeholder="输入 API Key", type="password")
    if st.button("保存 Agent 配置", key="agent_conf_save"):
        save_params(params)
with agent_col4:
    api_user_override = st.text_input("API 用户", value="", placeholder="默认读取 config")
with agent_col5:
    api_pass_override = st.text_input("API 密码", value="", placeholder="默认读取 config", type="password")
    refresh = st.button("刷新（API）")

# ---------------- Agent Chat / Plan / Tools ----------------
if "agent_session_id" not in st.session_state:
    st.session_state["agent_session_id"] = ensure_session(None)

agent_session_id = st.session_state["agent_session_id"]

chat_col, plan_col = st.columns([2, 1])

with chat_col:
    st.markdown("### 对话")
    chat_events = [e for e in load_events(agent_session_id) if e.get("type") in {"user_message", "assistant_message"}]
    for e in chat_events[-40:]:
        if e["type"] == "user_message":
            st.markdown(f"**你：** {e['data'].get('text','')}")
        else:
            st.markdown(f"**Agent：** {e['data'].get('text','')}")

    user_input = st.text_input("输入任务/问题：", value="", key="agent_user_input")
    send = st.button("发送", key="agent_send")

    if send and user_input.strip():
        # Build tool contexts from the same config selection as the dashboard.
        config_path = GEN_CONFIG_PATH if api_config_choice == "config.generated.json" else BASE_CONFIG_PATH

        # freqtrade api auth
        ft_auth = None
        try:
            ft_auth = load_api_auth_from_config(str(config_path))
            if api_user_override.strip():
                ft_auth.username = api_user_override.strip()
            if api_pass_override.strip():
                ft_auth.password = api_pass_override
        except Exception:
            ft_auth = None

        # ccxt exchange (read-only tools)
        ccxt_ex = None
        try:
            ex_cfg = _load_exchange_credentials(config_path)
            import ccxt  # type: ignore

            exchange_cls = getattr(ccxt, str(ex_cfg.get("name") or "okx"))
            ccxt_ex = exchange_cls(
                {
                    "apiKey": ex_cfg.get("key"),
                    "secret": ex_cfg.get("secret"),
                    "password": ex_cfg.get("password"),
                    **(ex_cfg.get("ccxt_config") or {}),
                }
            )
            ccxt_ex.options = {**getattr(ccxt_ex, "options", {}), "defaultType": "swap"}
        except Exception:
            ccxt_ex = None

        ctx = {
            "mode": "analysis",
            "freqtrade_auth": ft_auth,
            "exchange": ccxt_ex,
            "pairs": trading.get("pairs", []),
            "timeframe": trading.get("timeframe", "1h"),
        }

        user_message(agent_session_id, user_input.strip(), context={"pairs": ctx["pairs"], "timeframe": ctx["timeframe"]})
        st.rerun()

with plan_col:
    st.markdown("### 工具与图表")

    pending = list_pending_tool_calls(agent_session_id)
    if pending:
        st.markdown("**待确认工具调用**")
        for tc in pending:
            call_id = tc.get("call_id")
            st.code(json.dumps(tc, ensure_ascii=False, indent=2), language="json")
            if call_id and st.button(f"批准执行 {call_id}", key=f"approve_{call_id}"):
                approve_tool_call(agent_session_id, call_id)
                st.rerun()

        if st.button("执行已批准工具", key="exec_tools"):
            # Build context same as send block
            config_path = GEN_CONFIG_PATH if api_config_choice == "config.generated.json" else BASE_CONFIG_PATH

            ft_auth = None
            try:
                ft_auth = load_api_auth_from_config(str(config_path))
                if api_user_override.strip():
                    ft_auth.username = api_user_override.strip()
                if api_pass_override.strip():
                    ft_auth.password = api_pass_override
            except Exception:
                ft_auth = None

            ccxt_ex = None
            try:
                ex_cfg = _load_exchange_credentials(config_path)
                import ccxt  # type: ignore

                exchange_cls = getattr(ccxt, str(ex_cfg.get("name") or "okx"))
                ccxt_ex = exchange_cls(
                    {
                        "apiKey": ex_cfg.get("key"),
                        "secret": ex_cfg.get("secret"),
                        "password": ex_cfg.get("password"),
                        **(ex_cfg.get("ccxt_config") or {}),
                    }
                )
                ccxt_ex.options = {**getattr(ccxt_ex, "options", {}), "defaultType": "swap"}
            except Exception:
                ccxt_ex = None

            tool_ctx = {"freqtrade_auth": ft_auth, "exchange": ccxt_ex}
            execute_approved_tool_calls(agent_session_id, context=tool_ctx)
            st.rerun()

    chart = get_latest_chart(agent_session_id)
    if chart and isinstance(chart.get("content"), dict) and "plotly" in chart["content"]:
        import plotly.graph_objects as go

        fig = go.Figure(chart["content"]["plotly"])
        st.plotly_chart(fig, use_container_width=True)
        inds = chart["content"].get("indicators")
        if isinstance(inds, dict):
            with st.expander("指标摘要", expanded=False):
                st.json(inds)

    with st.expander("Sessions / 回放", expanded=False):
        sessions = list_sessions(limit=20)
        for s in sessions:
            sid = s.get("session_id")
            if sid and st.button(f"切换到 {sid[:8]} (events={s.get('n')})", key=f"sess_{sid}"):
                st.session_state["agent_session_id"] = sid
                st.rerun()


api_data = {}
api_error = None

if api_enabled:
    try:
        config_path = GEN_CONFIG_PATH if api_config_choice == "config.generated.json" else BASE_CONFIG_PATH
        auth = load_api_auth_from_config(str(config_path))
        if api_user_override.strip():
            auth.username = api_user_override.strip()
        if api_pass_override.strip():
            auth.password = api_pass_override
        base_url = auth.base_url

        # Only fetch when user clicks refresh.
        if refresh:
            api_data["status"] = get_json(auth, "/api/v1/status")
            api_data["balance"] = get_json(auth, "/api/v1/balance")
            api_data["performance"] = get_json(auth, "/api/v1/performance")
            api_data["profit"] = get_json(auth, "/api/v1/profit")
            api_data["trades"] = get_json(auth, "/api/v1/trades")

        st.caption(f"API: {base_url} (Basic Auth) | 点击『刷新（API）』拉取数据")
    except Exception as e:
        api_error = str(e)

if api_error:
    st.error(f"API 调用失败：{api_error}")
    st.caption(
        "如果你用 curl/浏览器访问看到 {\"detail\":\"Unauthorized\"}，说明 API Server 开启了认证。"
        "请确认：使用的配置文件里 api_server.username/password 与你输入的一致。"
        "（默认是 admin/admin）"
    )
else:
    # ---- 资产概览（尽量兼容不同结构） ----
    bal = api_data.get("balance") or {}
    bal_list = bal.get("balances") if isinstance(bal, dict) else None

    total = _safe_get(bal, "total", default=None)
    stake = _safe_get(bal, "stake_currency", default=None)

    perf = api_data.get("performance") or {}
    profit = api_data.get("profit") or {}

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Stake", str(stake) if stake is not None else "-")
    m2.metric("Total", str(total) if total is not None else "-")
    m3.metric("Profit", str(profit.get("profit_total_abs", profit.get("profit_total", "-"))) if isinstance(profit, dict) else "-")
    m4.metric("Open trades", str(len(api_data.get("status") or [])))

    # ---- 持仓 / 开仓列表（Freqtrade 用 status 作为 open trades） ----
    st.markdown("### 持仓（Freqtrade Open Trades）")
    status_rows = api_data.get("status")
    if status_rows == []:
        st.info("当前没有 Freqtrade 管理的持仓（/api/v1/status 为空）。这不代表 OKX 账户没有手工仓位/委托。")
    st.dataframe(_df(status_rows), use_container_width=True, height=240)

    # ---- 挂单（如果在 status 的 orders 里） ----
    st.markdown("### 委托（来自 Open Trades 的 orders 字段）")
    orders_rows = []
    if isinstance(status_rows, list):
        for t in status_rows:
            if isinstance(t, dict):
                for o in t.get("orders") or []:
                    if isinstance(o, dict):
                        row = {"trade_id": t.get("trade_id"), "pair": t.get("pair"), **o}
                        orders_rows.append(row)
    st.dataframe(_df(orders_rows), use_container_width=True, height=220)

    # ---- 成交 / 历史交易 ----
    st.markdown("### 成交/历史交易（Trades）")
    trades = api_data.get("trades")
    if isinstance(trades, dict) and "trades" in trades:
        trades = trades.get("trades")
    st.dataframe(_df(trades), use_container_width=True, height=240)

    # ---- OKX 账户视图（WIP：直连交易所） ----
    st.markdown("### OKX 账户（直连，包含手工仓位/委托）")
    okx_col1, okx_col2 = st.columns([1, 3])
    with okx_col1:
        okx_enabled = st.toggle("启用 OKX 直连", value=False)
    with okx_col2:
        okx_refresh = st.button("刷新（OKX）")

    if okx_enabled:
        if "okx_snapshot" not in st.session_state:
            st.session_state["okx_snapshot"] = None

        if okx_refresh or st.session_state["okx_snapshot"] is None:
            try:
                config_path = GEN_CONFIG_PATH if api_config_choice == "config.generated.json" else BASE_CONFIG_PATH
                ex_cfg = _load_exchange_credentials(config_path)

                import ccxt  # type: ignore

                exchange_cls = getattr(ccxt, str(ex_cfg.get("name") or "okx"))
                exchange = exchange_cls(
                    {
                        "apiKey": ex_cfg.get("key"),
                        "secret": ex_cfg.get("secret"),
                        "password": ex_cfg.get("password"),
                        **(ex_cfg.get("ccxt_config") or {}),
                    }
                )
                # Make sure we query swaps in futures mode.
                exchange.options = {**getattr(exchange, "options", {}), "defaultType": "swap"}

                okx_bal = exchange.fetch_balance()
                okx_positions = []
                okx_open_orders = []
                try:
                    okx_positions = exchange.fetch_positions()
                except Exception:
                    okx_positions = []
                try:
                    okx_open_orders = exchange.fetch_open_orders()
                except Exception:
                    okx_open_orders = []

                st.session_state["okx_snapshot"] = {
                    "ex_id": exchange.id,
                    "defaultType": (getattr(exchange, "options", {}) or {}).get("defaultType"),
                    "apiKey": _redact(ex_cfg.get("key")),
                    "balance": okx_bal,
                    "positions": okx_positions,
                    "open_orders": okx_open_orders,
                }
            except Exception as e:
                st.error(f"OKX 直连失败：{e}")

        snap = st.session_state.get("okx_snapshot")
        if isinstance(snap, dict):
            okx_bal = snap.get("balance") or {}
            okx_positions = snap.get("positions") or []
            okx_open_orders = snap.get("open_orders") or []

            show_dust = st.checkbox("显示小额资产(dust)", value=False)
            dust_usdt = 0.0 if show_dust else 0.5

            # --- Summary (WIP) ---
            # Rebuild exchange only for ticker valuation.
            exchange_for_ticker = None
            try:
                config_path = GEN_CONFIG_PATH if api_config_choice == "config.generated.json" else BASE_CONFIG_PATH
                ex_cfg = _load_exchange_credentials(config_path)
                import ccxt  # type: ignore

                exchange_cls = getattr(ccxt, str(ex_cfg.get("name") or "okx"))
                exchange_for_ticker = exchange_cls(
                    {
                        "apiKey": ex_cfg.get("key"),
                        "secret": ex_cfg.get("secret"),
                        "password": ex_cfg.get("password"),
                        **(ex_cfg.get("ccxt_config") or {}),
                    }
                )
                exchange_for_ticker.options = {**getattr(exchange_for_ticker, "options", {}), "defaultType": "swap"}
            except Exception:
                exchange_for_ticker = None

            bal_df = _okx_balance_table(okx_bal, exchange=exchange_for_ticker, dust_usdt=dust_usdt)

            total_free = float(bal_df["free"].sum()) if not bal_df.empty else 0.0
            total_used = float(bal_df["used"].sum()) if not bal_df.empty else 0.0
            total_total = float(bal_df["total"].sum()) if not bal_df.empty else 0.0
            total_usdt = (
                float(bal_df["value_usdt"].fillna(0).sum()) if (not bal_df.empty and "value_usdt" in bal_df.columns) else 0.0
            )

            s1, s2, s3, s4, s5 = st.columns(5)
            s1.metric("总资产(USDT估值)", f"{total_usdt:,.2f}")
            s2.metric("资产总额(Σtotal)", f"{total_total:,.4f}")
            s3.metric("可用(Σfree)", f"{total_free:,.4f}")
            s4.metric("占用(Σused)", f"{total_used:,.4f}")
            s5.metric("未成交委托", str(len(okx_open_orders or [])))

            st.markdown("#### 资产明细")
            st.dataframe(bal_df, use_container_width=True, height=260)

            st.markdown("#### 持仓（positions）")
            st.dataframe(_okx_positions_table(okx_positions), use_container_width=True, height=240)

            st.markdown("#### 委托（open orders）")
            st.dataframe(_okx_orders_table(okx_open_orders), use_container_width=True, height=240)

            with st.expander("调试：raw JSON（余额/持仓/委托）", expanded=False):
                st.caption(
                    f"exchange={snap.get('ex_id')} apiKey={snap.get('apiKey')} defaultType={snap.get('defaultType')}"
                )
                st.json({"balance": okx_bal, "positions": okx_positions, "open_orders": okx_open_orders})

    # ---- Agent 事件流（WIP 占位：暂时用 bot.log tail） ----
    st.markdown("### 事件流（WIP：暂用日志代替）")
    if LOG_PATH.exists():
        log_text = LOG_PATH.read_text(encoding="utf-8", errors="ignore")
        st.text_area("bot.log (tail)", log_text[-12000:], height=220)
    else:
        st.caption("尚无日志文件：启动后会生成 app/bot.log")

st.divider()

st.subheader("日志")
if LOG_PATH.exists():
    log_text = LOG_PATH.read_text(encoding="utf-8", errors="ignore")
    st.text_area("bot.log", log_text[-20000:], height=300)
else:
    st.caption("尚无日志文件：启动后会生成 app/bot.log")
