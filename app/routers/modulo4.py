# app/routers/modulo4.py
"""
Módulo 4 — Análisis de Vulnerabilidad y Evaluación de Daños (EDAN).

Dos sub-módulos:
  A) Análisis de vulnerabilidad: cruce datos censales × zonas de riesgo (M3).
  B) Ficha EDAN: formulario SENAPRED de daños, vinculado a la geometría del
     Módulo 2 de forma híbrida (FK incidente_id + snapshot geojson — decisión D2).
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
from app.models import DatoCensal, FichaEDAN, Incidente, Usuario
from app.services.modulo3_engine import COMUNAS_COORDS
from app.services.modulo4_engine import calcular_vulnerabilidad

router = APIRouter(tags=["Módulo 4 — Vulnerabilidad y EDAN"])
templates = Jinja2Templates(directory="app/templates")

DANIO_VIVIENDA_TIPOS = ["Sin daño", "Daño leve", "Daño medio", "Daño total"]
ESTADOS_EDAN = ["borrador", "enviada"]

CAMPOS_ENTERO = (
    "viviendas_evaluadas", "viviendas_danadas", "viviendas_destruidas",
    "personas_afectadas", "personas_damnificadas", "personas_desaparecidas",
    "personas_fallecidas",
)
CAMPOS_BOOL = (
    "nec_agua_potable", "nec_alimentacion", "nec_habitacion",
    "nec_asistencia_medica", "nec_servicio_sanitario",
)
CAMPOS_TEXTO = ("sector", "otras_necesidades")


# ---------------------------------------------------------------------------
# Bodies (Pydantic)
# ---------------------------------------------------------------------------
class CrearEDANBody(BaseModel):
    comuna: str
    sector: Optional[str] = None
    estado: str = "borrador"
    danio_vivienda_tipo: str = "Sin daño"
    geojson_geometria: Optional[dict] = None
    incidente_id: Optional[int] = None
    viviendas_evaluadas: int = Field(0, ge=0)
    viviendas_danadas: int = Field(0, ge=0)
    viviendas_destruidas: int = Field(0, ge=0)
    personas_afectadas: int = Field(0, ge=0)
    personas_damnificadas: int = Field(0, ge=0)
    personas_desaparecidas: int = Field(0, ge=0)
    personas_fallecidas: int = Field(0, ge=0)
    nec_agua_potable: bool = False
    nec_alimentacion: bool = False
    nec_habitacion: bool = False
    nec_asistencia_medica: bool = False
    nec_servicio_sanitario: bool = False
    otras_necesidades: Optional[str] = None


class EditarEDANBody(BaseModel):
    comuna: Optional[str] = None
    sector: Optional[str] = None
    estado: Optional[str] = None
    danio_vivienda_tipo: Optional[str] = None
    geojson_geometria: Optional[dict] = None
    incidente_id: Optional[int] = None
    viviendas_evaluadas: Optional[int] = Field(None, ge=0)
    viviendas_danadas: Optional[int] = Field(None, ge=0)
    viviendas_destruidas: Optional[int] = Field(None, ge=0)
    personas_afectadas: Optional[int] = Field(None, ge=0)
    personas_damnificadas: Optional[int] = Field(None, ge=0)
    personas_desaparecidas: Optional[int] = Field(None, ge=0)
    personas_fallecidas: Optional[int] = Field(None, ge=0)
    nec_agua_potable: Optional[bool] = None
    nec_alimentacion: Optional[bool] = None
    nec_habitacion: Optional[bool] = None
    nec_asistencia_medica: Optional[bool] = None
    nec_servicio_sanitario: Optional[bool] = None
    otras_necesidades: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _geojson(edan: FichaEDAN) -> Optional[dict]:
    if not edan.geojson_geometria:
        return None
    try:
        return json.loads(edan.geojson_geometria)
    except (TypeError, ValueError):
        return None


def _serializar_edan(e: FichaEDAN) -> dict:
    return {
        "id": e.id,
        "comuna": e.comuna,
        "sector": e.sector,
        "estado": e.estado,
        "incidente_id": e.incidente_id,
        "geojson_geometria": _geojson(e),
        "danio_vivienda_tipo": e.danio_vivienda_tipo,
        "viviendas_evaluadas": e.viviendas_evaluadas,
        "viviendas_danadas": e.viviendas_danadas,
        "viviendas_destruidas": e.viviendas_destruidas,
        "personas_afectadas": e.personas_afectadas,
        "personas_damnificadas": e.personas_damnificadas,
        "personas_desaparecidas": e.personas_desaparecidas,
        "personas_fallecidas": e.personas_fallecidas,
        "nec_agua_potable": e.nec_agua_potable,
        "nec_alimentacion": e.nec_alimentacion,
        "nec_habitacion": e.nec_habitacion,
        "nec_asistencia_medica": e.nec_asistencia_medica,
        "nec_servicio_sanitario": e.nec_servicio_sanitario,
        "otras_necesidades": e.otras_necesidades,
        "creado_por": e.creado_por_id,
        "creado_en": e.creado_en.isoformat() if e.creado_en else None,
        "activo": e.activo,
    }


def _resolver_geometria(db: Session, incidente_id: Optional[int], geojson: Optional[dict]) -> Optional[str]:
    """Decisión D2 (híbrido): prioriza el snapshot entregado; si se referencia un
    incidente de M2 y no viene geometría, copia la de éste como respaldo."""
    if geojson is not None:
        return json.dumps(geojson)
    if incidente_id is not None:
        inc = db.get(Incidente, incidente_id)
        if inc is None or inc.eliminado:
            raise HTTPException(404, "Incidente vinculado no encontrado")
        if inc.geojson_geometria:
            return inc.geojson_geometria  # ya es str
    return None


def _validar_edan(comuna: str, estado: str, danio: str) -> None:
    if not comuna or not comuna.strip():
        raise HTTPException(400, "La comuna es obligatoria")
    if estado not in ESTADOS_EDAN:
        raise HTTPException(400, f"Estado inválido: {estado}")
    if danio not in DANIO_VIVIENDA_TIPOS:
        raise HTTPException(400, f"Tipo de daño inválido: {danio}")


# ---------------------------------------------------------------------------
# Vistas HTML
# ---------------------------------------------------------------------------
@router.get(
    "/modulo4/vulnerabilidad",
    response_class=HTMLResponse,
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("vulnerabilidad:consultar")),
    ],
)
def vista_vulnerabilidad(
    request: Request,
    user: Usuario = Depends(get_current_user_html),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "modulo4/vulnerabilidad.html",
        {
            "app_name": settings.APP_NAME,
            "user": user,
            "csrf_token": emitir_csrf(request),
            "comunas": list(COMUNAS_COORDS.keys()),
            "danio_tipos": DANIO_VIVIENDA_TIPOS,
        },
    )


@router.get(
    "/modulo4/edan",
    response_class=HTMLResponse,
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:leer")),
    ],
)
def vista_edan(
    request: Request,
    user: Usuario = Depends(get_current_user_html),
):
    return templates.TemplateResponse(
        request,
        "modulo4/edan.html",
        {
            "app_name": settings.APP_NAME,
            "user": user,
            "csrf_token": emitir_csrf(request),
            "comunas": list(COMUNAS_COORDS.keys()),
            "danio_tipos": DANIO_VIVIENDA_TIPOS,
        },
    )


# ---------------------------------------------------------------------------
# API: análisis de vulnerabilidad (sub-módulo A)
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo4/vulnerabilidad",
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("vulnerabilidad:consultar")),
    ],
)
def api_vulnerabilidad(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
):
    return calcular_vulnerabilidad(db, comuna=comuna)


@router.get(
    "/api/modulo4/sectores-censales",
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("vulnerabilidad:consultar")),
    ],
)
def api_sectores_censales(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
):
    q = db.query(DatoCensal)
    if comuna:
        q = q.filter(DatoCensal.comuna == comuna)
    sectores = q.all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": (
                    {"type": "Point", "coordinates": [s.lon, s.lat]}
                    if s.lat is not None and s.lon is not None else None
                ),
                "properties": {
                    "id": s.id,
                    "comuna": s.comuna,
                    "sector": s.sector,
                    "poblacion": s.poblacion,
                    "viviendas": s.viviendas,
                    "escuelas": s.escuelas,
                    "postas": s.postas,
                },
            }
            for s in sectores
        ],
    }


# ---------------------------------------------------------------------------
# API: EDAN — lectura
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo4/edan",
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:leer")),
    ],
)
def api_listar_edan(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
    comuna: Optional[str] = None,
    solo_activas: bool = True,
):
    q = db.query(FichaEDAN)
    if comuna:
        q = q.filter(FichaEDAN.comuna == comuna)
    if solo_activas:
        q = q.filter(FichaEDAN.activo.is_(True))  # noqa: E712
    fichas = q.order_by(FichaEDAN.creado_en.desc()).all()
    return {"fichas": [_serializar_edan(f) for f in fichas]}


@router.get(
    "/api/modulo4/incidentes-disponibles",
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:leer")),
    ],
)
def api_incidentes_disponibles(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    """Incidentes vigentes del M2 para vincularlos a una ficha EDAN (D2)."""
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
                "geojson_geometria": json.loads(i.geojson_geometria) if i.geojson_geometria else None,
            }
            for i in incidentes
        ]
    }


# ---------------------------------------------------------------------------
# API: EDAN — crear
# ---------------------------------------------------------------------------
@router.post(
    "/api/modulo4/edan",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:escribir")),
    ],
)
def api_crear_edan(
    body: CrearEDANBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    _validar_edan(body.comuna, body.estado, body.danio_vivienda_tipo)

    geojson_str = _resolver_geometria(db, body.incidente_id, body.geojson_geometria)
    if body.incidente_id is not None and geojson_str is None:
        raise HTTPException(400, "El incidente vinculado no tiene geometría")

    nueva = FichaEDAN(
        comuna=body.comuna.strip(),
        sector=body.sector,
        estado=body.estado,
        danio_vivienda_tipo=body.danio_vivienda_tipo,
        geojson_geometria=geojson_str,
        incidente_id=body.incidente_id,
        viviendas_evaluadas=body.viviendas_evaluadas,
        viviendas_danadas=body.viviendas_danadas,
        viviendas_destruidas=body.viviendas_destruidas,
        personas_afectadas=body.personas_afectadas,
        personas_damnificadas=body.personas_damnificadas,
        personas_desaparecidas=body.personas_desaparecidas,
        personas_fallecidas=body.personas_fallecidas,
        nec_agua_potable=body.nec_agua_potable,
        nec_alimentacion=body.nec_alimentacion,
        nec_habitacion=body.nec_habitacion,
        nec_asistencia_medica=body.nec_asistencia_medica,
        nec_servicio_sanitario=body.nec_servicio_sanitario,
        otras_necesidades=body.otras_necesidades,
        creado_por_id=user.id,
        activo=True,
    )
    db.add(nueva)
    db.flush()

    registrar_auditoria(
        db, request, user.id,
        f"Creó ficha EDAN #{nueva.id} - {nueva.comuna}",
        "fichas_edan", nueva.id,
    )
    db.commit()
    db.refresh(nueva)
    return {"estado": "ok", "edan_id": nueva.id}


# ---------------------------------------------------------------------------
# API: EDAN — editar
# ---------------------------------------------------------------------------
@router.put(
    "/api/modulo4/edan/{edan_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:escribir")),
    ],
)
def api_editar_edan(
    edan_id: int,
    body: EditarEDANBody,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    edan = db.get(FichaEDAN, edan_id)
    if edan is None or not edan.activo:
        raise HTTPException(404, "Ficha EDAN no encontrada")

    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"estado": "sin_cambios", "cambios": []}

    if "estado" in data and data["estado"] not in ESTADOS_EDAN:
        raise HTTPException(400, f"Estado inválido: {data['estado']}")
    if "danio_vivienda_tipo" in data and data["danio_vivienda_tipo"] not in DANIO_VIVIENDA_TIPOS:
        raise HTTPException(400, f"Tipo de daño inválido: {data['danio_vivienda_tipo']}")
    if "comuna" in data and not (data["comuna"] or "").strip():
        raise HTTPException(400, "La comuna es obligatoria")

    cambios: list[str] = []

    # --- Georreferenciación (D2) ---
    if "incidente_id" in data:
        nuevo_inc = data["incidente_id"]
        if nuevo_inc is not None:
            inc = db.get(Incidente, nuevo_inc)
            if inc is None or inc.eliminado:
                raise HTTPException(404, "Incidente vinculado no encontrado")
            if edan.incidente_id != nuevo_inc:
                cambios.append(f"incidente → #{nuevo_inc}")
            edan.incidente_id = nuevo_inc
            # si no se envió geometría explícita, refresca el snapshot desde M2
            if "geojson_geometria" not in data and inc.geojson_geometria:
                edan.geojson_geometria = inc.geojson_geometria
                cambios.append("geometría (desde incidente)")
        else:
            if edan.incidente_id is not None:
                cambios.append("desvinculó incidente")
            edan.incidente_id = None

    if "geojson_geometria" in data:
        nuevo_geo = data["geojson_geometria"]
        edan.geojson_geometria = json.dumps(nuevo_geo) if nuevo_geo else None
        cambios.append("geometría")

    # --- Campos simples ---
    simples = ("comuna", "sector", "estado", "danio_vivienda_tipo", "otras_necesidades")
    for campo in simples + CAMPOS_ENTERO + CAMPOS_BOOL:
        if campo in data and data[campo] != getattr(edan, campo):
            valor_anterior = getattr(edan, campo)
            setattr(edan, campo, data[campo])
            if campo in ("comuna", "estado", "danio_vivienda_tipo"):
                cambios.append(f"{campo} '{valor_anterior}' → '{data[campo]}'")
            else:
                cambios.append(campo)

    if not cambios:
        return {"estado": "sin_cambios", "cambios": []}

    registrar_auditoria(
        db, request, user.id,
        f"Modificó ficha EDAN #{edan.id} ({', '.join(cambios)})",
        "fichas_edan", edan.id,
    )
    db.commit()
    return {"estado": "ok", "edan_id": edan.id, "cambios": cambios}


# ---------------------------------------------------------------------------
# API: EDAN — eliminar (soft delete)
# ---------------------------------------------------------------------------
@router.delete(
    "/api/modulo4/edan/{edan_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("edan:escribir")),
    ],
)
def api_eliminar_edan(
    edan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    edan = db.get(FichaEDAN, edan_id)
    if edan is None or not edan.activo:
        raise HTTPException(404, "Ficha EDAN no encontrada")

    edan.activo = False
    registrar_auditoria(
        db, request, user.id,
        f"Eliminó ficha EDAN #{edan.id} - {edan.comuna}",
        "fichas_edan", edan.id,
    )
    db.commit()
    return {"estado": "ok"}


# ---------------------------------------------------------------------------
# API: consolidado / exportación SENAPRED
# ---------------------------------------------------------------------------
@router.get(
    "/api/modulo4/exportar-edan",
    dependencies=[
        Depends(requiere_modulo("modulo_4")),
        Depends(requiere_permiso("exportar:datos")),
    ],
)
def api_exportar_edan(
    db: Session = Depends(get_db),
    user: Usuario = Depends(usuario_actual),
):
    fichas = db.query(FichaEDAN).filter(FichaEDAN.activo.is_(True)).all()  # noqa: E712

    resumen = {
        "total_fichas": len(fichas),
        "borrador": sum(1 for f in fichas if f.estado == "borrador"),
        "enviada": sum(1 for f in fichas if f.estado == "enviada"),
        "viviendas_evaluadas": sum(f.viviendas_evaluadas for f in fichas),
        "viviendas_danadas": sum(f.viviendas_danadas for f in fichas),
        "viviendas_destruidas": sum(f.viviendas_destruidas for f in fichas),
        "personas_afectadas": sum(f.personas_afectadas for f in fichas),
        "personas_damnificadas": sum(f.personas_damnificadas for f in fichas),
        "personas_desaparecidas": sum(f.personas_desaparecidas for f in fichas),
        "personas_fallecidas": sum(f.personas_fallecidas for f in fichas),
    }

    geojson = {
        "type": "FeatureCollection",
        "titulo": "Consolidado EDAN — Sistema GRD Comunal",
        "resumen": resumen,
        "features": [
            {
                "type": "Feature",
                "geometry": _geojson(f),
                "properties": _serializar_edan(f),
            }
            for f in fichas
        ],
    }
    return JSONResponse(
        content=geojson,
        headers={"Content-Disposition": "attachment; filename=fichas_edan_grd.geojson"},
    )
