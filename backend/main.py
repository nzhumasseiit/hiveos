from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings

app = FastAPI(title="HiveOS API", version="1.0.0")
settings = get_settings()

cors_origins = settings.allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    # If origins is ["*"], CORS spec forbids credentials; browsers will ignore otherwise.
    allow_credentials=(cors_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {"status": "HiveOS API running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "hiveos-api"}


@app.get("/api/health")
def api_health():
    return health()
