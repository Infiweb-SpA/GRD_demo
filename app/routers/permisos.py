from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import (
    csrf_obligatorio,
    emitir_csrf,
    get_current_superadmin_html,
    registrar_auditoria,
    requiere_superadmin,
)
from app.models import Permiso, Rol, Usuario
from app.security import generar_clave_temporal, hash_password

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(prefix="/admin", tags=["súper administrador"])

ROL_PROTEGIDO = "superadmin"


# ============================================================
#  Esquemas
# ============================================================
class RolIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=50)
    descripcion: str | None = Field(default=None, max_length=255)
    permisos: list[str] = Field(default_factory=list)


class UsuarioIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    role_id: int
    comuna: str | None = Field(default=None, max_length=60)


class UsuarioUpdateIn(BaseModel):
    role_id: int | None = None
    activo: bool | None = None


# ============================================================
#  Vista HTML
# ============================================================
@router.get("", response_class=HTMLResponse)
def vista_admin(
    request: Request,
    usuario: Usuario = Depends(get_current_superadmin_html),
):
    return templates.TemplateResponse(
        request,
        "permisos/index.html",
        {
            "app_name": settings.APP_NAME,
            "usuario": usuario,
            "csrf_token": emitir_csrf(request),
        },
    )


# ============================================================
#  Roles
# ============================================================
@router.get("/roles")
def listar_roles(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_superadmin),
):
    roles = db.query(Rol).order_by(Rol.nombre).all()
    return {
        "roles": [
            {
                "id": r.id,
                "nombre": r.nombre,
                "descripcion": r.descripcion or "",
                "protegido": r.nombre == ROL_PROTEGIDO,
                "permisos": sorted(p.codigo for p in r.permisos),
                "num_usuarios": len(r.usuarios),
            }
            for r in roles
        ]
    }


@router.get("/permisos-disponibles")
def listar_permisos(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_superadmin),
):
    permisos = db.query(Permiso).order_by(Permiso.codigo).all()
    return {
        "permisos": [
            {"id": p.id, "codigo": p.codigo, "descripcion": p.descripcion or ""}
            for p in permisos
        ]
    }


