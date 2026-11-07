import os
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config("FinTrack", layout="wide")
S = st.session_state


def call(method, path, **kw):
    headers = {"Authorization": f"Bearer {S['token']}"} if S.get("token") else {}
    r = requests.request(method, API + path, headers=headers, timeout=120, **kw)
    if not r.ok:
        st.error(r.json().get("detail", r.text)); return None
    return r.json() if r.content else True


# ---------- auth ----------
with st.sidebar:
    st.title("FinTrack")
    if not S.get("token"):
        email, pw = st.text_input("Email"), st.text_input("Password", type="password")
        c1, c2 = st.columns(2)
        if c1.button("Login"):
            r = requests.post(f"{API}/auth/token", data={"username": email, "password": pw}, timeout=30)
            if r.ok: S["token"] = r.json()["access_token"]; st.rerun()
            else: st.error("Bad credentials")
        if c2.button("Register"):
            r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw}, timeout=30)
            st.success("Registered, now log in") if r.ok else st.error(r.text)
    elif st.button("Logout"):
        S.clear(); st.rerun()
if not S.get("token"):
    st.stop()

t_tx, t_rep, t_port, t_mc, t_risk = st.tabs(["Transactions", "Reports & forecast", "Portfolio", "Monte Carlo", "Risk profile"])

# ---------- transactions ----------
with t_tx:
    with st.form("tx"):
        c = st.columns(5)
        d, k = c[0].date_input("Date", date.today()), c[1].selectbox("Kind", ["expense", "income"])
        cat, amt, note = c[2].text_input("Category"), c[3].number_input("Amount", 0.01, step=1.0), c[4].text_input("Note")
        if st.form_submit_button("Add") and cat:
            call("POST", "/transactions", json={"date": str(d), "kind": k, "category": cat, "amount": amt, "note": note})
    if (tx := call("GET", "/transactions")):
        st.dataframe(pd.DataFrame(tx), use_container_width=True, hide_index=True)

# ---------- reports ----------
with t_rep:
    month = st.text_input("Month (YYYY-MM)", date.today().strftime("%Y-%m"))
    if (rep := call("GET", "/reports/monthly", params={"month": month})):
        c = st.columns(4)
        c[0].metric("Income", f"{rep['income']:,.2f}"); c[1].metric("Expense", f"{rep['expense']:,.2f}")
        c[2].metric("Net", f"{rep['net']:,.2f}")
        c[3].metric("Savings rate", "n/a" if rep["savings_rate"] is None else f"{rep['savings_rate']:.1%}")
        if rep["expense_by_category"]:
            cats = pd.Series(rep["expense_by_category"]).reset_index()
            cats.columns = ["category", "amount"]
            st.plotly_chart(px.pie(cats, names="category", values="amount", title="Expenses by category"), use_container_width=True)
    n = st.slider("Forecast months", 1, 24, 6)
    if (fc := call("GET", "/forecast", params={"months": n})):
        f = pd.DataFrame(fc)
        fig = go.Figure([go.Bar(x=f.month, y=f.income, name="Income"), go.Bar(x=f.month, y=f.expense, name="Expense"),
                         go.Scatter(x=f.month, y=f.balance, name="Cumulative balance", mode="lines+markers")])
        st.plotly_chart(fig.update_layout(title="Cash flow forecast", barmode="group"), use_container_width=True)

# ---------- portfolio ----------
with t_port:
    with st.form("h"):
        c = st.columns(4)
        tk, q = c[0].text_input("Ticker (AAPL, D05.SI)"), c[1].number_input("Quantity", 0.0001, value=1.0)
        cost, pd_ = c[2].number_input("Cost/share", 0.0001, value=1.0), c[3].date_input("Purchase date", date.today())
        if st.form_submit_button("Add holding") and tk:
            call("POST", "/holdings", json={"ticker": tk, "quantity": q, "cost_per_share": cost, "purchase_date": str(pd_)})
    if (s := call("GET", "/portfolio/summary")):
        c = st.columns(3)
        c[0].metric("Market value", f"{s['market_value']:,.2f}")
        c[1].metric("P&L", f"{s['pnl']:,.2f}", f"{s['return_pct']:.2%}")
        al = pd.Series(s["allocation"]).reset_index(); al.columns = ["ticker", "weight"]
        st.plotly_chart(px.pie(al, names="ticker", values="weight", hole=0.4, title="Asset allocation"), use_container_width=True)
        days = st.select_slider("Window (days)", [90, 180, 365, 730, 1095], 365)
        if (m := call("GET", "/portfolio/metrics", params={"days": days})):
            c = st.columns(4)
            c[0].metric("CAGR", f"{m['cagr']:.2%}"); c[1].metric("Volatility", f"{m['volatility']:.2%}")
            c[2].metric("Sharpe", f"{m['sharpe']:.2f}"); c[3].metric("Max drawdown", f"{m['max_drawdown']:.2%}")
            st.plotly_chart(px.line(x=m["series"]["dates"], y=m["series"]["values"], labels={"x": "", "y": "Value"},
                                    title="Basket value"), use_container_width=True)

# ---------- Monte Carlo ----------
with t_mc:
    yrs, sims = st.slider("Years", 1, 30, 5), st.select_slider("Simulations", [500, 1000, 2000, 5000], 2000)
    if st.button("Run simulation") and (r := call("POST", "/portfolio/monte-carlo", params={"years": yrs, "sims": sims})):
        fig = go.Figure()
        for p, col in ((5, "#d62728"), (25, "#ff9896"), (50, "#1f77b4"), (75, "#98df8a"), (95, "#2ca02c")):
            fig.add_scatter(x=r["months"], y=r["percentiles"][str(p)], name=f"P{p}", line={"color": col})
        st.plotly_chart(fig.update_layout(xaxis_title="Months", yaxis_title="Portfolio value"), use_container_width=True)
        st.metric("Probability of loss at horizon", f"{r['prob_loss']:.1%}")

# ---------- risk ----------
with t_risk:
    qs = ["Investment horizon (1=<1y … 5=>15y)", "Reaction to a 20% drop (1=sell all … 5=buy more)",
          "Income stability (1=unstable … 5=very stable)", "Investing experience (1=none … 5=expert)",
          "Return goal (1=capital preservation … 5=max growth)"]
    ans = [st.slider(q, 1, 5, 3) for q in qs]
    if st.button("Save profile") and (p := call("POST", "/risk-profile", json={"answers": ans})):
        lo, hi = p["target_vol"]
        st.success(f"{p['profile'].title()} (score {p['score']}); target volatility {lo:.0%}–{hi:.0%}")
