import numpy as np, pandas as pd
from app import analytics as an


def _px(n=800, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n))) for t in ("A", "B")}, index=idx)


def test_performance_and_mc():
    px, qty = _px(), pd.Series({"A": 10.0, "B": 5.0})
    perf = an.performance(an.basket_value(qty, px))
    assert perf["volatility"] > 0 and perf["max_drawdown"] <= 0
    mc = an.monte_carlo(qty, px, years=2, sims=300, seed=0)
    assert len(mc["months"]) == 25 and 0 <= mc["prob_loss"] <= 1
    assert mc["percentiles"][5][-1] < mc["percentiles"][95][-1]


def test_forecast_shape():
    d = pd.date_range("2025-01-15", periods=8, freq="MS")
    tx = pd.concat([pd.DataFrame({"date": d, "kind": "income", "category": "pay", "amount": 5000.0}),
                    pd.DataFrame({"date": d, "kind": "expense", "category": "rent", "amount": 2000.0})])
    out = an.forecast_cashflow(tx, 3)
    assert len(out) == 3 and out[0]["net"] > 0
