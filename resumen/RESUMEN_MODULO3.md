# Sistema GRD Comunal – Módulo 3: Inteligencia Predictiva de Zonas de Riesgo

## 📌 Estado actual

- **Operativo (MVP)** ✅
- Versión: **v1.0.0** (motor v2 con scoring por familia de amenaza)
- Dependencias clave: FastAPI · SQLAlchemy · Jinja2 · Tailwind CSS (CDN) · Leaflet 1.9.4 · MapLibre GL · Open-Meteo (Flood + Forecast + Archive) · SQLite
- Entorno: `.venv` con FastAPI + Uvicorn
- Python: 3.14 (compatible)
- Cumplimiento: **Ley 21.364** (Sistema Nacional de Prevención y Respuesta ante Desastres)
- **Decisión de diseño relevante:** motor empírico determinista con pesos explícitos por amenaza. Sin ML, sin cajas negras, auditable ante la CGR.

---

## 📂 Archivos que componen este módulo

| Archivo / Carpeta | Rol dentro del módulo |
| --- | --- |
| `app/services/modulo3_engine.py` | Motor completo: sincronización fluvial, precipitación, scoring por amenaza, clustering por familia, persistencia |
| `app/services/__init__.py` | Marcador de paquete (vacío) |
| `app/routers/modulo3.py` | Endpoints: vista HTML, generar, sincronizar, CRUD de zonas |
| `app/templates/modulo3/zonas.html` | Vista operativa: mapa Leaflet + panel de control + tabla + modal de detalle técnico |
| `app/templates/modulo1/mapa.html` | Capa conmutable "Zonas de Riesgo" en el visor público con colores por severidad |
| `app/templates/dashboard.html` | Tarjeta del módulo con candado dinámico (licencia + permiso) |
| `app/routers/vistas.py` | Arma la entrada del módulo en la lista `modulos` |
| `app/routers/modulo1.py` | Endpoint público `/api/modulo1/zonas-riesgo-publicas` |
| `app/models.py` (tablas `datos_fluviales_historicos` y `zonas_riesgo`) | Modelos ORM |
| `seed_modulo3.py` | Habilita permisos + licencia en BD existente (idempotente) |
| `app/static/uploads/` | (Compartido con M2) |

---

## 🎯 Alcance y funcionalidades implementadas

| Componente | Descripción |
| --- | --- |
| **Motor de scoring empírico** | Algoritmo determinista que combina 3 forzantes (crecidas fluviales, precipitación, recurrencia geográfica) con pesos específicos por amenaza. |
| **Matriz de amenazas** | 9 amenazas catalogadas en 3 familias: **hidro-meteorológica** (Inundación, Aluvión, Deslizamiento, Temporal), **climática seca** (Incendio Forestal, Ola de Calor, Sequía) y **geológica** (Terremoto, Erupción Volcánica). |
| **Cache fluvial Open-Meteo Flood** | Backfill histórico 2016→hoy por comuna. Sincronización incremental (solo trae días nuevos). Almacenado en `datos_fluviales_historicos`. |
| **Precipitación resiliente** | Combina **Forecast API** (últimos ~90 días con `past_days`) + **Archive API** (histórico con lag de 6 días). Un fallo de la API externa no tumba la generación. |
| **Cálculo de P90/P95** | Percentiles de caudal por comuna para detectar crecidas objetivamente (no umbrales arbitrarios). |
| **Clustering por familia** | Agrupa incidentes por **familia de amenaza Y proximidad** (radio 5 km). No mezcla sequías con inundaciones. |
| **Score clasificado en 4 severidades** | bajo (<50) · medio (50-64.9) · alto (65-79.9) · critico (≥80). |
| **Trazabilidad total** | Cada zona guarda `datos_origen` (JSON) con: familia, scores individuales, desglose por componente, P90/P95, IDs de incidentes vinculados, metadata técnica. |
| **Regeneración idempotente** | Cada `POST /generar` desactiva las zonas automáticas previas de la comuna y crea las nuevas. Las zonas editadas manualmente NO se borran. |
| **Vista operativa `/modulo3/zonas`** | Mapa Leaflet + OpenFreeMap con zonas por color, tabla con filtros, modal de detalle con score, botón Generar y botón Sincronizar. |
| **Capa pública en visor ciudadano** | El `mapa.html` del Módulo 1 tiene la capa "Zonas de Riesgo" activa por defecto con colores por severidad y leyenda de 4 niveles. |
| **Exportación de geometrías** | Disponible vía `GET /api/modulo1/zonas-riesgo-publicas` (público saneado) y `GET /api/modulo3/zonas` (privado con metadata). |
| **Auditoría legal (CGR)** | Cada generación, sincronización, edición o desactivación queda en `logs_auditoria` con usuario, IP y timestamp. |

