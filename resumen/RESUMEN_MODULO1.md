# Sistema GRD Comunal – Módulo 1: Visor Público y Landing Informativa

## 📌 Estado actual

- **Finalizado** ✅ (con un pendiente de mejora: alertas dinámicas)
- Versión: **v1.0.1**
- Dependencias clave: FastAPI · Jinja2 · Tailwind CSS · Chart.js · Httpx · SQLite / SQLAlchemy
- Entorno: `.venv` con FastAPI + Uvicorn
- Python: 3.14 (compatible)

---

## 📂 Archivos que componen este módulo

| Archivo / Carpeta | Rol dentro del módulo |
| --- | --- |
| `app/routers/modulo1.py` | Endpoints de estadísticas, comparativa, landing, mapa e incidentes públicos |
| `app/templates/modulo1/landing.html` | Landing ciudadana con gráficos Chart.js y tarjetas climáticas |
| `app/templates/modulo1/mapa.html` | Visor cartográfico público con capas conmutables (Leaflet) |
| `app/static/uploads/incidentes/` | (Compartido con Módulo 2) imágenes servidas al visor público |

---

## 🗺️ Alcance y funcionalidades principales

| Componente | Descripción |
| --- | --- |
| **Landing Page Ciudadana** (`/modulo1/landing`) | Interfaz pública y transparente para el monitoreo de las comunas de **Cunco**, **Freire** y **Padre Las Casas**. |
| **Indicadores Climáticos en Tiempo Real** | Consumo dinámico de la API oficial de **Open-Meteo** para temperatura actual, acumulado de agua caída en 24h y ráfagas de viento máximas (`windgusts_10m`). |
| **Gráfico Histórico Dinámico (2015 - 2026)** | Selector temporal con Chart.js para consultar el acumulado mensual de precipitaciones de cualquier año histórico desde 2015. |
| **Gráfico Comparativo Intercomunal** | Gráfico de barras cruzado que evalúa el impacto de precipitaciones de las 3 comunas en las últimas 24h. |
| **Alertas Críticas Automáticas** | Detección automática de tormenta eléctrica (agua 24h > 15 mm + ráfagas > 50 km/h) y ráfagas críticas (> 70 km/h). |
| **Bitácora de Alertas Climáticas** | ⚠️ **Pendiente**: actualmente usa datos estáticos hardcodeados; debe conectarse a la tabla `alertas_municipales_activas`. |
| **Visor Cartográfico Público** (`/modulo1/mapa`) | Mapa Leaflet con capas conmutables: zonas de riesgo, estaciones fluviales e incidentes históricos. |
| **Endpoint de incidentes públicos** | Consumido por el visor ciudadano, sin exponer autor, IP ni IDs internos. |

---

## 📡 Endpoints principales (API REST)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/modulo1/landing` | GET | 🌐 Público | Landing ciudadana (HTML Jinja2). |
| `/modulo1/mapa` | GET | 🌐 Público | Visor cartográfico base (Leaflet). |
| `/api/modulo1/estadisticas` | GET | 🌐 Público | Params: `comuna` y `anio`. Retorna clima actual, agua 24h, ráfagas, efectividad, histórico anual y alertas críticas. **Resiliente a fallos de Open-Meteo**. |
| `/api/modulo1/comparativa-comunas` | GET | 🌐 Público | Consolidado multi-comuna de precipitaciones 24h. |
| `/api/modulo1/incidentes-publicos` | GET | 🌐 Público | FeatureCollection de incidentes vigentes (Módulo 2). No expone autor ni IP. |

