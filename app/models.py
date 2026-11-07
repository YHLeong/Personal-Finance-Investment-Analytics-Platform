from datetime import date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    risk_score: Mapped[int | None] = mapped_column(Integer, default=None)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(7))  # income | expense
    category: Mapped[str] = mapped_column(String(50))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # always positive
    note: Mapped[str] = mapped_column(String(255), default="")


class Holding(Base):
    __tablename__ = "holdings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))  # e.g. AAPL, D05.SI
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cost_per_share: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    purchase_date: Mapped[date] = mapped_column(Date)
