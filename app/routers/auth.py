from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import (
    csrf_obligatorio,
    emitir_csrf,
    registrar_auditoria,
    requiere_permiso,
    usuario_actual,
)
from app.models import Usuario
from app.security import (
    generar_clave_temporal,
    hash_password,
    validar_fortaleza_clave,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["autenticación"])


# ---------------------------------------------------------------
# Esquemas de entrada
# ---------------------------------------------------------------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


class ResolverClaveIn(BaseModel):
    accion: Literal["cambiar", "mantener"]
    nueva_clave: str | None = Field(default=None, max_length=72)
    confirmar_clave: str | None = Field(default=None, max_length=72)


class ResetClaveIn(BaseModel):
    comuna: str | None = Field(default=None, max_length=60)


# ---------------------------------------------------------------
# Helpers de sesión
# ---------------------------------------------------------------
def _establecer_sesion(
    request: Request,
    usuario_id: int | None = None,
    pendiente_id: int | None = None,
) -> str:
    """Limpia la sesión (evita session fixation), fija el estado y rota el CSRF.
    Devuelve el nuevo token CSRF para el cliente."""
    request.session.clear()
    if usuario_id is not None:
        request.session["user_id"] = usuario_id
    if pendiente_id is not None:
        request.session["pendiente_id"] = pendiente_id
    return emitir_csrf(request)


def _resumen_usuario(usuario: Usuario) -> dict:
    return {
        "id": usuario.id,
        "username": usuario.username,
        "rol": usuario.rol.nombre,
        "permisos": sorted(p.codigo for p in usuario.rol.permisos),
    }


# ---------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------
@router.get("/csrf")
def obtener_csrf(request: Request) -> dict:
    """Entrega el token CSRF de la sesión. Debe llamarse antes de cualquier escritura."""
    return {"csrf_token": emitir_csrf(request)}


@router.post("/login", dependencies=[Depends(csrf_obligatorio)])
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    usuario = db.scalar(select(Usuario).where(Usuario.username == datos.username.strip()))
    if usuario is None or not usuario.activo or not verify_password(
        datos.password, usuario.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    # Primer ingreso con clave temporal: el usuario debe decidir antes de tener sesión completa
    if usuario.requiere_cambio_clave:
        token = _establecer_sesion(request, pendiente_id=usuario.id)
        return {
            "estado": "cambio_clave_requerido",
            "mensaje": "Debes cambiar tu contraseña o mantener la clave actual.",
            "opciones": ["cambiar", "mantener"],
            "csrf_token": token,
        }

    token = _establecer_sesion(request, usuario_id=usuario.id)
    registrar_auditoria(db, request, usuario.id, "Inició sesión", "usuarios", usuario.id)
    db.commit()
    return {"estado": "ok", "usuario": _resumen_usuario(usuario), "csrf_token": token}


@router.post("/clave/resolver", dependencies=[Depends(csrf_obligatorio)])
def resolver_clave(
    datos: ResolverClaveIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Resuelve el cambio de clave obligatorio: 'cambiar' o 'mantener' la temporal."""
    pendiente_id = request.session.get("pendiente_id")
    if pendiente_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No hay un cambio de clave pendiente.",
        )

    usuario = db.get(Usuario, pendiente_id)
    if usuario is None or not usuario.activo or not usuario.requiere_cambio_clave:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No hay un cambio de clave pendiente.",
        )

    if datos.accion == "cambiar":
        nueva = datos.nueva_clave or ""
        if nueva != (datos.confirmar_clave or ""):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Las claves no coinciden.")

        errores = validar_fortaleza_clave(nueva)
        if errores:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, " ".join(errores))

        if verify_password(nueva, usuario.password_hash):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "La nueva clave no puede ser igual a la temporal.",
            )

        usuario.password_hash = hash_password(nueva)
        accion_txt = "Cambió su contraseña en el primer inicio de sesión"
    else:
        accion_txt = "Mantuvo la clave temporal en el primer inicio de sesión"

    usuario.requiere_cambio_clave = False
    token = _establecer_sesion(request, usuario_id=usuario.id)
    registrar_auditoria(db, request, usuario.id, accion_txt, "usuarios", usuario.id)
    db.commit()
    return {"estado": "ok", "usuario": _resumen_usuario(usuario), "csrf_token": token}


@router.post("/logout", dependencies=[Depends(csrf_obligatorio)])
def logout(request: Request) -> dict:
    request.session.clear()
    return {"estado": "sesion_cerrada"}


@router.get("/me")
def me(usuario: Usuario = Depends(usuario_actual)) -> dict:
    return _resumen_usuario(usuario)


@router.post("/usuarios/{usuario_id}/reset-clave", dependencies=[Depends(csrf_obligatorio)])
def reset_clave(
    usuario_id: int,
    datos: ResetClaveIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_permiso("usuarios:gestionar")),
) -> dict:
    """Genera una clave temporal legible para un funcionario. Se muestra UNA sola vez."""
    objetivo = db.get(Usuario, usuario_id)
    if objetivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")

    if objetivo.rol.nombre == "superadmin" and actor.rol.nombre != "superadmin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes reiniciar la clave del superadmin.")

    clave = generar_clave_temporal(datos.comuna)
    objetivo.password_hash = hash_password(clave)
    objetivo.requiere_cambio_clave = True

    registrar_auditoria(
        db, request, actor.id,
        f"Reinició contraseña de {objetivo.username}",
        "usuarios", objetivo.id,
    )
    db.commit()
    return {
        "usuario": objetivo.username,
        "clave_temporal": clave,
        "aviso": "Entrégala por canal interno. Deberá cambiarla al ingresar.",
    }