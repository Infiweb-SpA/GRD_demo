# app/services/modulo3_engine.py
"""
Motor de Inteligencia Predictiva — Módulo 3 GRD.

Algoritmo empírico determinista (Ley 21.364).
Sin dependencias geoespaciales externas (math puro).

v2 — Scoring diferenciado por amenaza:
  * Matriz AMENAZAS_CONFIG con pesos específicos.
  * Clustering por familia (hidro / seca / geo).
  * Familia geo excluida del motor automático.
  * Componentes normalizados 0-1, score final 0-100.
"""

from __future__ import annotations

import json
import math
import traceback
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


# ---------------------------------------------------------------------------
# Comunas soportadas
# ---------------------------------------------------------------------------

COMUNAS_COORDS: dict[str, dict[str, float]] = {
    "Cunco":           {"lat": -38.9328, "lon": -72.0320},
    "Freire":          {"lat": -38.9530, "lon": -72.6270},
    "Padre Las Casas": {"lat": -38.7674, "lon": -72.5956},
}


# ---------------------------------------------------------------------------
# APIs externas
# ---------------------------------------------------------------------------

FLOOD_API_URL     = "https://flood-api.open-meteo.com/v1/flood"
ARCHIVE_API_URL   = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API_URL  = "https://api.open-meteo.com/v1/forecast"


# ---------------------------------------------------------------------------
# Parámetros del motor
# ---------------------------------------------------------------------------

FECHA_INICIO_HISTORICO = date(2016, 1, 1)
VENTANA_DIAS           = 3
UMBRAL_SCORE_MINIMO    = 40.0
RADIO_CLUSTER_KM       = 5.0
RADIO_POLIGONO_FACTOR  = 1.3
RADIO_COMUNA_KM        = 30.0
LAG_API_FLUVIAL_DIAS   = 2
FLOOD_BLOQUE_ANIOS     = 3
FORECAST_MAX_PAST_DAYS = 90
PRECIP_ESCALA_MM       = 20.0   # mm en ventana que saturan la componente de precipitación
CRECIDAS_ESCALA_HITS   = 5.0    # hits ponderados (P95*2 + P90) que saturan crecidas


# ---------------------------------------------------------------------------
# Matriz de amenazas: familia + pesos (suman 100)
# ---------------------------------------------------------------------------

AMENAZAS_CONFIG: dict[str, dict] = {
    # ---------- Familia hidro-meteorológica ----------
    "inundacion": {
        "nombre": "Inundación", "familia": "hidro",
        "pesos": {"crecidas": 40, "precipitacion": 30, "recurrencia": 30},
    },
    "aluvion": {
        "nombre": "Aluvión", "familia": "hidro",
        "pesos": {"crecidas": 40, "precipitacion": 30, "recurrencia": 30},
    },
    "deslizamiento": {
        "nombre": "Deslizamiento", "familia": "hidro",
        "pesos": {"crecidas": 15, "precipitacion": 55, "recurrencia": 30},
    },
    "temporal": {
        "nombre": "Temporal", "familia": "hidro",
        "pesos": {"crecidas": 10, "precipitacion": 50, "recurrencia": 40},
    },
    # ---------- Familia climática seca (MVP: solo recurrencia) ----------
    "incendio forestal": {
        "nombre": "Incendio Forestal", "familia": "seca",
        "pesos": {"recurrencia": 100},
    },
    "ola de calor": {
        "nombre": "Ola de Calor", "familia": "seca",
        "pesos": {"recurrencia": 100},
    },
    "sequia": {
        "nombre": "Sequía", "familia": "seca",
        "pesos": {"recurrencia": 100},
    },
    # ---------- Familia geológica (excluida del motor automático) ----------
    "terremoto":          {"nombre": "Terremoto",           "familia": "geo", "pesos": {}},
    "erupcion volcanica": {"nombre": "Erupción Volcánica",  "familia": "geo", "pesos": {}},
}

# Vecinos que saturan la componente de recurrencia según familia
VECINOS_RECURRENCIA_MAX = {"hidro": 4, "seca": 2, "geo": 1}

# Etiqueta legible por familia (para el motivo público)
FAMILIAS_LABEL = {
    "hidro": "hidro-meteorológica",
    "seca":  "climática seca",
    "geo":   "geológica",
}


# ---------------------------------------------------------------------------
# Normalización de strings
# ---------------------------------------------------------------------------

