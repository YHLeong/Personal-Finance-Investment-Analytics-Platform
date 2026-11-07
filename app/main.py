from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import analytics as an, market
from .db import Base, engine, get_db
from .models import Holding, Transaction, User
from .security import current_user, hash_pw, make_token, verify_pw


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # use Alembic migrations in production
    yield


app = FastAPI(title="FinTrack", lifespan=lifespan)
DB = Annotated[Session, Depends(get_db)]
Me = Annotated[User, Depends(current_user)]


# ---------- schemas ----------
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TxIn(BaseModel):
    date: date
    kind: Literal["income", "expense"]
    category: str = Field(max_length=50)
    amount: float = Field(gt=0)
    note: str = ""


class HoldingIn(BaseModel):
    ticker: str = Field(max_length=20)
    quantity: float = Field(gt=0)
    cost_per_share: float = Field(gt=0)
    purchase_date: date


class RiskIn(BaseModel):
    answers: list[Annotated[int, Field(ge=1, le=5)]] = Field(min_length=5, max_length=5)


# ---------- auth ----------
@app.post("/auth/register", status_code=201)
def register(c: Credentials, db: DB):
    db.add(User(email=c.email.lower(), password_hash=hash_pw(c.password)))
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "Email already registered")
    return {"status": "ok"}


@app.post("/auth/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    u = db.scalar(select(User).where(User.email == form.username.lower()))
    if not u or not verify_pw(form.password, u.password_hash):
        raise HTTPException(401, "Bad credentials")
    return {"access_token": make_token(u.id), "token_type": "bearer"}


# ---------- transactions ----------
@app.post("/transactions", status_code=201)
def add_tx(t: TxIn, me: Me, db: DB):
    row = Transaction(user_id=me.id, **t.model_dump())
    db.add(row); db.commit()
    return {"id": row.id}


@app.get("/transactions")
def list_tx(me: Me, db: DB, limit: int = Query(200, le=1000)):
    rows = db.scalars(select(Transaction).where(Transaction.user_id == me.id)
                      .order_by(Transaction.date.desc()).limit(limit)).all()
    return [{"id": r.id, "date": r.date, "kind": r.kind, "category": r.category,
             "amount": float(r.amount), "note": r.note} for r in rows]


@app.delete("/transactions/{tx_id}", status_code=204)
def del_tx(tx_id: int, me: Me, db: DB):
    r = db.get(Transaction, tx_id)
    if not r or r.user_id != me.id:
        raise HTTPException(404)
    db.delete(r); db.commit()


def _tx_df(me: User, db: Session) -> pd.DataFrame:
    df = an.tx_frame(db.scalars(select(Transaction).where(Transaction.user_id == me.id)).all())
    if df.empty:
        raise HTTPException(404, "No transactions yet")
    return df


@app.get("/reports/monthly")
def report(me: Me, db: DB, month: str = Query(pattern=r"^\d{4}-\d{2}$")):
    return an.monthly_report(_tx_df(me, db), month)


@app.get("/forecast")
def forecast(me: Me, db: DB, months: int = Query(6, ge=1, le=24)):
    return an.forecast_cashflow(_tx_df(me, db), months)


# ---------- holdings & portfolio ----------
@app.post("/holdings", status_code=201)
def add_holding(h: HoldingIn, me: Me, db: DB):
    row = Holding(user_id=me.id, **{**h.model_dump(), "ticker": h.ticker.upper()})
    db.add(row); db.commit()
    return {"id": row.id}


@app.get("/holdings")
def list_holdings(me: Me, db: DB):
    return [{"id": h.id, "ticker": h.ticker, "quantity": float(h.quantity),
             "cost_per_share": float(h.cost_per_share), "purchase_date": h.purchase_date}
            for h in db.scalars(select(Holding).where(Holding.user_id == me.id))]


@app.delete("/holdings/{hid}", status_code=204)
def del_holding(hid: int, me: Me, db: DB):
    h = db.get(Holding, hid)
    if not h or h.user_id != me.id:
        raise HTTPException(404)
    db.delete(h); db.commit()


def _qty_prices(me: User, db: Session, lookback_days: int):
    rows = db.scalars(select(Holding).where(Holding.user_id == me.id)).all()
    if not rows:
        raise HTTPException(404, "No holdings yet")
    qty = pd.Series({}, dtype=float)
    for h in rows:
        qty[h.ticker] = qty.get(h.ticker, 0.0) + float(h.quantity)
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    try:
        px = market.prices(list(qty.index), start)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return rows, qty, px


@app.get("/portfolio/summary")
def summary(me: Me, db: DB):
    rows, qty, px = _qty_prices(me, db, 10)
    last = px.ffill().iloc[-1]
    cost = sum(float(h.quantity * h.cost_per_share) for h in rows)
    value = float((qty * last[qty.index]).sum())
    return {"market_value": value, "cost_basis": cost, "pnl": value - cost,
            "return_pct": value / cost - 1,
            "allocation": an.allocation(qty, last).round(4).to_dict(),
            "positions": {t: {"quantity": q, "price": float(last[t]), "value": float(q * last[t])} for t, q in qty.items()}}


@app.get("/portfolio/metrics")
def metrics(me: Me, db: DB, days: int = Query(365, ge=60, le=3650), rf: float = 0.03):
    _, qty, px = _qty_prices(me, db, days)
    value = an.basket_value(qty, px)
    return {**an.performance(value, rf), "window_days": days,
            "series": {"dates": [d.strftime("%Y-%m-%d") for d in value.index], "values": value.round(2).tolist()},
            "note": "Constant-share basket of current holdings over the window."}


@app.post("/portfolio/monte-carlo")
def mc(me: Me, db: DB, years: int = Query(5, ge=1, le=30), sims: int = Query(2000, ge=100, le=10000)):
    _, qty, px = _qty_prices(me, db, 365 * 3)
    return an.monte_carlo(qty, px, years, sims)


# ---------- risk ----------
@app.post("/risk-profile")
def set_risk(r: RiskIn, me: Me, db: DB):
    me.risk_score = sum(r.answers); db.commit()
    return an.risk_profile(me.risk_score) | {"score": me.risk_score}


@app.get("/risk-profile")
def get_risk(me: Me):
    if me.risk_score is None:
        raise HTTPException(404, "Not assessed")
    return an.risk_profile(me.risk_score) | {"score": me.risk_score}
