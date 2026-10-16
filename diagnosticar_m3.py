# diagnosticar_m3.py
"""Diagnóstico del estado del Módulo 3."""
import json
from datetime import timedelta
from sqlalchemy import func

from app.database import SessionLocal
from app import models
from app.services.modulo3_engine import (
    COMUNAS_COORDS, _fetch_precipitacion, _percentil, _haversine_km,
    _centroide_geojson, VENTANA_DIAS,
)

db = SessionLocal()

print("=" * 70)
print("1) DATOS FLUVIALES EN BD")
print("=" * 70)
for c in COMUNAS_COORDS:
    cnt = db.query(models.DatoFluvialHistorico).filter_by(comuna=c).count()
    mn = db.query(func.min(models.DatoFluvialHistorico.fecha)).filter_by(comuna=c).scalar()
    mx = db.query(func.max(models.DatoFluvialHistorico.fecha)).filter_by(comuna=c).scalar()
    print(f"  {c:18s}: {cnt:5d} filas | {mn} → {mx}")

print()
print("=" * 70)
print("2) INCIDENTES VIGENTES")
print("=" * 70)
for inc in db.query(models.Incidente).filter(models.Incidente.eliminado == False).all():
    try:
        geom = json.loads(inc.geojson_geometria)
        centro = _centroide_geojson(geom)
    except Exception:
        centro = None
    print(f"  #{inc.id} {inc.amenaza_tipo:20s} fecha={inc.fecha_creacion} centro={centro}")

print()
print("=" * 70)
print("3) TEST DE PRECIPITACIÓN PARA LA FECHA DE CADA INCIDENTE")
print("=" * 70)
for c in COMUNAS_COORDS:
    incs = db.query(models.Incidente).filter(models.Incidente.eliminado == False).all()
    for inc in incs:
        try:
            geom = json.loads(inc.geojson_geometria)
            centro = _centroide_geojson(geom)
        except Exception:
            continue
        if not centro:
            continue
        clat, clon = COMUNAS_COORDS[c]["lat"], COMUNAS_COORDS[c]["lon"]
        if _haversine_km(*centro, clat, clon) > 30:
            continue
        f_inc = inc.fecha_creacion.date() if hasattr(inc.fecha_creacion, "date") else inc.fecha_creacion
        ini = f_inc - timedelta(days=VENTANA_DIAS)
        fin = f_inc + timedelta(days=VENTANA_DIAS)
        precip = _fetch_precipitacion(c, ini, fin)
        total = sum(precip.values())
        print(f"  {c:18s} inc#{inc.id} {f_inc} ventana {ini}→{fin} → {len(precip)} días, {total:.1f} mm")

print()
print("=" * 70)
print("4) SCORE POTENCIAL DE CADA INCIDENTE")
print("=" * 70)
for c in COMUNAS_COORDS:
    filas = db.query(models.DatoFluvialHistorico).filter_by(comuna=c).all()
    if not filas:
        print(f"  {c}: sin datos fluviales")
        continue
    caudales = {f.fecha: f.caudal_m3_s for f in filas}
    p90 = _percentil(list(caudales.values()), 0.90)
    p95 = _percentil(list(caudales.values()), 0.95)
    incs = db.query(models.Incidente).filter(models.Incidente.eliminado == False).all()
    for inc in incs:
        try:
            geom = json.loads(inc.geojson_geometria)
            centro = _centroide_geojson(geom)
        except Exception:
            continue
        if not centro:
            continue
        clat, clon = COMUNAS_COORDS[c]["lat"], COMUNAS_COORDS[c]["lon"]
        if _haversine_km(*centro, clat, clon) > 30:
            continue
        f_inc = inc.fecha_creacion.date() if hasattr(inc.fecha_creacion, "date") else inc.fecha_creacion
        ventana = [f_inc + timedelta(days=d) for d in range(-VENTANA_DIAS, VENTANA_DIAS + 1)]
        hits_p95 = sum(1 for f in ventana if caudales.get(f, 0) >= p95)
        hits_p90 = sum(1 for f in ventana if p90 <= caudales.get(f, 0) < p95)
        score_crec = min(hits_p95 * 2 * 8 + hits_p90 * 8, 40)
        print(f"  {c:18s} inc#{inc.id} {f_inc} → P95 hits={hits_p95} P90 hits={hits_p90} → crecidas={score_crec}/40")

db.close()