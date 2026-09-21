from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class TxnIn(BaseModel):
    date: date
    description: str = Field(min_length=2, max_length=200)
    amount: float = Field(gt=0, lt=1e9)
    type: Literal["expense", "income"] = "expense"
    category: Optional[str] = None


class TxnPatch(BaseModel):
    date: Optional[date] = None
    description: Optional[str] = Field(default=None, min_length=2, max_length=200)
    amount: Optional[float] = Field(default=None, gt=0, lt=1e9)
    type: Optional[Literal["expense", "income"]] = None
    category: Optional[str] = None


class BudgetIn(BaseModel):
    category: str
    monthly_limit: float = Field(gt=0, lt=1e9)


class SuggestIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)


class GoalIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    target: float = Field(gt=0, lt=1e10)
    saved: float = Field(default=0, ge=0, lt=1e10)
    deadline: Optional[date] = None
    emoji: str = Field(default="🎯", max_length=8)


class GoalPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    target: Optional[float] = Field(default=None, gt=0, lt=1e10)
    deadline: Optional[date] = None
    emoji: Optional[str] = Field(default=None, max_length=8)


class ContributeIn(BaseModel):
    amount: float = Field(gt=-1e10, lt=1e10)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
