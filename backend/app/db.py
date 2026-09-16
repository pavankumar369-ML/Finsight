import os
from datetime import datetime
from sqlalchemy import (create_engine, Column, Integer, String, Float, Boolean, Date,
                        DateTime, ForeignKey, Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = os.getenv("FINSIGHT_DB", "sqlite:///./finsight.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    description = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)          # always positive
    type = Column(String(10), nullable=False)       # "expense" | "income"
    category = Column(String(40), nullable=False)
    confidence = Column(Float, default=1.0)
    source = Column(String(10), default="manual")   # manual | csv | seed
    user_corrected = Column(Boolean, default=False)
    is_anomaly = Column(Boolean, default=False)
    anomaly_reason = Column(String(160), nullable=True)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    category = Column(String(40), nullable=False)
    monthly_limit = Column(Float, nullable=False)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    method = Column(String(8))
    path = Column(String(120), index=True)
    status = Column(Integer)
    ms = Column(Float)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.utcnow)
    trigger = Column(String(20))          # startup | retrain
    n_train = Column(Integer)
    n_test = Column(Integer)
    n_corrections = Column(Integer, default=0)
    accuracy = Column(Float)
    f1_macro = Column(Float)
    train_ms = Column(Float)
    details = Column(Text)                # json: per-class f1, confusion matrix, labels


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
