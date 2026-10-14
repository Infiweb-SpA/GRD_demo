from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.deps import emitir_csrf

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["vistas"])


@router.get("/auth/login", response_class=HTMLResponse)
def vista_login(request: Request) -> HTMLResponse:
    """Portal de autenticación. El token CSRF se incrusta en la plantilla."""
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "app_name": settings.APP_NAME,
            "csrf_token": emitir_csrf(request),
        },
    )