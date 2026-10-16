# app/services/modulo4_engine.py
"""
Motor del Módulo 4 — Análisis de Vulnerabilidad Socioeconómica.

Cruza los sectores censales (``datos_censales``, decisión D1: datos locales)
con los polígonos de riesgo activos del Módulo 3 (``zonas_riesgo``) mediante
point-in-polygon (ray casting).

El centroide de cada sector (lat/lon) representa al sector completo: es una
aproximación suficiente para el prototipo y MUY importante: se resuelve en
Python puro, sin SpatiaLite ni PostGIS, en línea con la filosofía del motor
del Módulo 3 (determinista, auditable, sin cajas negras).
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app import models


# ---------------------------------------------------------------------------
# Primitiva geométrica: point-in-polygon (ray casting)
# ---------------------------------------------------------------------------
def _punto_en_anillo(lon: float, lat: float, anillo: list) -> bool:
    """¿El punto (lon, lat) cae dentro del anillo dado (lista de [lon, lat])?"""
    dentro = False
    n = len(anillo)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat):
            x_corte = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_corte:
                dentro = not dentro
        j = i
    return dentro


def punto_en_poligono(lon: float, lat: float, geojson) -> bool:
    """Devuelve True si el punto cae dentro del Polygon GeoJSON.

    Acepta el GeoJSON ya parseado o serializado (str). Solo soporta Polygon;
    Point/LineString devuelven False (no son áreas de exposición).
    """
    if geojson is None:
        return False
    if isinstance(geojson, str):
        try:
            geojson = json.loads(geojson)
        except (TypeError, ValueError):
            return False
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        return False

    anillos = geojson.get("coordinates") or []
    if not anillos:
        return False
    # Anillo exterior
    if not _punto_en_anillo(lon, lat, anillos[0]):
        return False
    # Huecos (anillos interiores): si cae en uno, está fuera
    for hueco in anillos[1:]:
        if _punto_en_anillo(lon, lat, hueco):
            return False
    return True


# ---------------------------------------------------------------------------
# Cruce: sectores censales × zonas de riesgo
# ---------------------------------------------------------------------------
def calcular_vulnerabilidad(db: Session, comuna: Optional[str] = None) -> dict:
    """Cruza datos censales con las zonas de riesgo activas del Módulo 3.

    Devuelve un dict con:
      * resumen global (población total del territorio vs. expuesta),
      * detalle por zona (qué sectores y cuánta población/infraestructura cae
        dentro de cada polígono),
      * lista plana de sectores expuestos.

    El total expuesto deduplica sectores (un sector dentro de 2 zonas solo
    cuenta una vez); el detalle por zona sí lo muestra en cada una.
    """
    # --- Datos de entrada ---
    q_sectores = db.query(models.DatoCensal)
    q_zonas = db.query(models.ZonaRiesgo).filter(models.ZonaRiesgo.activa.is_(True))  # noqa: E712
    if comuna:
        q_sectores = q_sectores.filter(models.DatoCensal.comuna == comuna)
        q_zonas = q_zonas.filter(models.ZonaRiesgo.comuna == comuna)

    sectores = q_sectores.all()
    zonas = q_zonas.order_by(models.ZonaRiesgo.id).all()

    # --- Cruce ---
    expuestos_por_zona: list[dict] = []
    ids_sector_expuesto: set[int] = set()  # deduplicado global

    for zona in zonas:
        try:
            geom = json.loads(zona.geojson_geometria)
        except (TypeError, ValueError):
            geom = None

        afectados = [
            s for s in sectores
            if s.lat is not None and s.lon is not None and punto_en_poligono(s.lon, s.lat, geom)
        ]
        for s in afectados:
            ids_sector_expuesto.add(s.id)

        expuestos_por_zona.append({
            "zona_id": zona.id,
            "nombre": zona.nombre,
            "comuna": zona.comuna,
            "severidad": zona.severidad,
            "geojson": geom,
            "poblacion_expuesta": sum(s.poblacion for s in afectados),
            "viviendas_expuestas": sum(s.viviendas for s in afectados),
            "escuelas_expuestas": sum(s.escuelas for s in afectados),
            "postas_expuestas": sum(s.postas for s in afectados),
            "sectores": [
                {
                    "id": s.id,
                    "sector": s.sector,
                    "poblacion": s.poblacion,
                    "viviendas": s.viviendas,
                    "escuelas": s.escuelas,
                    "postas": s.postas,
                }
                for s in afectados
            ],
        })

    # --- Totales globales (deduplicando sectores) ---
    sectores_expuestos = [s for s in sectores if s.id in ids_sector_expuesto]
    poblacion_total = sum(s.poblacion for s in sectores)
    poblacion_expuesta = sum(s.poblacion for s in sectores_expuestos)

    return {
        "comuna": comuna,
        "resumen": {
            "sectores_evaluados": len(sectores),
            "zonas_activas": len(zonas),
            "poblacion_total": poblacion_total,
            "poblacion_expuesta": poblacion_expuesta,
            "viviendas_expuestas": sum(s.viviendas for s in sectores_expuestos),
            "escuelas_expuestas": sum(s.escuelas for s in sectores_expuestos),
            "postas_expuestas": sum(s.postas for s in sectores_expuestos),
            "porcentaje_poblacion_expuesta": (
                round(poblacion_expuesta * 100.0 / poblacion_total, 1)
                if poblacion_total else 0.0
            ),
        },
        "zonas": expuestos_por_zona,
        "sectores_expuestos": [
            {
                "id": s.id,
                "sector": s.sector,
                "comuna": s.comuna,
                "poblacion": s.poblacion,
                "viviendas": s.viviendas,
                "escuelas": s.escuelas,
                "postas": s.postas,
            }
            for s in sectores_expuestos
        ],
    }
