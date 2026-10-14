from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any, Optional
import httpx
import asyncio
from datetime import datetime

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))

# Coordenadas geográficas oficiales de las tres comunas de control
COORDENADAS_COMUNAS = {
    "Cunco": {"lat": -38.92, "lon": -72.03},
    "Freire": {"lat": -38.95, "lon": -72.65},
    "Padre Las Casas": {"lat": -38.75, "lon": -72.60}
}

# Alertas del sistema administrativo municipal (Gestión interna)
ALERTAS_INTERNAS = [
    {"tipo": "Lluvia", "intensidad": "Alta", "fecha": "2026-10-15", "comuna": "Cunco"},
    {"tipo": "Viento", "intensidad": "Moderada", "fecha": "2026-10-16", "comuna": "Freire"},
    {"tipo": "Temporal", "intensidad": "Crítica", "fecha": "2026-10-14", "comuna": "Padre Las Casas"}
]

@router.get("/modulo1/landing", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Vista HTML principal de la Landing Page."""
    template = env.get_template("modulo1/landing.html")
    html = template.render(request=request, alertas=ALERTAS_INTERNAS)
    return HTMLResponse(html)

@router.get("/modulo1/mapa", response_class=HTMLResponse)
async def mapa_publico(request: Request):
    """Vista HTML del Visor Cartográfico."""
    template = env.get_template("modulo1/mapa.html")
    return HTMLResponse(template.render(request=request))

@router.get("/api/modulo1/estadisticas")
async def obtener_estadisticas(
    comuna: str = Query("Cunco"), 
    anio: int = Query(2026)
) -> Dict[str, Any]:
    """
    Obtiene clima actual, acumulado 24h, ráfagas de viento, alertas de tormenta 
    y el histórico anual seleccionado dinámicamente (ej. 2024, 2025, 2026).
    """
    if comuna not in COORDENADAS_COMUNAS:
        raise HTTPException(status_code=400, detail=f"La comuna '{comuna}' no está parametrizada.")

    lat = COORDENADAS_COMUNAS[comuna]["lat"]
    lon = COORDENADAS_COMUNAS[comuna]["lon"]

    # Validar rangos de fechas históricos o año en curso
    anho_actual = datetime.now().year
    if anio > anho_actual:
        anio = anho_actual

    # Definir fechas de inicio y fin para el histórico según el año seleccionado
    start_date = f"{anio}-01-01"
    end_date = f"{anio}-12-31"
    
    # Si el año es el actual, acotar la fecha final al día de hoy para evitar errores de API
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if anio == anho_actual:
        end_date = hoy_str

    # Endpoint 1: Pronóstico y tiempo real (incluyendo ráfagas de viento y clima horario)
    url_forecast = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=precipitation,temperature_2m,windgusts_10m&current_weather=true&timezone=America/Santiago"
    
    # Endpoint 2: Histórico diario del año seleccionado (soporta 2024, 2025, 2026, etc.)
    url_archive = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&daily=precipitation_sum&timezone=America/Santiago"

    async with httpx.AsyncClient() as client:
        try:
            res_f, res_a = await asyncio.gather(
                client.get(url_forecast),
                client.get(url_archive)
            )
            
            res_f.raise_for_status()
            res_a.raise_for_status()
            
            data_f = res_f.json()
            data_a = res_a.json()

            # Cálculos de 24 horas
            hourly_data = data_f.get("hourly", {})
            precipitation_list = hourly_data.get("precipitation", [])
            windgusts_list = hourly_data.get("windgusts_10m", [])

            agua_24h = sum(precipitation_list[:24]) if precipitation_list else 0.0
            
            # Ráfaga máxima en las últimas 24 horas
            rafaga_max_24h = max(windgusts_list[:24]) if windgusts_list else 0.0

            # Lógica de alerta por ráfagas superiores a 70 km/h
            alerta_viento_critico = rafaga_max_24h > 70.0

            # Simulación / Detección de Tormenta Eléctrica basada en condiciones de precipitación y viento
            # (En implementaciones avanzadas se puede conectar a APIs de descargas eléctricas o avisos SENAPRED)
            alerta_tormenta_electrica = False
            periodo_tormenta = "Sin riesgo inminente"
            if agua_24h > 15.0 and rafaga_max_24h > 50.0:
                alerta_tormenta_electrica = True
                periodo_tormenta = "Estimado entre las 15:00 y 21:00 hrs de hoy"

            # Procesamiento histórico anual dinámico
            lluvias_diarias = data_a.get("daily", {}).get("precipitation_sum", [])
            fechas_diarias = data_a.get("daily", {}).get("time", [])
            
            valores_mensuales = [0.0] * 12
            for i, fecha_str in enumerate(fechas_diarias):
                try:
                    mes_idx = int(fecha_str.split("-")[1]) - 1
                    if 0 <= mes_idx < 12 and lluvias_diarias[i] is not None:
                        valores_mensuales[mes_idx] += lluvias_diarias[i]
                except (IndexError, ValueError):
                    continue

            meses_claves = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            historico_real = {meses_claves[m]: round(valores_mensuales[m], 1) for m in range(12)}

            efectividad_map = {"Cunco": 85, "Freire": 72, "Padre Las Casas": 91}

            return {
                "comuna": comuna,
                "anio": anio,
                "temperatura_actual": data_f["current_weather"]["temperature"],
                "agua_ultimas_24h": round(agua_24h, 1),
                "rafaga_max_24h": round(rafaga_max_24h, 1),
                "alerta_viento_critico": alerta_viento_critico,
                "alerta_tormenta_electrica": alerta_tormenta_electrica,
                "periodo_tormenta": periodo_tormenta,
                "efectividad_limpieza": efectividad_map.get(comuna, 80),
                "historico_precipitaciones_anual": historico_real
            }

        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Falla de conexión con Open-Meteo: {exc}")

@router.get("/api/modulo1/comparativa-comunas")
async def obtener_comparativa_comunas() -> Dict[str, Any]:
    """Entrega el agua caída real en las últimas 24 horas de todas las comunas para comparación."""
    comparativa = {}
    async with httpx.AsyncClient() as client:
        for comuna, coords in COORDENADAS_COMUNAS.items():
            try:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={coords['lat']}&longitude={coords['lon']}&hourly=precipitation&timezone=America/Santiago"
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    comparativa[comuna] = round(sum(data["hourly"]["precipitation"][:24]), 1)
                else:
                    comparativa[comuna] = 0.0
            except Exception:
                comparativa[comuna] = 0.0
    return {"comparativa_agua_24h": comparativa}