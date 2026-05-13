from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
import jwt, bcrypt, os
from datetime import datetime, timedelta

load_dotenv()

app = FastAPI(title="HiveOS API", version="1.0.0")

cors_origins_raw = os.getenv("CORS_ORIGINS", "").strip()
cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()] if cors_origins_raw else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    # If origins is ["*"], CORS spec forbids credentials; browsers will ignore otherwise.
    allow_credentials=(cors_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

ENV = os.getenv("ENV", "development").lower()
SECRET_KEY = os.getenv("JWT_SECRET")
if ENV == "production" and not SECRET_KEY:
    raise RuntimeError("JWT_SECRET must be set in production")
SECRET_KEY = SECRET_KEY or "change-this-in-production"
security = HTTPBearer()

USERS = {
    "admin": bcrypt.hashpw(b"hiveos2024", bcrypt.gensalt()),
}

def create_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

from routes.auth  import router as auth_router
from routes.gpt   import router as gpt_router
from routes.data  import router as data_router
from routes.hives import router as hives_router

app.include_router(auth_router,  prefix="/api")
app.include_router(gpt_router,   prefix="/api")
app.include_router(data_router,  prefix="/api")
app.include_router(hives_router, prefix="/api")

@app.get("/")
def root():
    return {"status": "HiveOS API running 🐝", "docs": "/docs"}