### Endpoints modificados que afectan a este módulo

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/` | GET | 🌐 Público | Redirige 303 a `/modulo1/landing` (antes iba a `/dashboard`). |
| `/auth/logout` | POST | 🔒 CSRF | Devuelve `{"redirect": "/modulo1/landing"}` para que el cliente navegue allí tras cerrar sesión. |

---

## 🛡️ Resiliencia ante fallos de Open-Meteo

El endpoint `/api/modulo1/estadisticas` fue rediseñado en v1.0.1 para evitar caídas de toda la vista cuando una API externa falla:

- **Forecast y Archive** se consultan en bloques `try/except` independientes.
- Si el Archive API falla, la vista sigue mostrando el clima actual (con histórico en ceros).
- **Ajuste automático de fecha**: como el Archive API (ERA5) tiene ~5 días de lag, al pedir el año en curso se resta `-6 días` al `end_date` para evitar `400 Bad Request`.
- **Campo diagnóstico** `errores_api` en el JSON: `null` si todo OK, o lista de errores si algo falló.
- **Timeout explícito** de 15 segundos.

### Estructura del JSON de respuesta

```json
{
  "comuna": "Cunco",
  "anio": 2026,
  "temperatura_actual": 12.5,
  "agua_ultimas_24h": 3.2,
  "rafaga_max_24h": 45.8,
  "alerta_viento_critico": false,
  "alerta_tormenta_electrica": false,
  "periodo_tormenta": "Sin riesgo inminente",
  "efectividad_limpieza": 85,
  "historico_precipitaciones_anual": {
    "Ene": 45.2, "Feb": 38.1, "Mar": 62.4,
    "...": "..."
  },
  "errores_api": null
}
```

---

## 🗺️ Capas del visor público

| Capa | Estado | Descripción |
| --- | --- | --- |
| **Zonas de Riesgo** | ✅ Conmutable | Polígonos consolidados (Módulo 3 futuro). |
| **Estaciones Fluviales** | ✅ Conmutable | Marcadores con altura actual (Módulo 1). |
| **Incidentes Históricos** | ✅ Conmutable | Puntos/líneas/polígonos púrpura del Módulo 2, con popups e imágenes. |

Sin herramientas de edición para usuarios anónimos (bloqueo total de Leaflet Geoman).

---

## ⚠️ Pendientes críticos

### 1. Alertas de la Bitácora son estáticas (hardcoded)

Actualmente en `app/routers/modulo1.py`:

```python
ALERTAS_INTERNAS = [
    {"tipo": "Lluvia",   "intensidad": "Alta",     "fecha": "2026-10-15", "comuna": "Cunco"},
    {"tipo": "Viento",   "intensidad": "Moderada", "fecha": "2026-10-16", "comuna": "Freire"},
    {"tipo": "Temporal", "intensidad": "Crítica",  "fecha": "2026-10-14", "comuna": "Padre Las Casas"},
]
```

**Deben reemplazarse** por consulta a la tabla `alertas_municipales_activas` (ya existe el modelo en `models.py` y hay un registro de prueba en `seed.py`).

### 2. Rol COGRID

Pendiente crear rol `cogrid` (Comité de Gestión del Riesgo de Desastres) con permiso `alertas:emitir` para que puedan registrar alertas desde el dashboard.

### 3. CRUD de alertas

Faltan endpoints para que administradores/COGRID creen, activen y desactiven alertas desde el panel.

---

## 🎯 Decisiones de diseño

- **Landing pública sin autenticación**: cumple con el objetivo de transparencia ciudadana.
- **Consumo server-side de Open-Meteo**: el frontend no llama APIs externas directamente (evita CORS y expone menos la lógica).
- **Gráficos del lado del cliente con Chart.js**: se renderizan con datos ya procesados por el backend (más rápido y menos llamadas).
- **Resiliencia por API externa**: un fallo de Archive API no tumba la vista completa.
- **Ajuste de lag del Archive API**: `-6 días` cuando se consulta el año en curso.
- **Mapa sin edición pública**: solo lectura, todas las herramientas de dibujo bloqueadas.

---

## 🧪 Pruebas rápidas

```bash
# 1) Landing pública
curl http://localhost:8000/modulo1/landing

# 2) Visor cartográfico
curl http://localhost:8000/modulo1/mapa

# 3) Estadísticas climáticas (2024, 2025, 2026)
curl "http://localhost:8000/api/modulo1/estadisticas?comuna=Cunco&anio=2026" | jq

# 4) Verificar el campo errores_api (debe ser null en condiciones normales)
curl "http://localhost:8000/api/modulo1/estadisticas?comuna=Freire&anio=2026" | jq '.errores_api'

# 5) Comparativa multi-comuna
curl http://localhost:8000/api/modulo1/comparativa-comunas | jq

# 6) Incidentes públicos (FeatureCollection)
curl http://localhost:8000/api/modulo1/incidentes-publicos | jq
```

---

## 🔗 Integraciones con otros módulos

| Módulo | Integración |
| --- | --- |
| **Módulo 0** | El login expulsa a usuarios logueados (303 a `/dashboard`). El logout devuelve redirect a esta landing. |
| **Módulo 2** | Consume `/api/modulo1/incidentes-publicos` para mostrar los incidentes en el mapa público. |
| **Módulo 3** (futuro) | Alimentará la capa de Zonas de Riesgo con polígonos consolidados. |
| **Módulo 4** (futuro) | Potencial visualización de población vulnerable expuesta en la landing. |

---

## 🛠️ Próximos pasos

1. **Conectar alertas a BD**: reemplazar `ALERTAS_INTERNAS` por consulta a `alertas_municipales_activas`.
2. **Crear rol COGRID** con permiso `alertas:emitir`.
3. **CRUD de alertas**: endpoints `POST/PUT/DELETE /api/modulo1/alertas`.
4. **Panel de gestión de alertas** en el dashboard para administradores y COGRID.
5. **Cache de respuestas de Open-Meteo** (TTL 10-15 min) para reducir llamadas y mejorar tiempo de carga.
6. **Gráfico de temperatura histórica** (actualmente solo precipitaciones).

---

## 📝 Notas de versión

- **v1.0.0** – Versión inicial: landing, gráficos Chart.js, visor Leaflet, endpoints de estadísticas y comparativa.
- **v1.0.1** – Resiliencia ante fallos de Open-Meteo: try/except independientes, ajuste de lag de Archive API, timeout explícito, campo `errores_api` en JSON.

