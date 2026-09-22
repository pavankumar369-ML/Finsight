import os
from datetime import datetime
from sqlalchemy import (create_engine, Column, Integer, String, Float, Boolean, Date,
                        DateTime, ForeignKey, Text, UniqueConstraint)
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = os.getenv("DATABASE_URL") or os.getenv("FINSIGHT_DB", "sqlite:///./finsight.db")
if DB_URL.startswith("postgres://"):          # Render/Neon/Heroku style URLs
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)
if DB_URL.startswith("sqlite"):
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    # connect_timeout: fail fast (10s) instead of hanging indefinitely if the database is unreachable --
    # a silent hang here previously looked identical to a slow-starting app and caused Render's deploy
    # to time out with no error message at all.
    # NOTE: don't add "options": "-c statement_timeout=..." here -- Neon's pooled (PgBouncer)
    # connection endpoint (hostname contains "-pooler") rejects that startup parameter outright.
    engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=280,
                           connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True, index=True)
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)


class LoginEvent(Base):
    __tablename__ = "login_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, index=True)
    method = Column(String(12))          # password | register | demo


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
    import_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True, index=True)   # which file it came from


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    filename = Column(String(200))
    file_type = Column(String(10))
    imported = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    category = Column(String(40), nullable=False)
    monthly_limit = Column(Float, nullable=False)


class Goal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(60), nullable=False)
    target = Column(Float, nullable=False)
    saved = Column(Float, default=0)
    deadline = Column(Date, nullable=True)
    emoji = Column(String(8), default="🎯")
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    role = Column(String(10), nullable=False)       # user | assistant
    content = Column(Text, nullable=False)
    mode = Column(String(20), nullable=True)        # llm | offline
    ms = Column(Float, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow)


class AnalyticsCache(Base):
    """Persisted results of expensive per-user computations (forecasts, ML insights), keyed by a
    fingerprint of the user's transactions. Survives server restarts, so a cold free-tier server
    can serve the dashboard without re-importing statsmodels/scikit-learn or re-fitting models."""
    __tablename__ = "analytics_cache"
    __table_args__ = (UniqueConstraint("user_id", "key"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    key = Column(String(80), nullable=False)
    fingerprint = Column(String(40), nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    _add_missing_columns()


def _add_missing_columns():
    """create_all() never alters existing tables, so older databases get new columns added here."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