def _normalizar(s: str) -> str:
    """Sin tildes, minúsculas, espacios colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _config_amenaza(amenaza: str) -> Optional[dict]:
    return AMENAZAS_CONFIG.get(_normalizar(amenaza))


# ---------------------------------------------------------------------------
# Utilidades matemáticas
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    s = sorted(valores)
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def _centroide_geojson(geom: dict) -> Optional[tuple[float, float]]:
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None
    if gtype == "Point":
        return (coords[1], coords[0])
    if gtype == "LineString":
        lons = [c[0] for c in coords]; lats = [c[1] for c in coords]
    elif gtype == "Polygon":
        ring = coords[0]
        lons = [c[0] for c in ring]; lats = [c[1] for c in ring]
    else:
        return None
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _poligono_circular(lat: float, lon: float, radio_km: float, n: int = 16) -> dict:
    coords: list[list[float]] = []
    for k in range(n):
        ang = 2 * math.pi * k / n
        dlat = (radio_km / 111.0) * math.cos(ang)
        dlon = (radio_km / (111.0 * math.cos(math.radians(lat)))) * math.sin(ang)
        coords.append([round(lon + dlon, 7), round(lat + dlat, 7)])
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def _clasificar_severidad(score_promedio: float) -> str:
    if score_promedio >= 80:
        return "critico"
    if score_promedio >= 65:
        return "alto"
    if score_promedio >= 50:
        return "medio"
    return "bajo"


# ---------------------------------------------------------------------------
# API Flood (caudal)
# ---------------------------------------------------------------------------

def _fetch_flood_bloque(comuna: str, inicio: date, fin: date) -> list[dict]:
    coords = COMUNAS_COORDS[comuna]
    params = {
        "latitude": coords["lat"], "longitude": coords["lon"],
        "daily": "river_discharge",
        "start_date": inicio.isoformat(), "end_date": fin.isoformat(),
        "timezone": "America/Santiago",
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.get(FLOOD_API_URL, params=params)
        if r.status_code != 200:
            print(f"[M3][Flood] {comuna} {inicio}→{fin} HTTP {r.status_code}: {r.text[:300]}")
            return []
        data = r.json()
    daily = data.get("daily", {})
    out = []
    for f, q in zip(daily.get("time", []), daily.get("river_discharge", [])):
        if q is None:
            continue
        try:
            out.append({"fecha": date.fromisoformat(f), "caudal": float(q)})
        except (ValueError, TypeError):
            continue
    return out


def _fetch_flood_range(comuna: str, inicio: date, fin: date) -> list[dict]:
    filas: list[dict] = []
    cursor = inicio
    while cursor <= fin:
        bloque_fin = min(
            date(cursor.year + FLOOD_BLOQUE_ANIOS, cursor.month, cursor.day)
            - timedelta(days=1),
            fin,
        )
        filas.extend(_fetch_flood_bloque(comuna, cursor, bloque_fin))
        cursor = bloque_fin + timedelta(days=1)
    return filas


def sincronizar_datos_fluviales(db: Session, comuna: str) -> int:
    hasta = date.today() - timedelta(days=LAG_API_FLUVIAL_DIAS)
    ultimo = (
        db.query(func.max(models.DatoFluvialHistorico.fecha))
        .filter(models.DatoFluvialHistorico.comuna == comuna)
        .scalar()
    )
    if ultimo and isinstance(ultimo, str):
        try:
            ultimo = date.fromisoformat(ultimo)
        except ValueError:
            print(f"[M3] WARN: no pude parsear '{ultimo}' como fecha, reinicio backfill")
            ultimo = None

    inicio = (ultimo + timedelta(days=1)) if ultimo else FECHA_INICIO_HISTORICO
    if inicio > hasta:
        return 0

    filas = _fetch_flood_range(comuna, inicio, hasta)
    if not filas:
        return 0

    coords = COMUNAS_COORDS[comuna]
    db.add_all([
        models.DatoFluvialHistorico(
            comuna=comuna, fecha=f["fecha"], caudal_m3_s=f["caudal"],
            lat=coords["lat"], lon=coords["lon"],
        )
        for f in filas
    ])
    db.commit()
    return len(filas)


# ---------------------------------------------------------------------------
# API Precipitación (Forecast reciente + Archive histórico)
# ---------------------------------------------------------------------------

def _fetch_precipitacion_forecast(comuna, inicio, fin):
    dias_atras = (date.today() - inicio).days
    dias_atras = max(1, min(dias_atras, FORECAST_MAX_PAST_DAYS))
    coords = COMUNAS_COORDS[comuna]
    params = {
        "latitude": coords["lat"], "longitude": coords["lon"],
        "daily": "precipitation_sum",
        "past_days": dias_atras, "forecast_days": 1,
        "timezone": "America/Santiago",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(FORECAST_API_URL, params=params)
            if r.status_code != 200:
                print(f"[M3][Precip/FC] {comuna} HTTP {r.status_code}: {r.text[:200]}")
                return {}
            data = r.json()
    except httpx.HTTPError as e:
        print(f"[M3][Precip/FC] {comuna}: {e}")
        return {}
    daily = data.get("daily", {})
    result = {}
    for f, p in zip(daily.get("time", []), daily.get("precipitation_sum", [])):
        try:
            fd = date.fromisoformat(f)
        except (ValueError, TypeError):
            continue
        if inicio <= fd <= fin:
            result[fd] = float(p or 0.0)
    return result


def _fetch_precipitacion_archive(comuna, inicio, fin):
    fin_ajustado = min(fin, date.today() - timedelta(days=6))
    if inicio > fin_ajustado:
        return {}
    coords = COMUNAS_COORDS[comuna]
    params = {
        "latitude": coords["lat"], "longitude": coords["lon"],
        "daily": "precipitation_sum",
        "start_date": inicio.isoformat(), "end_date": fin_ajustado.isoformat(),
        "timezone": "America/Santiago",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(ARCHIVE_API_URL, params=params)
            if r.status_code != 200:
                return {}
            data = r.json()
    except httpx.HTTPError as e:
        print(f"[M3][Precip/AR] {comuna}: {e}")
        return {}
    daily = data.get("daily", {})
    return {
        date.fromisoformat(f): float(p or 0.0)
        for f, p in zip(daily.get("time", []), daily.get("precipitation_sum", []))
    }


def _fetch_precipitacion(comuna, inicio, fin):
    hoy = date.today()
    corte = hoy - timedelta(days=FORECAST_MAX_PAST_DAYS)
    precip = {}
    if inicio < corte:
        fin_ar = min(fin, corte - timedelta(days=1))
        if inicio <= fin_ar:
            precip.update(_fetch_precipitacion_archive(comuna, inicio, fin_ar))
    inicio_fc = max(inicio, corte)
    if inicio_fc <= fin:
        precip.update(_fetch_precipitacion_forecast(comuna, inicio_fc, fin))
    return precip


# ---------------------------------------------------------------------------
# Scoring con pesos por amenaza
# ---------------------------------------------------------------------------

def _score_incidente(incidente, caudales_por_fecha, p90, p95,
                     precip_por_fecha, vecinos, centro, config) -> tuple[float, dict]:
    fecha_inc = (
        incidente.fecha_creacion.date()
        if isinstance(incidente.fecha_creacion, datetime)
        else incidente.fecha_creacion
    )
    ventana = [fecha_inc + timedelta(days=d)
               for d in range(-VENTANA_DIAS, VENTANA_DIAS + 1)]

    # Componente crecidas (0-1)
    hits_p95 = 0
    hits_p90 = 0
    pico = 0.0
    for f in ventana:
        q = caudales_por_fecha.get(f)
        if q is None:
            continue
        pico = max(pico, q)
        if q >= p95:
            hits_p95 += 1
        elif q >= p90:
            hits_p90 += 1
    norm_crecidas = min(hits_p95 * 2 + hits_p90, CRECIDAS_ESCALA_HITS) / CRECIDAS_ESCALA_HITS

    # Componente precipitación (0-1)
    precip_total = sum(precip_por_fecha.get(f, 0.0) for f in ventana)
    norm_precip = min(precip_total / PRECIP_ESCALA_MM, 1.0)

    # Componente recurrencia (0-1)
    lat, lon = centro
    n_vecinos = sum(
        1 for v in vecinos
        if v["id"] != incidente.id
        and _haversine_km(lat, lon, *v["centro"]) <= RADIO_CLUSTER_KM
    )
    max_vec = VECINOS_RECURRENCIA_MAX.get(config["familia"], 4)
    norm_recurrencia = min(n_vecinos / max_vec, 1.0)

    # Aplicar pesos
    pesos = config["pesos"]
    pts_crecidas = norm_crecidas * pesos.get("crecidas", 0)
    pts_precip   = norm_precip   * pesos.get("precipitacion", 0)
    pts_recur    = norm_recurrencia * pesos.get("recurrencia", 0)

    score = pts_crecidas + pts_precip + pts_recur
    meta = {
        "familia": config["familia"],
        "amenaza_canonica": config["nombre"],
        "pico_caudal_ventana": round(pico, 2),
        "p90_caudal": round(p90, 2),
        "p95_caudal": round(p95, 2),
        "precipitacion_ventana_mm": round(precip_total, 2),
        "incidentes_vecinos": n_vecinos,
        "desglose": {
            "crecidas": round(pts_crecidas, 1),
            "precipitacion": round(pts_precip, 1),
            "recurrencia": round(pts_recur, 1),
        },
    }
    return score, meta


def _clustering(items: list[dict], radio_km: float) -> list[list[dict]]:
    """Greedy por proximidad. Los items ya vienen agrupados por familia."""
    clusters: list[list[dict]] = []
    usados: set[int] = set()
    for i, it in enumerate(items):
        if i in usados:
            continue
        grupo = [it]; usados.add(i)
        for j in range(i + 1, len(items)):
            if j in usados:
                continue
            if _haversine_km(*it["centro"], *items[j]["centro"]) <= radio_km:
                grupo.append(items[j]); usados.add(j)
        clusters.append(grupo)
    return clusters


def _clustering_por_familia(candidatos: list[dict]) -> list[tuple[str, list[dict]]]:
    """Agrupa por familia Y proximidad. Devuelve [(familia, cluster), ...]."""
    por_familia: dict[str, list[dict]] = defaultdict(list)
    for c in candidatos:
        por_familia[c["familia"]].append(c)
    out: list[tuple[str, list[dict]]] = []
    for familia, items in por_familia.items():
        for grupo in _clustering(items, RADIO_CLUSTER_KM):
            out.append((familia, grupo))
    return out


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def generar_zonas_riesgo(db: Session, comunas: Optional[list[str]] = None) -> dict:
    comunas = comunas or list(COMUNAS_COORDS.keys())
    resultado: dict = {"generadas": 0, "por_comuna": {}}

    for comuna in comunas:
        if comuna not in COMUNAS_COORDS:
            resultado["por_comuna"][comuna] = {"error": "comuna desconocida"}
            continue

        try:
            n_sync = sincronizar_datos_fluviales(db, comuna)
        except Exception as e:
            n_sync = 0
            print(f"[M3] Error sincronizando {comuna}:\n{traceback.format_exc()}")
            resultado.setdefault("advertencias", []).append(f"{comuna}: {e}")

        filas = (
            db.query(models.DatoFluvialHistorico)
            .filter(models.DatoFluvialHistorico.comuna == comuna)
            .all()
        )
        if not filas:
            resultado["por_comuna"][comuna] = {"error": "sin datos fluviales"}
            continue
        caudales = {f.fecha: f.caudal_m3_s for f in filas}
        valores = list(caudales.values())
        p90 = _percentil(valores, 0.90)
        p95 = _percentil(valores, 0.95)

        centro_comuna = (COMUNAS_COORDS[comuna]["lat"], COMUNAS_COORDS[comuna]["lon"])
        incidentes = (
            db.query(models.Incidente)
            .filter(models.Incidente.eliminado == False)  # noqa: E712
            .all()
        )

        incidentes_comuna: list[tuple] = []
        excluidos_amenaza = 0
        for inc in incidentes:
            config = _config_amenaza(inc.amenaza_tipo)
            if config is None or config["familia"] == "geo":
                excluidos_amenaza += 1
                continue
            try:
                geom = json.loads(inc.geojson_geometria)
            except (ValueError, TypeError):
                continue
            c = _centroide_geojson(geom)
            if not c:
                continue
            if _haversine_km(*c, *centro_comuna) <= RADIO_COMUNA_KM:
                incidentes_comuna.append((inc, c, config))

        if not incidentes_comuna:
            resultado["por_comuna"][comuna] = {
                "zonas": 0, "incidentes_analizados": 0,
                "excluidos_por_amenaza": excluidos_amenaza,
                "p90": round(p90, 2), "p95": round(p95, 2),
                "sincronizados_fluvial": n_sync,
            }
            continue

        # Precipitación: ventana combinada de todos los incidentes de la comuna
        fechas = [
            inc.fecha_creacion.date()
            if isinstance(inc.fecha_creacion, datetime) else inc.fecha_creacion
            for inc, _, _ in incidentes_comuna
        ]
        inicio_p = min(fechas) - timedelta(days=VENTANA_DIAS)
        fin_p    = max(fechas) + timedelta(days=VENTANA_DIAS)
        precip = _fetch_precipitacion(comuna, inicio_p, fin_p)

        vecinos_centro = [{"id": inc.id, "centro": c} for inc, c, _ in incidentes_comuna]

        candidatos: list[dict] = []
        for inc, c, config in incidentes_comuna:
            score, meta = _score_incidente(
                inc, caudales, p90, p95, precip, vecinos_centro, c, config
            )
            if score >= UMBRAL_SCORE_MINIMO:
                candidatos.append({
                    "incidente_id": inc.id,
                    "amenaza": config["nombre"],
                    "familia": config["familia"],
                    "centro": c,
                    "score": score,
                    "meta": meta,
                })

        # Desactivar zonas automáticas previas de la comuna
        db.query(models.ZonaRiesgo).filter(
            models.ZonaRiesgo.comuna == comuna,
            models.ZonaRiesgo.generado_automaticamente == True,  # noqa: E712
        ).update({"activa": False}, synchronize_session=False)
        db.commit()

        # Clustering por familia
        clusters = _clustering_por_familia(candidatos)
        zonas_creadas = 0
        familias_count: dict[str, int] = defaultdict(int)

        for familia, cluster in clusters:
            if not cluster:
                continue
            lat_c = sum(x["centro"][0] for x in cluster) / len(cluster)
            lon_c = sum(x["centro"][1] for x in cluster) / len(cluster)
            radio = max(_haversine_km(lat_c, lon_c, *x["centro"]) for x in cluster)
            radio = max(radio, 0.5) * RADIO_POLIGONO_FACTOR

            score_prom = sum(x["score"] for x in cluster) / len(cluster)
            severidad = _clasificar_severidad(score_prom)
            amenazas = sorted({x["amenaza"] for x in cluster})
            familia_label = FAMILIAS_LABEL.get(familia, familia)

            motivo = (
                f"Zona de riesgo {familia_label} consolidada a partir de "
                f"{len(cluster)} incidente(s) de tipo {', '.join(amenazas)}. "
                f"Score empírico promedio {score_prom:.1f}/100. "
                f"Caudal de referencia: P90={p90:.1f} m³/s, P95={p95:.1f} m³/s."
            )

            nombre_zona = f"Zona {comuna} {familia} #{familias_count[familia] + 1}"

            zona = models.ZonaRiesgo(
                comuna=comuna,
                nombre=nombre_zona,
                severidad=severidad,
                geojson_geometria=json.dumps(_poligono_circular(lat_c, lon_c, radio)),
                motivo=motivo[:500],
                datos_origen=json.dumps({
                    "familia": familia,
                    "incidentes_vinculados": [x["incidente_id"] for x in cluster],
                    "scores": [round(x["score"], 1) for x in cluster],
                    "score_promedio": round(score_prom, 1),
                    "radio_km": round(radio, 2),
                    "centroide": [round(lat_c, 6), round(lon_c, 6)],
                    "p90_caudal": round(p90, 2),
                    "p95_caudal": round(p95, 2),
                    "metadata_por_incidente": [
                        {"id": x["incidente_id"], **x["meta"]} for x in cluster
                    ],
                }, ensure_ascii=False),
                activa=True,
                generado_automaticamente=True,
            )
            db.add(zona)
            zonas_creadas += 1
            familias_count[familia] += 1

        db.commit()
        resultado["por_comuna"][comuna] = {
            "zonas": zonas_creadas,
            "incidentes_analizados": len(incidentes_comuna),
            "excluidos_por_amenaza": excluidos_amenaza,
            "candidatos_sobre_umbral": len(candidatos),
            "familias_zonificadas": dict(familias_count),
            "p90": round(p90, 2),
            "p95": round(p95, 2),
            "sincronizados_fluvial": n_sync,
            "precipitacion_dias_cargados": len(precip),
        }
        resultado["generadas"] += zonas_creadas

    return resultado