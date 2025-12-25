本项目是一个基于 Freqtrade 的 OKX 实盘交易 Agent（带本地可视化界面）。

## 0. 本地启动 UI

```bash
streamlit run /Users/bytedance/Downloads/DataAgent/okx-trading-agent/app/ui.py
```

UI 功能：
- 配置交易参数（timeframe / 杠杆上限 / max_open_trades / 交易对）
- 配置风控阈值（最大回撤 / 日亏 / 开关）
- 新闻白名单抓取与本地摘要
- 生成 `user_data/config.generated.json`
- 一键启动/停止 bot，并查看日志

## 1. 生成运行配置
在 UI 里点“生成 config.generated.json”，或命令行：

```bash
python /Users/bytedance/Downloads/DataAgent/okx-trading-agent/app/generate_config.py
```

## 2. 启动交易（实盘）
推荐通过 UI 启动。

命令行方式：
```bash
freqtrade trade \
  --userdir /Users/bytedance/Downloads/DataAgent/okx-trading-agent/user_data \
  -c /Users/bytedance/Downloads/DataAgent/okx-trading-agent/user_data/config.generated.json \
  --logfile /Users/bytedance/Downloads/DataAgent/okx-trading-agent/app/bot.log
```

API Server 会启动在：
- http://127.0.0.1:18080
- basic auth：`admin/admin`（建议你后续自行修改）

## 3. LLM（可选，默认关闭）
LLM 只用于“入场前否决/放行”的轻量 Gatekeeper，不直接下单。

环境变量：
- `AGENT_LLM_ENABLED=1`
- `AGENT_LLM_PROVIDER=anthropic`
- `AGENT_LLM_MODEL=claude-3-5-sonnet-latest`
- `AGENT_LLM_API_KEY_ENV=ANTHROPIC_API_KEY`
- 以及 `ANTHROPIC_API_KEY=...`

不设置或关闭 `AGENT_LLM_ENABLED` 则不会调用 LLM。

## 4. 新闻（白名单）
UI 里只允许抓取白名单域名的 URL，并对文本做基础去注入清洗。

## 5. 交易记忆（FinMem 风格，简化版）
- 数据库：`agent/memory.sqlite`
- 记录：每次订单成交回调会写入 `order_filled` 事件
- 检索：LLM Gatekeeper 会检索与交易对相关的最近记忆（轻量 substring match）

## 6. 重要说明（当前实现边界）
- 风控：日亏/回撤 目前通过 Freqtrade protections 机制实现（会阻止开新仓，不会强制平仓）。
- 部署到网站：后续可将 Streamlit 改为 FastAPI + 前端并部署；目前是本地可用版本。
