from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import SessionLocal, init_db
from app.routers import auth
from app.seed import seed_inicial
from app.routers import auth, vistas,modulo1

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Al arrancar: crea tablas y carga datos base (idempotente)
    if settings.ENVIRONMENT == "production" and settings.SECRET_KEY.startswith("cambiar"):
        raise RuntimeError("En producción debes definir SECRET_KEY por variable de entorno.")

    init_db()
    with SessionLocal() as db:
        seed_inicial(db)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    max_age=settings.SESSION_MAX_AGE,
    same_site="strict",
    https_only=settings.ENVIRONMENT == "production",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(vistas.router)
app.include_router(modulo1.router)

@app.get("/api/salud", tags=["sistema"])
def salud() -> dict:
    return {"estado": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}