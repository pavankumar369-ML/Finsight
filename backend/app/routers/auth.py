from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db, User
from ..auth import hash_password, verify_password, create_token, current_user
from ..schemas import RegisterIn, LoginIn
from ..seed import ensure_demo

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(user):
    return {"token": create_token(user.id), "user": {"id": user.id, "name": user.name, "email": user.email}}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return _out(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return _out(user)


@router.post("/demo")
def demo(db: Session = Depends(get_db)):
    return _out(ensure_demo(db))


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}