---

## 📡 Endpoints del Módulo 3

### Vistas HTML

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/modulo3/zonas` | GET | 🔒 `modulo_3` + `zonas:leer` | Vista operativa con mapa, tabla y controles. |

### API REST (privada — dashboard)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo3/generar` | POST | 🔒 CSRF + `modulo_3` + `zonas:generar` | Ejecuta el motor. Body opcional `{"comunas": [...]}`. |
| `/api/modulo3/sincronizar-fluvial` | POST | 🔒 CSRF + `modulo_3` + `zonas:generar` | Solo backfill de caudal fluvial. |
| `/api/modulo3/zonas` | GET | 🔒 `modulo_3` + `zonas:leer` | FeatureCollection con `datos_origen` completo. |
| `/api/modulo3/zonas/{id}` | PUT | 🔒 CSRF + `modulo_3` + `zonas:editar` | Edita nombre, severidad o estado activa. |
| `/api/modulo3/zonas/{id}` | DELETE | 🔒 CSRF + `modulo_3` + `zonas:editar` | Soft delete (`activa=False`). |

### API REST (pública — visor ciudadano)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo1/zonas-riesgo-publicas` | GET | 🌐 Público | FeatureCollection saneada. **No expone** `datos_origen`, `creado_por_id` ni `generado_automaticamente`. |

### Endpoints de otros módulos que afectan al M3

| Ruta | Método | Descripción |
| --- | --- | --- |
| `/dashboard` | GET | Muestra la tarjeta del módulo con candado dinámico (licencia + permiso `zonas:leer`). |
| `/auth/logout` | POST | Redirige a `/modulo1/landing`. |

---

## 🗂️ Modelo de datos involucrado

### Tabla `datos_fluviales_historicos`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `comuna` | String(100) | Indexado |
| `fecha` | Date | Indexado |
| `caudal_m3_s` | Float | Caudal diario del río |
| `lat` / `lon` | Float | Coordenadas usadas en la consulta |
| — | — | `UniqueConstraint(comuna, fecha)` |

**Volumen actual:** ~3.940 filas por comuna (11.817 total, 2016-01-01 → hoy).

### Tabla `zonas_riesgo`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `comuna` | String(100) | Indexado |
| `nombre` | String(200) | Ej: "Zona Cunco hidro #1" |
| `severidad` | String(20) | `bajo` \| `medio` \| `alto` \| `critico` |
| `geojson_geometria` | Text | Polygon WGS84 con 16 vértices |
| `motivo` | String(500) | Texto legible para ciudadano |
| `datos_origen` | Text | JSON con toda la trazabilidad del algoritmo |
| `activa` | Boolean | Indexado. Default `True` |
| `generado_automaticamente` | Boolean | `True` = borrable al regenerar; `False` = manual |
| `creado_por_id` | Integer FK | → `usuarios.id` (`SET NULL`) |
| `fecha_generacion` | DateTime UTC | Indexado |

### Estructura de `datos_origen` (JSON)

```json
{
  "familia": "hidro",
  "incidentes_vinculados": [2, 5],
  "scores": [45.3, 48.1],
  "score_promedio": 46.7,
  "radio_km": 2.71,
  "centroide": [-38.957377, -72.168603],
  "p90_caudal": 151.05,
  "p95_caudal": 182.65,
  "metadata_por_incidente": [
    {
      "id": 2,
      "familia": "hidro",
      "amenaza_canonica": "Inundación",
      "pico_caudal_ventana": 182.23,
      "precipitacion_ventana_mm": 14.2,
      "incidentes_vecinos": 0,
      "desglose": {
        "crecidas": 24.0,
        "precipitacion": 21.3,
        "recurrencia": 0.0
      }
    }
  ]
}
```

---

## 🧠 Algoritmo del motor

### Fase 1 — Sincronización de datos
1. Consulta Open-Meteo Flood desde el último día en BD + 1 (o desde 2016 si vacío).
2. Trocea el rango en bloques de 3 años para evitar límites de la API.
3. Inserta en `datos_fluviales_historicos` con `UniqueConstraint`.

