# FinTrack: Personal Finance & Investment Analytics

A full-stack, Python-only application for tracking income and spending, managing an investment portfolio, and analysing risk and return. It combines a REST API, a relational data model and quantitative finance methods (CAGR, volatility, Sharpe ratio, Monte Carlo simulation) behind an interactive dashboard.

<!-- Add 2-3 screenshots or a short GIF here: docs/dashboard.png, docs/montecarlo.png -->

## Features

**Personal finance**
- Registration and JWT authentication (bcrypt password hashing)
- Income and expense tracking with categories
- Monthly report: income, expenses, net, savings rate, spending by category
- Cash-flow forecast: trend-based projection of income, expenses and running balance

**Investments**
- Holdings management with cost basis and purchase date
- Market prices via `yfinance` (delayed; cached for 15 minutes)
- Portfolio summary: market value, P&L, return, asset allocation
- Performance metrics: CAGR, annualised volatility, Sharpe ratio, maximum drawdown
- Monte Carlo simulation of future portfolio value (5th to 95th percentile fan chart, probability of loss)
- Risk profiling questionnaire mapped to a target volatility band

## Architecture

```mermaid
flowchart LR
    UI[Streamlit + Plotly] -->|HTTPS / JSON + JWT| API[FastAPI]
    API --> DB[(PostgreSQL)]
    API --> AN[analytics.py<br/>pandas / numpy]
    API --> MKT[market.py<br/>yfinance + cache]
```

| Path | Responsibility |
|---|---|
| `app/main.py` | Routes, request validation (Pydantic), dependency injection |
| `app/analytics.py` | Pure functions: no I/O, so they are easy to unit test |
| `app/market.py` | Market data access with a TTL cache; swap the provider here |
| `app/security.py` | Password hashing, token issue and verification |
| `app/models.py`, `app/db.py` | SQLAlchemy 2.0 models and session management |
| `ui/dashboard.py` | Streamlit client that talks to the API only |
| `tests/` | Unit tests for the quantitative code |

## Methodology

| Metric | Definition |
|---|---|
| CAGR | `(V_end / V_start)^(1 / years) - 1` |
| Volatility | `std(daily returns) * sqrt(252)` |
| Sharpe ratio | `(mean daily return * 252 - rf) / volatility`, default `rf = 3%` |
| Max drawdown | `min(V_t / max(V_0..V_t) - 1)` |
| Monte Carlo | Correlated geometric Brownian motion: drift and covariance estimated from 3 years of daily log returns, shocks correlated via the Cholesky factor, `-0.5 * sigma^2` drift correction, monthly steps, buy-and-hold |
| Cash-flow forecast | Least-squares linear trend over the last 12 months per series, clipped at zero. Falls back to the mean with fewer than 4 months of data |
| Risk profile | Five questions scored 1 to 5, summed and mapped to conservative / moderate / aggressive |

## Design decisions

- **Analytics separated from the web layer.** Finance logic is pure and deterministic (seedable), so it can be tested without a database or network.
- **`Numeric(14, 2)` for money in the database,** converted to floats only for analytics.
- **Monthly Monte Carlo steps.** A daily simulation of 2,000 paths over 5 years across 10 assets needs hundreds of MB; monthly steps need a few MB with the same terminal distribution under GBM.
- **Ownership checks on every row.** Queries and deletes are scoped to the authenticated user.

## Getting started

### Docker (PostgreSQL)

```bash
docker compose up --build
```

API docs: http://localhost:8000/docs, UI: http://localhost:8501

### Local (Windows PowerShell, SQLite, no Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./fin.db"
python -m uvicorn app.main:app --reload
```

In a second terminal (venv activated):

```powershell
python -m streamlit run ui/dashboard.py
```

On macOS/Linux, activate with `source .venv/bin/activate` and set variables with `export`.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://fin:fin@localhost:5432/fin` | SQLAlchemy connection string |
| `SECRET_KEY` | `dev-only-secret` | JWT signing key. **Change in production** |
| `API_URL` | `http://localhost:8000` | API base URL used by the UI |

### Tests

```bash
pytest tests
```

## API overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register`, `/auth/token` | Create account, obtain JWT |
| GET / POST / DELETE | `/transactions` | Manage income and expenses |
| GET | `/reports/monthly?month=YYYY-MM` | Monthly summary |
| GET | `/forecast?months=6` | Cash-flow projection |
| GET / POST / DELETE | `/holdings` | Manage positions |
| GET | `/portfolio/summary` | Value, P&L, allocation |
| GET | `/portfolio/metrics?days=365` | CAGR, volatility, Sharpe, drawdown, value series |
| POST | `/portfolio/monte-carlo?years=5&sims=2000` | Simulation percentiles and loss probability |
| GET / POST | `/risk-profile` | Questionnaire result |

Interactive documentation is generated at `/docs`.

## Limitations

- Portfolio metrics use a **constant-share basket of current holdings**, not a money-weighted or time-weighted return that accounts for when each purchase was made.
- Market data comes from `yfinance`, which is unofficial and delayed. Singapore tickers use the `.SI` suffix (e.g. `D05.SI`).
- The Monte Carlo model assumes log-normal returns with constant parameters estimated from history. It does not capture fat tails, regime shifts or rebalancing, and is an illustration, not a prediction.
- The forecast is a linear trend, with no seasonality or one-off events.
- Schema is created with `create_all`; there are no migrations yet.
- Tests cover the analytics module; API and integration tests are not yet written.
- Not financial advice.

## Roadmap

- [ ] Trades ledger (buy/sell) and time-weighted / money-weighted returns
- [ ] Per-category budgets with overspend alerts
- [ ] Alembic migrations
- [ ] API integration tests (pytest + httpx) and CI via GitHub Actions
- [ ] Multi-currency support (SGD base) with FX conversion
- [ ] Efficient frontier / mean-variance optimisation, VaR and CVaR
- [ ] Rate limiting, refresh tokens, cloud deployment

## Tech stack

Python 3.11+, FastAPI, SQLAlchemy 2.0, PostgreSQL, pandas, NumPy, yfinance, Streamlit, Plotly, PyJWT, bcrypt, Docker Compose, pytest.
