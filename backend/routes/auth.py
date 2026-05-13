from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from security import create_token, verify_admin_password


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    if not verify_admin_password(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {"token": create_token(body.username), "username": get_settings().admin_username}