### Fase 2 — Análisis por comuna
1. Carga los caudales históricos y calcula **P90** y **P95**.
2. Carga precipitación (Forecast + Archive) para la ventana `[min_fecha - 3, max_fecha + 3]`.
3. Filtra incidentes del M2 por comuna (Haversine ≤ 30 km del centro comunal).
4. Excluye amenazas de familia `geo` (no analizables con forzantes climáticos).

### Fase 3 — Scoring por incidente
```
Componente crecidas (normalizado 0-1)     = min(hits_p95*2 + hits_p90, 5) / 5
Componente precipitación (normalizado 0-1) = min(mm_ventana / 20, 1)
Componente recurrencia (normalizado 0-1)   = min(vecinos_5km / max_familia, 1)

score = Σ (componente × peso_de_la_amenaza)
```

Donde `max_familia` = 4 para hidro, 2 para seca.

### Fase 4 — Clustering y persistencia
1. Agrupa candidatos (score ≥ 40) por **familia + proximidad (5 km)**.
2. Desactiva zonas automáticas previas de la comuna.
3. Genera polígono circular (radio = máx distancia intra-cluster × 1.3, mínimo 500 m).
4. Clasifica severidad por score promedio.
5. Persiste `ZonaRiesgo` con `datos_origen` completo.

### Matriz de pesos por amenaza

| Amenaza | Familia | Crecidas | Precip | Recurrencia |
| --- | --- | --- | --- | --- |
| Inundación | hidro | 40 | 30 | 30 |
| Aluvión | hidro | 40 | 30 | 30 |
| Deslizamiento | hidro | 15 | 55 | 30 |
| Temporal | hidro | 10 | 50 | 40 |
| Incendio Forestal | seca | 0 | 0 | 100 |
| Ola de Calor | seca | 0 | 0 | 100 |
| Sequía | seca | 0 | 0 | 100 |
| Terremoto | geo | — | — | — (excluida) |
| Erupción Volcánica | geo | — | — | — (excluida) |

---

## 🔐 Seguridad y cumplimiento

| Aspecto | Estado |
| --- | --- |
| **CSRF** | Toda escritura exige header `X-CSRF-Token` obtenido de `GET /auth/csrf`. |
| **RBAC** | Permisos específicos: `zonas:leer`, `zonas:generar`, `zonas:editar`. |
| **Feature flag** | `requiere_modulo("modulo_3")` bloquea si el municipio no contrató el módulo. |
| **Auditoría CGR** | Cada acción deja rastro en `logs_auditoria` dentro de la misma transacción. |
| **Endpoint público saneado** | Solo expone `id, comuna, nombre, severidad, motivo`. **No** expone `datos_origen`, autor, IP, ni IDs de incidentes. |
| **Trazabilidad algorítmica** | `datos_origen` guarda el porqué de cada decisión (auditable por la CGR o un tribunal). |
| **Determinismo** | Mismo input → mismo output. Sin ML, sin cajas negras. |
| **Soft delete** | Las zonas se marcan `activa=False` pero no se borran de BD. |

---

## 🎯 Decisiones de diseño

- **Motor determinista, no ML:** la Ley 21.364 exige trazabilidad. Un modelo de caja negra no es defendible ante la CGR.
- **Pesos por amenaza, no universales:** una sequía no se agrava con caudal alto del río. Cada amenaza tiene sus propios forzantes físicos.
- **Clustering por familia:** nunca agrupa Sequía con Inundación, aunque estén a 100 m.
- **Familia geo excluida del motor:** un terremoto no tiene forzantes climáticos predecibles. Se crea manualmente desde el dashboard.
- **Cache de caudal en BD propia:** evita depender de la API externa en cada consulta y permite calcular P90/P95 locales.
- **Precipitación Forecast + Archive:** el Archive API tiene lag de 6 días y no sirve para incidentes recientes. Forecast con `past_days=90` cubre el hueco.
- **Radio 5 km por cluster:** zonas rurales de La Araucanía; 2 km era demasiado estricto.
- **Severidad en 4 niveles:** estándar de la industria (bajo/medio/alto/critico) en lugar de "alto/moderado" binario.
- **Regeneración idempotente:** cada `POST /generar` no acumula ruido. Las zonas manuales se preservan.

---

## 🧪 Pruebas rápidas

