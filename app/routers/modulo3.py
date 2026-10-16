# app/routers/modulo3.py
"""
Módulo 3 — Inteligencia Predictiva de Zonas de Riesgo.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import (
    csrf_obligatorio,
    registrar_auditoria,
    requiere_modulo,
    requiere_permiso,
    usuario_actual,
)
from app.services.modulo3_engine import (
    COMUNAS_COORDS,
    generar_zonas_riesgo,
    sincronizar_datos_fluviales,
)
from app import models


router = APIRouter(tags=["Módulo 3 — Zonas de Riesgo"])
templates = Jinja2Templates(directory="app/templates")


class GenerarZonasBody(BaseModel):
    comunas: Optional[list[str]] = None


class EditarZonaBody(BaseModel):
    nombre: Optional[str] = None
    severidad: Optional[str] = None
    activa: Optional[bool] = None


SEVERIDADES_VALIDAS = {"bajo", "medio", "alto", "critico"}


# ---------------------------------------------------------------------------
# Vista HTML
# ---------------------------------------------------------------------------

@router.get("/modulo3/zonas", response_class=HTMLResponse)
def vista_zonas(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:leer")),
):
    # FIX: firma nueva de Starlette — request primero, luego name, luego context
    return templates.TemplateResponse(
        request,
        "modulo3/zonas.html",
        {
            "user": user,
            "comunas": list(COMUNAS_COORDS.keys()),
        },
    )


# ---------------------------------------------------------------------------
# Generación y sincronización
# ---------------------------------------------------------------------------

@router.post("/api/modulo3/generar")
def api_generar(
    body: GenerarZonasBody,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _csrf=Depends(csrf_obligatorio),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:generar")),
):
    try:
        resultado = generar_zonas_riesgo(db, comunas=body.comunas)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Error generando zonas: {e}") from e

    registrar_auditoria(
        db, request, user.id,
        f"Generó zonas de riesgo ({resultado.get('generadas', 0)} nuevas)",
        "zonas_riesgo", 0,
    )
    db.commit()
    return resultado


@router.post("/api/modulo3/sincronizar-fluvial")
def api_sincronizar(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _csrf=Depends(csrf_obligatorio),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:generar")),
):
    res: dict = {}
    total = 0
    for comuna in COMUNAS_COORDS:
        try:
            n = sincronizar_datos_fluviales(db, comuna)
            res[comuna] = {"nuevos_registros": n}
            total += n
        except Exception as e:  # noqa: BLE001
            res[comuna] = {"error": str(e)}

    registrar_auditoria(
        db, request, user.id,
        f"Sincronizó datos fluviales ({total} registros nuevos)",
        "datos_fluviales_historicos", 0,
    )
    db.commit()
    return res


# ---------------------------------------------------------------------------
# CRUD de zonas
# ---------------------------------------------------------------------------

@router.get("/api/modulo3/zonas")
def api_listar_zonas(
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:leer")),
    comuna: Optional[str] = None,
    solo_activas: bool = True,
):
    q = db.query(models.ZonaRiesgo)
    if comuna:
        q = q.filter(models.ZonaRiesgo.comuna == comuna)
    if solo_activas:
        q = q.filter(models.ZonaRiesgo.activa == True)  # noqa: E712
    zonas = q.order_by(models.ZonaRiesgo.fecha_generacion.desc()).all()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(z.geojson_geometria),
                "properties": {
                    "id": z.id,
                    "comuna": z.comuna,
                    "nombre": z.nombre,
                    "severidad": z.severidad,
                    "motivo": z.motivo,
                    "activa": z.activa,
                    "generado_automaticamente": z.generado_automaticamente,
                    "fecha_generacion": (
                        z.fecha_generacion.isoformat() if z.fecha_generacion else None
                    ),
                    "datos_origen": (
                        json.loads(z.datos_origen) if z.datos_origen else None
                    ),
                },
            }
            for z in zonas
        ],
    }


@router.put("/api/modulo3/zonas/{zona_id}")
def api_editar_zona(
    zona_id: int,
    body: EditarZonaBody,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _csrf=Depends(csrf_obligatorio),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:editar")),
):
    zona = db.query(models.ZonaRiesgo).filter(models.ZonaRiesgo.id == zona_id).first()
    if not zona:
        raise HTTPException(404, "Zona no encontrada")

    cambios = []
    if body.nombre is not None and body.nombre != zona.nombre:
        cambios.append(f"nombre '{zona.nombre}' → '{body.nombre}'")
        zona.nombre = body.nombre
    if body.severidad is not None:
        if body.severidad not in SEVERIDADES_VALIDAS:
            raise HTTPException(400, f"Severidad inválida: {body.severidad}")
        if body.severidad != zona.severidad:
            cambios.append(f"severidad '{zona.severidad}' → '{body.severidad}'")
            zona.severidad = body.severidad
    if body.activa is not None and body.activa != zona.activa:
        cambios.append(f"activa {zona.activa} → {body.activa}")
        zona.activa = body.activa

    if not cambios:
        return {"ok": True, "cambios": []}

    zona.generado_automaticamente = False

    registrar_auditoria(
        db, request, user.id,
        f"Editó zona #{zona_id}: " + "; ".join(cambios),
        "zonas_riesgo", zona_id,
    )
    db.commit()
    return {"ok": True, "cambios": cambios}


@router.delete("/api/modulo3/zonas/{zona_id}")
def api_desactivar_zona(
    zona_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(usuario_actual),
    _csrf=Depends(csrf_obligatorio),
    _mod=Depends(requiere_modulo("modulo_3")),
    _perm=Depends(requiere_permiso("zonas:editar")),
):
    zona = db.query(models.ZonaRiesgo).filter(models.ZonaRiesgo.id == zona_id).first()
    if not zona:
        raise HTTPException(404, "Zona no encontrada")

    zona.activa = False
    zona.generado_automaticamente = False

    registrar_auditoria(
        db, request, user.id,
        f"Desactivó zona #{zona_id} ({zona.comuna})",
        "zonas_riesgo", zona_id,
    )
    db.commit()
    return {"ok": True}