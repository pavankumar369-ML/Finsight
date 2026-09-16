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