```bash
# 1) Verificación de la matriz de amenazas
python verificar2.py

# 2) Diagnóstico del motor
python diagnosticar_m3.py

# 3) Test completo del flujo
powershell -ExecutionPolicy Bypass -File .\test_m3.ps1

# 4) Endpoint público (sin sesión)
curl http://localhost:8000/api/modulo1/zonas-riesgo-publicas | jq

# 5) Verificar tablas nuevas en BD
python -c "from app.database import SessionLocal; from app import models; db=SessionLocal(); print('Fluvial:', db.query(models.DatoFluvialHistorico).count()); print('Zonas:', db.query(models.ZonaRiesgo).count())"
```

**Vista web:**
- `/modulo3/zonas` → panel operativo
- `/modulo1/mapa` → visor público con capa de zonas

---

## 🔗 Integraciones con otros módulos

| Módulo | Integración |
| --- | --- |
| **Módulo 0** | Reutiliza `csrf_obligatorio`, `usuario_actual`, `requiere_modulo`, `requiere_permiso`, `registrar_auditoria`. Feature flag `modulo_3`. |
| **Módulo 1** | Publica zonas activas vía `/api/modulo1/zonas-riesgo-publicas`. La capa "Zonas de Riesgo" del visor ciudadano ahora tiene datos reales. |
| **Módulo 2** | Fuente principal de datos. El motor consume `Incidente` vigentes (`eliminado=False`). |
| **Módulo 4** (futuro) | Podrá cruzar los polígonos de zona con datos censales para análisis de vulnerabilidad. |
| **Consola admin** (`/admin`) | El superadmin ve los logs de auditoría de acciones del M3 (crear, generar, editar, desactivar). |

---

## 🛠️ Pendientes / próximos pasos

### 🔴 Propios del M3

1. **Exportación GeoJSON de zonas** — replicar el patrón del M2 (`/api/modulo2/exportar-datos`) para entregar zonas a SENAPRED / IDE Chile.
2. **Edición de geometría de zona** — hoy el `PUT` solo edita nombre/severidad/activa. Permitir dibujar el polígono manualmente (reutilizar dibujo de M2).
3. **Filtros por familia y severidad** en la tabla del dashboard M3 (hoy solo filtra por comuna).
4. **Backfill de datos de entrada para Freire y PLC** — el motor funciona; solo falta que existan incidentes reales en esas comunas (no es bug).
5. **Documento de mapeo Ley 21.364** — articular explícitamente cada componente del motor con los artículos de la ley.
6. **Emisión automática de alerta** cuando se genere una zona `critico` — conectar con `alertas_municipales_activas` del M1.

### 🟡 Transversales (afectan al M3)

7. **Cache de Open-Meteo** con TTL 10-15 min (ya en pendientes M1).
8. **Rol COGRID** con permiso `alertas:emitir` (pendiente M0).
9. **Tests de integración** con `httpx.AsyncClient`.
10. **Doble confirmación** para acciones destructivas (desactivar zona, regenerar).
11. **Migrar a PostgreSQL + PostGIS** si el proyecto escala (soporte geoespacial nativo).

---

## 📝 Notas de versión

- **v1.0.0 — Motor v2** — Versión inicial completa:
  - Motor empírico con matriz de amenazas por familia.
  - Cache fluvial Open-Meteo con backfill incremental.
  - Precipitación combinada Forecast + Archive.
  - Clustering por familia y proximidad.
  - Vista operativa `/modulo3/zonas` con mapa, tabla y controles.
  - Capa pública saneada en el visor ciudadano.
  - Auditoría CGR completa.

---

## 🏛️ Cumplimiento Ley 21.364 — checklist

| Requisito | Estado |
| --- | --- |
| Basado en datos empíricos | ✅ Caudal real + precipitación real + incidentes reales |
| Temporalidad explícita | ✅ Ventana ±3 días por incidente |
| Recurrencia geográfica | ✅ Clustering por proximidad + familia |
| Trazabilidad de decisiones | ✅ `datos_origen` auditable en cada zona |
| Proyección pública | ✅ Capa en `/modulo1/mapa` y endpoint saneado |
| Determinismo algorítmico | ✅ Sin ML, sin cajas negras |
| Registro de auditoría | ✅ `logs_auditoria` con usuario, IP, timestamp |
| Actualización continua | ✅ Regeneración idempotente + sincronización incremental |


---

## Conclusión

**Puedes darlo por terminado como MVP.** El Módulo 3 cumple con lo que la especificación pedía:

- ✅ Algoritmo que intersecta temporalidad + mm de lluvia + recurrencia
- ✅ Consolidación y proyección en mapa público (Ley 21.364)
- ✅ Dependencia funcional del Módulo 2 (usa sus datos)
- ✅ Trazabilidad y auditoría

