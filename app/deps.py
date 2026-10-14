from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, ModuloLicencia, Usuario
from app.security import comparar_csrf, generar_csrf_token


# ---------------------------------------------------------------
# Utilidades de petición
# ---------------------------------------------------------------
def obtener_ip(request: Request) -> str:
    """IP del cliente. Detrás de Railway, uvicorn se inicia con --proxy-headers
    para que request.client ya contenga la IP real."""
    return request.client.host if request.client else "desconocida"


# ---------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------
def emitir_csrf(request: Request) -> str:
    """Devuelve el token CSRF de la sesión, creándolo si no existe."""
    token = request.session.get("csrf_token")
    if not token:
        token = generar_csrf_token()
        request.session["csrf_token"] = token
    return token


def csrf_obligatorio(request: Request) -> None:
    """Dependencia para todas las peticiones de escritura (POST, PUT, PATCH, DELETE).
    El cliente debe enviar el header X-CSRF-Token obtenido desde GET /auth/csrf."""
    esperado = request.session.get("csrf_token")
    recibido = request.headers.get("x-csrf-token")
    if not comparar_csrf(esperado, recibido):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido o ausente.",
        )


# ---------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------
def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Exige una sesión completa (clave ya resuelta)."""
    no_autenticado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Debes iniciar sesión.",
    )
    uid = request.session.get("user_id")
    if uid is None:
        raise no_autenticado

    usuario = db.get(Usuario, uid)
    # Si el admin reinició la clave, la sesión anterior deja de ser válida
    if usuario is None or not usuario.activo or usuario.requiere_cambio_clave:
        request.session.clear()
        raise no_autenticado
    return usuario


# ---------------------------------------------------------------
# RBAC: permisos por rol (Matriz de Permisos)
# ---------------------------------------------------------------
def requiere_permiso(codigo: str):
    """Fábrica de dependencias: exige que el rol del usuario tenga el permiso indicado."""

    def _dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        codigos = {permiso.codigo for permiso in usuario.rol.permisos}
        if codigo not in codigos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tu rol no tiene el permiso '{codigo}'.",
            )
        return usuario

    return _dependencia


# ---------------------------------------------------------------
# Licenciamiento: feature flags por módulo
# ---------------------------------------------------------------
def requiere_modulo(codigo: str):
    """Fábrica de dependencias: exige que el módulo esté contratado (activo)."""

    def _dependencia(db: Session = Depends(get_db)) -> None:
        modulo = db.scalar(select(ModuloLicencia).where(ModuloLicencia.codigo == codigo))
        if modulo is None or not modulo.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El módulo '{codigo}' no está contratado por el municipio.",
            )

    return _dependencia


# ---------------------------------------------------------------
# Auditoría legal
# ---------------------------------------------------------------
def registrar_auditoria(
    db: Session,
    request: Request,
    usuario_id: int | None,
    accion: str,
    tabla: str,
    registro_id: int | None = None,
) -> None:
    """Agrega un registro a logs_auditoria. No hace commit: lo hace la ruta llamadora,
    así la auditoría se guarda en la misma transacción que la acción."""
    db.add(
        LogAuditoria(
            usuario_id=usuario_id,
            accion_realizada=accion,
            tabla_afectada=tabla,
            registro_id=registro_id,
            direccion_ip=obtener_ip(request),
        )
    )