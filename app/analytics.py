import numpy as np
import pandas as pd

TD = 252  # trading days / year


# ---------- portfolio ----------
def basket_value(qty: pd.Series, px: pd.DataFrame) -> pd.Series:
    """Value of a constant-share basket over the price window (no cash flows)."""
    px = px[qty.index].ffill().dropna()
    return (px * qty).sum(axis=1)


def performance(value: pd.Series, rf: float = 0.03) -> dict:
    r = value.pct_change().dropna()
    years = max((value.index[-1] - value.index[0]).days / 365.25, 1e-9)
    cagr = (value.iloc[-1] / value.iloc[0]) ** (1 / years) - 1
    vol = r.std() * np.sqrt(TD)
    sharpe = (r.mean() * TD - rf) / vol if vol > 0 else float("nan")
    max_dd = (value / value.cummax() - 1).min()
    return {"cagr": cagr, "volatility": vol, "sharpe": sharpe, "max_drawdown": max_dd, "rf": rf}


def allocation(qty: pd.Series, last_px: pd.Series) -> pd.Series:
    mv = qty * last_px[qty.index]
    return (mv / mv.sum()).sort_values(ascending=False)


def monte_carlo(qty: pd.Series, px: pd.DataFrame, years: int = 5, sims: int = 2000, seed: int | None = None) -> dict:
    """Correlated GBM, monthly steps, buy-and-hold (no rebalancing)."""
    px = px[qty.index].ffill().dropna()
    lr = np.log(px / px.shift(1)).dropna()
    k = 21  # trading days per step
    mu, cov = lr.mean().values * k, lr.cov().values * k
    chol = np.linalg.cholesky(cov + 1e-12 * np.eye(len(mu)))
    steps, n = years * 12, len(mu)
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((sims, steps, n)) @ chol.T
    paths = np.exp(np.cumsum(mu - 0.5 * np.diag(cov) + shocks, axis=1))  # (sims, steps, n)
    v0 = qty * px.iloc[-1]
    port = (paths * v0.values).sum(axis=2)
    port = np.concatenate([np.full((sims, 1), v0.sum()), port], axis=1)
    pct = {p: np.percentile(port, p, axis=0).round(2).tolist() for p in (5, 25, 50, 75, 95)}
    return {
        "start_value": float(v0.sum()),
        "months": list(range(steps + 1)),
        "percentiles": pct,
        "prob_loss": float((port[:, -1] < v0.sum()).mean()),
    }


# ---------- risk profile ----------
def risk_profile(score: int) -> dict:
    """Score = sum of 5 answers, each 1-5 (range 5-25)."""
    if score <= 10:
        return {"profile": "conservative", "target_vol": (0.00, 0.08)}
    if score <= 17:
        return {"profile": "moderate", "target_vol": (0.08, 0.14)}
    return {"profile": "aggressive", "target_vol": (0.14, 0.30)}


# ---------- cash flow ----------
def _monthly(tx: pd.DataFrame) -> pd.DataFrame:
    tx = tx.assign(month=tx["date"].dt.to_period("M"))
    m = tx.pivot_table(index="month", columns="kind", values="amount", aggfunc="sum", fill_value=0.0)
    for k in ("income", "expense"):
        if k not in m:
            m[k] = 0.0
    m = m.reindex(pd.period_range(m.index.min(), m.index.max(), freq="M"), fill_value=0.0)
    m["net"] = m["income"] - m["expense"]
    return m


def monthly_report(tx: pd.DataFrame, month: str) -> dict:
    p = pd.Period(month, "M")
    t = tx[tx["date"].dt.to_period("M") == p]
    inc = float(t.loc[t.kind == "income", "amount"].sum())
    exp = float(t.loc[t.kind == "expense", "amount"].sum())
    cats = t[t.kind == "expense"].groupby("category")["amount"].sum().sort_values(ascending=False)
    return {
        "month": month, "income": inc, "expense": exp, "net": inc - exp,
        "savings_rate": (inc - exp) / inc if inc else None,
        "expense_by_category": cats.round(2).to_dict(),
    }


def forecast_cashflow(tx: pd.DataFrame, months: int = 6, opening_balance: float = 0.0) -> list[dict]:
    """Linear trend on last 12 months (mean if <4 months of history)."""
    hist = _monthly(tx).tail(12)
    x, fx = np.arange(len(hist)), np.arange(len(hist), len(hist) + months)
    pred = {}
    for k in ("income", "expense"):
        if len(hist) >= 4:
            slope, icpt = np.polyfit(x, hist[k].values, 1)
            pred[k] = np.clip(icpt + slope * fx, 0, None)
        else:
            pred[k] = np.full(months, hist[k].mean())
    start = hist.index[-1] + 1
    bal, out = opening_balance + float(hist["net"].sum()), []
    for i in range(months):
        net = pred["income"][i] - pred["expense"][i]
        bal += net
        out.append({"month": str(start + i), "income": round(float(pred["income"][i]), 2),
                    "expense": round(float(pred["expense"][i]), 2), "net": round(float(net), 2),
                    "balance": round(bal, 2)})
    return out


def tx_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame([{"date": r.date, "kind": r.kind, "category": r.category, "amount": float(r.amount)} for r in rows])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df