@router.post("/roles", dependencies=[Depends(csrf_obligatorio)])
def crear_rol(
    datos: RolIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    nombre = datos.nombre.strip().lower().replace(" ", "_")
    if not nombre:
        raise HTTPException(400, "El nombre del rol no puede estar vacío.")
    if db.scalar(select(Rol).where(Rol.nombre == nombre)):
        raise HTTPException(409, f"Ya existe un rol llamado '{nombre}'.")

    permisos = db.scalars(
        select(Permiso).where(Permiso.codigo.in_(datos.permisos))
    ).all()
    faltantes = set(datos.permisos) - {p.codigo for p in permisos}
    if faltantes:
        raise HTTPException(400, f"Permisos inválidos: {', '.join(sorted(faltantes))}")

    rol = Rol(nombre=nombre, descripcion=datos.descripcion or "")
    rol.permisos = list(permisos)
    db.add(rol)
    db.flush()

    registrar_auditoria(
        db, request, actor.id,
        f"Creó rol '{nombre}' con {len(permisos)} permiso(s)",
        "roles", rol.id,
    )
    db.commit()
    return {"estado": "ok", "rol_id": rol.id}


@router.put("/roles/{rol_id}", dependencies=[Depends(csrf_obligatorio)])
def actualizar_rol(
    rol_id: int,
    datos: RolIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(404, "Rol no encontrado.")

    cambios: list[str] = []

    nuevo_nombre = datos.nombre.strip().lower().replace(" ", "_")
    if rol.nombre == ROL_PROTEGIDO:
        if nuevo_nombre != ROL_PROTEGIDO:
            raise HTTPException(400, "El rol 'superadmin' no puede renombrarse.")
    elif nuevo_nombre != rol.nombre:
        if db.scalar(select(Rol).where(Rol.nombre == nuevo_nombre, Rol.id != rol_id)):
            raise HTTPException(409, f"Ya existe un rol llamado '{nuevo_nombre}'.")
        cambios.append(f"nombre {rol.nombre} → {nuevo_nombre}")
        rol.nombre = nuevo_nombre

    if datos.descripcion is not None and datos.descripcion != (rol.descripcion or ""):
        cambios.append("descripción")
        rol.descripcion = datos.descripcion

    # El rol superadmin siempre conserva TODOS los permisos
    if rol.nombre == ROL_PROTEGIDO:
        rol.permisos = db.query(Permiso).all()
    else:
        nuevos = db.scalars(
            select(Permiso).where(Permiso.codigo.in_(datos.permisos))
        ).all()
        actuales = {p.codigo for p in rol.permisos}
        nuevos_cod = {p.codigo for p in nuevos}
        if actuales != nuevos_cod:
            agregados = nuevos_cod - actuales
            quitados = actuales - nuevos_cod
            if agregados:
                cambios.append(f"+{len(agregados)} permiso(s)")
            if quitados:
                cambios.append(f"-{len(quitados)} permiso(s)")
            rol.permisos = list(nuevos)

    if not cambios:
        return {"estado": "sin_cambios"}

    registrar_auditoria(
        db, request, actor.id,
        f"Modificó rol '{rol.nombre}' ({'; '.join(cambios)})",
        "roles", rol.id,
    )
    db.commit()
    return {"estado": "ok"}


@router.delete("/roles/{rol_id}", dependencies=[Depends(csrf_obligatorio)])
def eliminar_rol(
    rol_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    rol = db.get(Rol, rol_id)
    if rol is None:
        raise HTTPException(404, "Rol no encontrado.")
    if rol.nombre == ROL_PROTEGIDO:
        raise HTTPException(400, "El rol 'superadmin' no puede eliminarse.")
    if rol.usuarios:
        raise HTTPException(
            409,
            f"No se puede eliminar: hay {len(rol.usuarios)} usuario(s) con este rol.",
        )

    nombre = rol.nombre
    db.delete(rol)
    registrar_auditoria(
        db, request, actor.id, f"Eliminó rol '{nombre}'", "roles", rol_id
    )
    db.commit()
    return {"estado": "ok"}


# ============================================================
#  Usuarios
# ============================================================
@router.get("/usuarios")
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_superadmin),
):
    usuarios = db.query(Usuario).order_by(Usuario.username).all()
    return {
        "usuarios": [
            {
                "id": u.id,
                "username": u.username,
                "rol": u.rol.nombre,
                "role_id": u.role_id,
                "activo": u.activo,
                "requiere_cambio_clave": u.requiere_cambio_clave,
                "creado_en": u.creado_en.isoformat() if u.creado_en else None,
            }
            for u in usuarios
        ]
    }


@router.post("/usuarios", dependencies=[Depends(csrf_obligatorio)])
def crear_usuario(
    datos: UsuarioIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    username = datos.username.strip()
    if not username:
        raise HTTPException(400, "El nombre de usuario no puede estar vacío.")
    if db.scalar(select(Usuario).where(Usuario.username == username)):
        raise HTTPException(409, f"Ya existe el usuario '{username}'.")

    rol = db.get(Rol, datos.role_id)
    if rol is None:
        raise HTTPException(404, "Rol no encontrado.")

    clave = generar_clave_temporal(datos.comuna)
    usuario = Usuario(
        username=username,
        password_hash=hash_password(clave),
        rol=rol,
        requiere_cambio_clave=True,
        activo=True,
    )
    db.add(usuario)
    db.flush()

    registrar_auditoria(
        db, request, actor.id,
        f"Creó usuario '{username}' con rol '{rol.nombre}'",
        "usuarios", usuario.id,
    )
    db.commit()
    return {
        "estado": "ok",
        "usuario_id": usuario.id,
        "username": username,
        "clave_temporal": clave,
        "aviso": "Entrégala por canal interno. Deberá cambiarla al ingresar.",
    }


@router.put("/usuarios/{usuario_id}", dependencies=[Depends(csrf_obligatorio)])
def actualizar_usuario(
    usuario_id: int,
    datos: UsuarioUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado.")

    cambios: list[str] = []

    # Cambio de rol
    if datos.role_id is not None and datos.role_id != usuario.role_id:
        if usuario.id == actor.id and usuario.rol.nombre == ROL_PROTEGIDO:
            raise HTTPException(400, "No puedes cambiar tu propio rol de superadmin.")

        nuevo_rol = db.get(Rol, datos.role_id)
        if nuevo_rol is None:
            raise HTTPException(404, "Rol no encontrado.")

        # Si es el último superadmin, no permitir degradarlo
        if usuario.rol.nombre == ROL_PROTEGIDO and nuevo_rol.nombre != ROL_PROTEGIDO:
            total = db.scalar(
                select(func.count()).select_from(Usuario)
                .join(Rol).where(Rol.nombre == ROL_PROTEGIDO)
            )
            if total <= 1:
                raise HTTPException(400, "Debe existir al menos un superadministrador.")

        cambios.append(f"rol {usuario.rol.nombre} → {nuevo_rol.nombre}")
        usuario.role_id = nuevo_rol.id

    # Cambio de estado activo
    if datos.activo is not None and datos.activo != usuario.activo:
        if usuario.id == actor.id and not datos.activo:
            raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
        cambios.append(f"activo {usuario.activo} → {datos.activo}")
        usuario.activo = datos.activo

    if not cambios:
        return {"estado": "sin_cambios"}

    registrar_auditoria(
        db, request, actor.id,
        f"Modificó usuario '{usuario.username}' ({'; '.join(cambios)})",
        "usuarios", usuario.id,
    )
    db.commit()
    return {"estado": "ok"}


@router.delete("/usuarios/{usuario_id}", dependencies=[Depends(csrf_obligatorio)])
def eliminar_usuario(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado.")
    if usuario.id == actor.id:
        raise HTTPException(400, "No puedes eliminar tu propia cuenta.")
    if usuario.rol.nombre == ROL_PROTEGIDO:
        total = db.scalar(
            select(func.count()).select_from(Usuario)
            .join(Rol).where(Rol.nombre == ROL_PROTEGIDO)
        )
        if total <= 1:
            raise HTTPException(400, "No puedes eliminar al último superadministrador.")

    usuario.activo = False
    usuario.requiere_cambio_clave = True

    registrar_auditoria(
        db, request, actor.id,
        f"Desactivó usuario '{usuario.username}'",
        "usuarios", usuario.id,
    )
    db.commit()
    return {"estado": "ok"}


@router.post("/usuarios/{usuario_id}/reset-clave", dependencies=[Depends(csrf_obligatorio)])
def reset_clave_usuario(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(requiere_superadmin),
):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado.")

    clave = generar_clave_temporal()
    usuario.password_hash = hash_password(clave)
    usuario.requiere_cambio_clave = True

    registrar_auditoria(
        db, request, actor.id,
        f"Reinició contraseña de '{usuario.username}'",
        "usuarios", usuario.id,
    )
    db.commit()
    return {
        "username": usuario.username,
        "clave_temporal": clave,
        "aviso": "Entrégala por canal interno. Deberá cambiarla al ingresar.",
    }