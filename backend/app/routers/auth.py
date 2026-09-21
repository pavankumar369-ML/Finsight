from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import get_db, User, LoginEvent
from ..auth import hash_password, verify_password, create_token, current_user, is_admin
from ..schemas import RegisterIn, LoginIn, PasswordChangeIn
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


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..seed import DEMO_EMAIL
    if user.email == DEMO_EMAIL:
        raise HTTPException(403, "The demo account is shared, so its password can't be changed. Create your own account.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a new password that's different from the current one.")
    user.password_hash = hash_password(body.new_password)
    db.commit()


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "is_admin": is_admin(user)}
