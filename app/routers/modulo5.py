# app/routers/modulo5.py
"""
Módulo 5 — Albergues y Logística.

Dos sub-módulos:
  A) Catastro de albergues: dónde puede refugiarse la población y con qué
     servicios cuenta. Vínculo OPCIONAL a una zona de riesgo del M3 (D4).
  B) Inventario de recursos logísticos: una sola tabla con discriminador
     `categoria` (maquinaria | abrigo | alimento) — decisión D3 — y asignación
     opcional a un albergue. Vínculo OPCIONAL a un incidente del M2 (D4).
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import (
    csrf_obligatorio,
    emitir_csrf,
    get_current_user_html,
    registrar_auditoria,
    requiere_modulo,
    requiere_permiso,
    usuario_actual,
)
from app.models import Albergue, Incidente, RecursoInventario, Usuario, ZonaRiesgo
from app.services.modulo3_engine import COMUNAS_COORDS

router = APIRouter(tags=["Módulo 5 — Albergues y Logística"])
templates = Jinja2Templates(directory="app/templates")

ALBERGUE_ESTADOS = ["activo", "mantencion", "inactivo"]
RECURSO_CATEGORIAS = ["maquinaria", "abrigo", "alimento"]
RECURSO_ESTADOS = ["disponible", "asignado", "mantencion"]

CAMPOS_SRV = (
    "srv_agua_potable", "srv_electricidad", "srv_sanitarios",
    "srv_cocina", "srv_internet",
)


# ---------------------------------------------------------------------------
# Bodies (Pydantic)
# ---------------------------------------------------------------------------
class CrearAlbergueBody(BaseModel):
    nombre: str
    comuna: str
    direccion: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    capacidad: int = Field(0, ge=0)
    estado: str = "activo"
    srv_agua_potable: bool = False
    srv_electricidad: bool = False
    srv_sanitarios: bool = False
    srv_cocina: bool = False
    srv_internet: bool = False
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None
    zona_riesgo_id: Optional[int] = None


class EditarAlbergueBody(BaseModel):
    nombre: Optional[str] = None
    comuna: Optional[str] = None
    direccion: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    capacidad: Optional[int] = Field(None, ge=0)
    estado: Optional[str] = None
    srv_agua_potable: Optional[bool] = None
    srv_electricidad: Optional[bool] = None
    srv_sanitarios: Optional[bool] = None
    srv_cocina: Optional[bool] = None
    srv_internet: Optional[bool] = None
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None
    zona_riesgo_id: Optional[int] = None


class CrearRecursoBody(BaseModel):
    nombre: str
    categoria: str
    comuna: str
    cantidad: int = Field(0, ge=0)
    unidad: str = "unidades"
    estado: str = "disponible"
    albergue_id: Optional[int] = None
    incidente_id: Optional[int] = None
    notas: Optional[str] = None


class EditarRecursoBody(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    comuna: Optional[str] = None
    cantidad: Optional[int] = Field(None, ge=0)
    unidad: Optional[str] = None
    estado: Optional[str] = None
    albergue_id: Optional[int] = None
    incidente_id: Optional[int] = None
    notas: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalizar_estado_recurso(estado: str, albergue_id: Optional[int]) -> str:
    """Mantiene coherencia entre la asignación y el estado.

    Si hay albergue destino pero el estado es 'disponible', pasa a 'asignado'.
    Si no hay albergue y el estado era 'asignado', vuelve a 'disponible'.
    """
    if albergue_id is not None and estado == "disponible":
        return "asignado"
    if albergue_id is None and estado == "asignado":
        return "disponible"
    return estado


def _serializar_albergue(a: Albergue, n_recursos: int = 0) -> dict:
    return {
        "id": a.id,
        "nombre": a.nombre,
        "comuna": a.comuna,
        "direccion": a.direccion,
        "lat": a.lat,
        "lon": a.lon,
        "capacidad": a.capacidad,
        "estado": a.estado,
        "srv_agua_potable": a.srv_agua_potable,
        "srv_electricidad": a.srv_electricidad,
        "srv_sanitarios": a.srv_sanitarios,
        "srv_cocina": a.srv_cocina,
        "srv_internet": a.srv_internet,
        "contacto_nombre": a.contacto_nombre,
        "contacto_telefono": a.contacto_telefono,
        "zona_riesgo_id": a.zona_riesgo_id,
        "recursos_asignados": n_recursos,
        "creado_en": a.creado_en.isoformat() if a.creado_en else None,
        "activo": a.activo,
    }


def _serializar_recurso(r: RecursoInventario) -> dict:
    return {
        "id": r.id,
        "nombre": r.nombre,
        "categoria": r.categoria,
        "cantidad": r.cantidad,
        "unidad": r.unidad,
        "estado": r.estado,
        "comuna": r.comuna,
        "albergue_id": r.albergue_id,
        "incidente_id": r.incidente_id,
        "notas": r.notas,
        "creado_en": r.creado_en.isoformat() if r.creado_en else None,
        "activo": r.activo,
    }


def _validar_albergue(nombre: str, comuna: str, estado: str) -> None:
    if not nombre or not nombre.strip():
        raise HTTPException(400, "El nombre del albergue es obligatorio")
    if not comuna or not comuna.strip():
        raise HTTPException(400, "La comuna es obligatoria")
    if estado not in ALBERGUE_ESTADOS:
        raise HTTPException(400, f"Estado de albergue inválido: {estado}")


def _validar_recurso(nombre: str, comuna: str, categoria: str, estado: str) -> None:
    if not nombre or not nombre.strip():
        raise HTTPException(400, "El nombre del recurso es obligatorio")
    if not comuna or not comuna.strip():
        raise HTTPException(400, "La comuna es obligatoria")
    if categoria not in RECURSO_CATEGORIAS:
        raise HTTPException(400, f"Categoría inválida: {categoria}")
    if estado not in RECURSO_ESTADOS:
        raise HTTPException(400, f"Estado de recurso inválido: {estado}")


# ---------------------------------------------------------------------------
# Vistas HTML
# ---------------------------------------------------------------------------
@router.get(
    "/modulo5/albergues",
    response_class=HTMLResponse,
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:leer")),
    ],
)
def vista_albergues(
    request: Request,
    user: Usuario = Depends(get_current_user_html),
):
    return templates.TemplateResponse(
        request,
        "modulo5/albergues.html",
        {
            "app_name": settings.APP_NAME,
            "user": user,
            "csrf_token": emitir_csrf(request),
            "comunas": list(COMUNAS_COORDS.keys()),
            "estados": ALBERGUE_ESTADOS,
        },
    )


@router.get(
    "/modulo5/recursos",
    response_class=HTMLResponse,
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:leer")),
    ],
)
def vista_recursos(
    request: Request,
    user: Usuario = Depends(get_current_user_html),
):
    return templates.TemplateResponse(
        request,
        "modulo5/recursos.html",
        {
            "app_name": settings.APP_NAME,
            "user": user,
            "csrf_token": emitir_csrf(request),
            "comunas": list(COMUNAS_COORDS.keys()),
            "categorias": RECURSO_CATEGORIAS,
            "estados": RECURSO_ESTADOS,
        },
    )


# ---------------------------------------------------------------------------
# API: albergues
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo5/albergues",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:leer")),
    ],
)
def api_listar_albergues(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
    solo_activos: bool = True,
):
    q = db.query(Albergue)
    if comuna:
        q = q.filter(Albergue.comuna == comuna)
    if solo_activos:
        q = q.filter(Albergue.activo.is_(True))  # noqa: E712
    albergues = q.order_by(Albergue.comuna, Albergue.nombre).all()

    conteo: dict[int, int] = {}
    for r in db.query(RecursoInventario).filter(
        RecursoInventario.activo.is_(True),  # noqa: E712
        RecursoInventario.albergue_id.isnot(None),
    ).all():
        conteo[r.albergue_id] = conteo.get(r.albergue_id, 0) + 1

    return {"albergues": [_serializar_albergue(a, conteo.get(a.id, 0)) for a in albergues]}


@router.post(
    "/api/modulo5/albergues",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:escribir")),
    ],
)
def api_crear_albergue(
    body: CrearAlbergueBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    _validar_albergue(body.nombre, body.comuna, body.estado)
    if body.zona_riesgo_id is not None and db.get(ZonaRiesgo, body.zona_riesgo_id) is None:
        raise HTTPException(404, "Zona de riesgo vinculada no encontrada")

    nuevo = Albergue(
        nombre=body.nombre.strip(),
        comuna=body.comuna.strip(),
        direccion=body.direccion,
        lat=body.lat,
        lon=body.lon,
        capacidad=body.capacidad,
        estado=body.estado,
        srv_agua_potable=body.srv_agua_potable,
        srv_electricidad=body.srv_electricidad,
        srv_sanitarios=body.srv_sanitarios,
        srv_cocina=body.srv_cocina,
        srv_internet=body.srv_internet,
        contacto_nombre=body.contacto_nombre,
        contacto_telefono=body.contacto_telefono,
        zona_riesgo_id=body.zona_riesgo_id,
        creado_por_id=user.id,
        activo=True,
    )
    db.add(nuevo)
    db.flush()

    registrar_auditoria(
        db, request, user.id,
        f"Creó albergue #{nuevo.id} - {nuevo.nombre} ({nuevo.comuna})",
        "albergues", nuevo.id,
    )
    db.commit()
    db.refresh(nuevo)
    return {"estado": "ok", "albergue_id": nuevo.id}


@router.put(
    "/api/modulo5/albergues/{albergue_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:escribir")),
    ],
)
def api_editar_albergue(
    albergue_id: int,
    body: EditarAlbergueBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    alb = db.get(Albergue, albergue_id)
    if alb is None or not alb.activo:
        raise HTTPException(404, "Albergue no encontrado")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"estado": "sin_cambios", "cambios": []}

    if "nombre" in data and not (data["nombre"] or "").strip():
        raise HTTPException(400, "El nombre del albergue es obligatorio")
    if "comuna" in data and not (data["comuna"] or "").strip():
        raise HTTPException(400, "La comuna es obligatoria")
    if "estado" in data and data["estado"] not in ALBERGUE_ESTADOS:
        raise HTTPException(400, f"Estado de albergue inválido: {data['estado']}")
    if "zona_riesgo_id" in data and data["zona_riesgo_id"] is not None \
            and db.get(ZonaRiesgo, data["zona_riesgo_id"]) is None:
        raise HTTPException(404, "Zona de riesgo vinculada no encontrada")

    cambios: list[str] = []
    for campo, valor in data.items():
        if valor != getattr(alb, campo):
            cambios.append(campo)
            setattr(alb, campo, valor)

    if not cambios:
        return {"estado": "sin_cambios", "cambios": []}

    registrar_auditoria(
        db, request, user.id,
        f"Modificó albergue #{alb.id} ({', '.join(cambios)})",
        "albergues", alb.id,
    )
    db.commit()
    return {"estado": "ok", "albergue_id": alb.id, "cambios": cambios}


@router.delete(
    "/api/modulo5/albergues/{albergue_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:escribir")),
    ],
)
def api_eliminar_albergue(
    albergue_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    alb = db.get(Albergue, albergue_id)
    if alb is None or not alb.activo:
        raise HTTPException(404, "Albergue no encontrado")

    alb.activo = False
    registrar_auditoria(
        db, request, user.id,
        f"Eliminó albergue #{alb.id} - {alb.nombre}",
        "albergues", alb.id,
    )
    db.commit()
    return {"estado": "ok"}


@router.get(
    "/api/modulo5/zonas-disponibles",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("albergues:leer")),
    ],
)
def api_zonas_disponibles(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
):
    """Zonas de riesgo activas para el vínculo opcional del albergue (D4)."""
    q = db.query(ZonaRiesgo).filter(ZonaRiesgo.activa.is_(True))  # noqa: E712
    if comuna:
        q = q.filter(ZonaRiesgo.comuna == comuna)
    zonas = q.order_by(ZonaRiesgo.comuna, ZonaRiesgo.nombre).all()
    return {
        "zonas": [
            {"id": z.id, "nombre": z.nombre, "comuna": z.comuna, "severidad": z.severidad}
            for z in zonas
        ]
    }


# ---------------------------------------------------------------------------
# API: recursos (D3: tabla única con discriminador de categoría)
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo5/recursos",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:leer")),
    ],
)
def api_listar_recursos(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
    categoria: Optional[str] = None,
    estado: Optional[str] = None,
    solo_activos: bool = True,
):
    q = db.query(RecursoInventario)
    if comuna:
        q = q.filter(RecursoInventario.comuna == comuna)
    if categoria:
        q = q.filter(RecursoInventario.categoria == categoria)
    if estado:
        q = q.filter(RecursoInventario.estado == estado)
    if solo_activos:
        q = q.filter(RecursoInventario.activo.is_(True))  # noqa: E712
    recursos = q.order_by(
        RecursoInventario.categoria, RecursoInventario.nombre
    ).all()
    return {"recursos": [_serializar_recurso(r) for r in recursos]}


@router.get(
    "/api/modulo5/inventario-resumen",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:leer")),
    ],
)
def api_inventario_resumen(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
):
    q = db.query(RecursoInventario).filter(RecursoInventario.activo.is_(True))  # noqa: E712
    if comuna:
        q = q.filter(RecursoInventario.comuna == comuna)
    recursos = q.all()

    por_categoria: dict[str, dict] = {}
    for cat in RECURSO_CATEGORIAS:
        items = [r for r in recursos if r.categoria == cat]
        por_categoria[cat] = {
            "items": len(items),
            "cantidad_total": sum(r.cantidad for r in items),
            "asignados": sum(1 for r in items if r.estado == "asignado"),
            "disponibles": sum(1 for r in items if r.estado == "disponible"),
            "mantencion": sum(1 for r in items if r.estado == "mantencion"),
        }

    return {
        "comuna": comuna,
        "total_items": len(recursos),
        "por_categoria": por_categoria,
    }


@router.post(
    "/api/modulo5/recursos",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:escribir")),
    ],
)
def api_crear_recurso(
    body: CrearRecursoBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    _validar_recurso(body.nombre, body.comuna, body.categoria, body.estado)
    if body.albergue_id is not None:
        alb = db.get(Albergue, body.albergue_id)
        if alb is None or not alb.activo:
            raise HTTPException(404, "Albergue destino no encontrado")
    if body.incidente_id is not None:
        inc = db.get(Incidente, body.incidente_id)
        if inc is None or inc.eliminado:
            raise HTTPException(404, "Incidente vinculado no encontrado")

    nuevo = RecursoInventario(
        nombre=body.nombre.strip(),
        categoria=body.categoria,
        comuna=body.comuna.strip(),
        cantidad=body.cantidad,
        unidad=body.unidad or "unidades",
        estado=_normalizar_estado_recurso(body.estado, body.albergue_id),
        albergue_id=body.albergue_id,
        incidente_id=body.incidente_id,
        notas=body.notas,
        creado_por_id=user.id,
        activo=True,
    )
    db.add(nuevo)
    db.flush()

    registrar_auditoria(
        db, request, user.id,
        f"Creó recurso #{nuevo.id} - {nuevo.nombre} [{nuevo.categoria}] ({nuevo.comuna})",
        "recursos_inventario", nuevo.id,
    )
    db.commit()
    db.refresh(nuevo)
    return {"estado": "ok", "recurso_id": nuevo.id}


@router.put(
    "/api/modulo5/recursos/{recurso_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:escribir")),
    ],
)
def api_editar_recurso(
    recurso_id: int,
    body: EditarRecursoBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    rec = db.get(RecursoInventario, recurso_id)
    if rec is None or not rec.activo:
        raise HTTPException(404, "Recurso no encontrado")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"estado": "sin_cambios", "cambios": []}

    if "nombre" in data and not (data["nombre"] or "").strip():
        raise HTTPException(400, "El nombre del recurso es obligatorio")
    if "comuna" in data and not (data["comuna"] or "").strip():
        raise HTTPException(400, "La comuna es obligatoria")
    if "categoria" in data and data["categoria"] not in RECURSO_CATEGORIAS:
        raise HTTPException(400, f"Categoría inválida: {data['categoria']}")
    if "estado" in data and data["estado"] not in RECURSO_ESTADOS:
        raise HTTPException(400, f"Estado de recurso inválido: {data['estado']}")
    if "albergue_id" in data and data["albergue_id"] is not None:
        alb = db.get(Albergue, data["albergue_id"])
        if alb is None or not alb.activo:
            raise HTTPException(404, "Albergue destino no encontrado")
    if "incidente_id" in data and data["incidente_id"] is not None:
        inc = db.get(Incidente, data["incidente_id"])
        if inc is None or inc.eliminado:
            raise HTTPException(404, "Incidente vinculado no encontrado")

    cambios: list[str] = []
    for campo, valor in data.items():
        if campo == "estado":
            continue  # se normaliza al final con la asignación
        if valor != getattr(rec, campo):
            cambios.append(campo)
            setattr(rec, campo, valor)

    # Recalcula estado coherente con la asignación (asignado <-> disponible),
    # respetando 'mantencion' si se pidió explícitamente.
    estado_pedido = data.get("estado", rec.estado)
    estado_final = _normalizar_estado_recurso(estado_pedido, rec.albergue_id)
    if estado_final != rec.estado:
        cambios.append("estado")
        rec.estado = estado_final

    if not cambios:
        return {"estado": "sin_cambios", "cambios": []}

    registrar_auditoria(
        db, request, user.id,
        f"Modificó recurso #{rec.id} ({', '.join(cambios)})",
        "recursos_inventario", rec.id,
    )
    db.commit()
    return {"estado": "ok", "recurso_id": rec.id, "cambios": cambios}


@router.delete(
    "/api/modulo5/recursos/{recurso_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:escribir")),
    ],
)
def api_eliminar_recurso(
    recurso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    rec = db.get(RecursoInventario, recurso_id)
    if rec is None or not rec.activo:
        raise HTTPException(404, "Recurso no encontrado")

    rec.activo = False
    registrar_auditoria(
        db, request, user.id,
        f"Eliminó recurso #{rec.id} - {rec.nombre}",
        "recursos_inventario", rec.id,
    )
    db.commit()
    return {"estado": "ok"}


@router.get(
    "/api/modulo5/incidentes-disponibles",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:leer")),
    ],
)
def api_incidentes_disponibles(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    """Incidentes vigentes del M2 para el vínculo opcional del recurso (D4)."""
    incidentes = (
        db.query(Incidente)
        .filter(Incidente.eliminado.is_(False))  # noqa: E712
        .order_by(Incidente.fecha_creacion.desc())
        .all()
    )
    return {
        "incidentes": [
            {
                "id": i.id,
                "amenaza_tipo": i.amenaza_tipo,
                "comentario": i.comentario,
                "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
            }
            for i in incidentes
        ]
    }


# ---------------------------------------------------------------------------
# API: consolidado logístico (albergue -> recursos asignados)
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo5/logistica",
    dependencies=[
        Depends(requiere_modulo("modulo_5")),
        Depends(requiere_permiso("recursos:leer")),
    ],
)
def api_logistica(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
):
    """Cruza albergues activos con los recursos asignados a cada uno."""
    q_alb = db.query(Albergue).filter(Albergue.activo.is_(True))  # noqa: E712
    if comuna:
        q_alb = q_alb.filter(Albergue.comuna == comuna)
    albergues = q_alb.order_by(Albergue.comuna, Albergue.nombre).all()

    q_rec = db.query(RecursoInventario).filter(
        RecursoInventario.activo.is_(True),  # noqa: E712
        RecursoInventario.albergue_id.isnot(None),
    )
    if comuna:
        q_rec = q_rec.filter(RecursoInventario.comuna == comuna)
    recursos = q_rec.all()

    por_albergue: dict[int, list[RecursoInventario]] = {}
    for r in recursos:
        por_albergue.setdefault(r.albergue_id, []).append(r)

    detalle = []
    for a in albergues:
        asignados = por_albergue.get(a.id, [])
        detalle.append({
            "albergue_id": a.id,
            "nombre": a.nombre,
            "comuna": a.comuna,
            "capacidad": a.capacidad,
            "estado": a.estado,
            "recursos": [
                {
                    "id": r.id,
                    "nombre": r.nombre,
                    "categoria": r.categoria,
                    "cantidad": r.cantidad,
                    "unidad": r.unidad,
                }
                for r in asignados
            ],
            "total_recursos": len(asignados),
            "por_categoria": {
                cat: sum(r.cantidad for r in asignados if r.categoria == cat)
                for cat in RECURSO_CATEGORIAS
            },
        })

    return {
        "comuna": comuna,
        "albergues": detalle,
        "resumen": {
            "albergues_activos": len(albergues),
            "capacidad_total": sum(a.capacidad for a in albergues),
            "recursos_asignados": len(recursos),
        },
    }
