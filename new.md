# MACATS – Multi-Agent Crypto Trading System (Demo Scaffold)

This is a prototype scaffold for **MACATS**: a modular, multi-agent system for crypto trading.  
It is designed for experimentation with **market data ingestion, sentiment analysis, technical/regime modeling, trading strategy generation, risk management, and (simulated) execution**.

⚠️ **Important:** This is a **research/demo project**. It currently runs in **paper-trading mode only**.  
No real trades are placed unless you explicitly implement and enable a live execution adapter with your own exchange API keys.  

---

## ✨ Features

- **Event-driven multi-agent architecture** (async pub/sub bus)
- **Included agents**:
  - `SentimentAgent` – toy sentiment stream (random sample sentences → simple sentiment score)
  - `TechAgent` – fetches OHLCV candles via [yfinance](https://pypi.org/project/yfinance/), computes SMA, RSI, ATR
  - `RegimeAgent` – classifies current market regime (`trend_up` / `trend_down` / `flat` + vol regime)
  - `StrategyAgent` – simple rule-based signals (long / short / flat)
  - `RiskAgent` – converts signals into position sizes (paper account sizing)
  - `ExecutionAgent` – **paper fills only** (simulated execution)
  - `LLMAnalystAgent` (optional) – scaffolding for LLaMA/OpenAI/Together models
- **Configurable via `.env`** (symbol, timeframe, balance, execution mode, API keys for live trading later)
- **Dev tooling**: pytest, ruff (lint), black (format), pre-commit hooks
- **Docker & docker-compose** support for reproducible runs
- **LLM analyst council** ready to be wired in later

---

## 📂 Project Structure

```
macats/
  __init__.py
  config.py
  event_bus.py
  orchestrator.py
  agents/
    __init__.py
    sentiment_agent.py
    tech_agent.py
    regime_agent.py
    strategy_agent.py
    risk_agent.py
    execution_agent.py
    llm_analyst_agent.py   # optional LLM council
  data/
    __init__.py
    market.py
    sentiment.py
    macro.py
main.py
requirements.txt
requirements-dev.txt
Dockerfile
Dockerfile.playwright
docker-compose.yml
Makefile
.github/workflows/ci.yml
.env.example
```

---

## 🚀 Getting Started

### 1. Clone & install

```bash
git clone <your-repo-url> macats
cd macats
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # then edit values (e.g. SYMBOL, EXECUTION_MODE=paper)
```

### 2. Run locally (paper mode)

```bash
python3 main.py
```

You should see logs like:

```
[strategy.log] {'note': 'Regime=trend_up:low_vol'}
[orders.planned] {'side': 'long', 'qty': 12.0}
[exec.fills] {'status': 'filled', 'side': 'long', 'qty': 12.0}
```

---

## 🐳 Docker

### Build the image
```bash
docker build -t macats:latest .
# or force a clean rebuild
docker build --no-cache -t macats:latest .
```

### Run (normal, baked-in code)
```bash
docker run --rm -it --env-file .env macats:latest
```

### Run (dev mode: mount local code so you don’t need to rebuild on edits)
```bash
docker run --rm -it --env-file .env -v "$(pwd)":/app macats:latest
```

### Docker Compose (dev loop)
```bash
docker compose up --build
# after edits, just rerun:
docker compose up
```

---

## ⚙️ Development

Convenience commands (see `Makefile`):

```bash
make setup    # create venv + install deps + setup pre-commit
make lint     # run ruff
make format   # run black
make test     # run pytest
make run      # run python main.py
```

---

## 🔮 Next Steps

- Integrate a real **LLM analyst** (Ollama / OpenAI / Together.ai).
- Add **real sentiment feeds** (Reddit/Twitter scraping with Playwright, or [CryptoPanic API](https://cryptopanic.com/developers/api/)).
- Extend `ExecutionAgent` into a **portfolio ledger** with PnL tracking.
- Build dashboards (e.g. Streamlit or React + Recharts).
- Implement safe **live trading** via [ccxt](https://github.com/ccxt/ccxt) and testnets before going live.

---

## ⚠️ Safety

This code is **for research/learning only**.  
It is currently in **paper mode** — no live orders are sent.  
If you implement live trading:
- Add strict position/risk limits and a kill switch.
- Use **exchange testnets first**.
- Never trade real money without thorough testing.

---

## 📜 License

MIT
