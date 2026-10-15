from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import emitir_csrf, get_current_user_html
from app.models import ModuloLicencia, Usuario

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["vistas"])


def _destino_segun_permisos(usuario: Usuario) -> str:
    """Duplicado deliberado de auth._destino_segun_permisos para evitar
    dependencia circular entre routers."""
    return "/dashboard"

@router.get("/")
def raiz():
    """La raíz redirige al dashboard. Si el usuario no tiene sesión,
    /dashboard lo expulsará automáticamente al login (esa lógica ya existe)."""
    return RedirectResponse("/modulo1/landing", status_code=303)

@router.get("/auth/login", response_class=HTMLResponse)
def vista_login(request: Request, db: Session = Depends(get_db)):
    """Portal de autenticación.

    Si ya hay sesión activa, expulsa al usuario al destino correcto en vez
    de renderizar el formulario.
    """
    # 1) ¿Cambio de clave pendiente?
    pendiente_id = request.session.get("pendiente_id")
    if pendiente_id is not None:
        usuario = db.get(Usuario, pendiente_id)
        if usuario is not None and usuario.activo and usuario.requiere_cambio_clave:
            return RedirectResponse("/auth/clave/resolver", status_code=303)
        request.session.clear()

    # 2) ¿Sesión completa?
    user_id = request.session.get("user_id")
    if user_id is not None:
        usuario = db.get(Usuario, user_id)
        if (
            usuario is not None
            and usuario.activo
            and not usuario.requiere_cambio_clave
        ):
            return RedirectResponse(
                _destino_segun_permisos(usuario), status_code=303
            )
        request.session.clear()

    # 3) Sin sesión → formulario
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"app_name": settings.APP_NAME, "csrf_token": emitir_csrf(request)},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def vista_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user_html),
):
    """Panel operativo con sidebar de módulos filtrados por permiso y licencia."""
    modulos_db = {m.codigo: m for m in db.query(ModuloLicencia).all()}
    codigos_perm = {p.codigo for p in usuario.rol.permisos}

    def _bloque(codigo, nombre, descripcion, url, permiso, icono):
        m = modulos_db.get(codigo)
        return {
            "codigo": codigo,
            "nombre": nombre,
            "descripcion": descripcion,
            "url": url,
            "activo": bool(m and m.activo),
            "permitido": permiso in codigos_perm,
            "icono": icono,
        }

    modulos = [
        _bloque("modulo_2", "Registro de Incidentes",
                "Levantamiento en terreno y trazabilidad",
                "/modulo2/reportes", "reportes:leer", "📋"),
        _bloque("modulo_3", "Zonas de Riesgo",
                "Inteligencia predictiva",
                "/modulo3/zonas", "riesgo:generar", "⚠️"),
        _bloque("modulo_4", "Vulnerabilidad",
                "Análisis socioeconómico",
                "/modulo4/vulnerabilidad", "vulnerabilidad:consultar", "📊"),
    ]

    return templates.TemplateResponse(
    request,
    "dashboard.html",
    {
        "app_name": settings.APP_NAME,
        "usuario": usuario,
        "modulos": modulos,
        "csrf_token": emitir_csrf(request),
        "es_superadmin": usuario.rol.nombre == "superadmin",   # ← nueva línea
    },
)