from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import get_db, User, LoginEvent
from ..auth import hash_password, verify_password, create_token, current_user, is_admin
from ..schemas import RegisterIn, LoginIn
from ..seed import ensure_demo

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _record(db, user, method):
    now = datetime.utcnow()
    user.last_login = now
    user.last_seen = now
    user.login_count = (user.login_count or 0) + 1
    db.add(LoginEvent(user_id=user.id, ts=now, method=method))
    db.commit()


def _out(user):
    return {"token": create_token(user.id), "user": {"id": user.id, "name": user.name, "email": user.email, "is_admin": is_admin(user)}}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    _record(db, user, "register")
    return _out(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    _record(db, user, "password")
    return _out(user)


@router.post("/demo")
def demo(db: Session = Depends(get_db)):
    user = ensure_demo(db)
    _record(db, user, "demo")
    return _out(user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "is_admin": is_admin(user)}
