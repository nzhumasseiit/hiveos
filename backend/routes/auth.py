from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import bcrypt
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from main import USERS, create_token  # noqa: E402


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    stored = USERS.get(body.username)
    if not stored:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    stored_hash = stored.encode() if isinstance(stored, str) else stored
    if not bcrypt.checkpw(body.password.encode(), stored_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"token": create_token(body.username), "username": body.username}
