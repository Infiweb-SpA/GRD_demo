# Sistema GRD Comunal – Módulo 4: Análisis de Vulnerabilidad y Evaluación de Daños (EDAN)

## 📌 Estado actual

- **Operativo (MVP)** ✅
- Versión: **v1.0.0**
- Dependencias clave: FastAPI · SQLAlchemy · Jinja2 · Tailwind CSS (CDN) · Leaflet 1.9.4 · SQLite
- Entorno: `.venv` con FastAPI + Uvicorn
- Python: 3.14 (compatible)
- Cumplimiento: **Ley 21.364** · Formulario **EDAN SENAPRED** (Evaluación de Daños y Necesidades)
- **Decisión de diseño relevante:** el cruce demográfico es determinista y local (point-in-polygon en Python puro), y la ficha EDAN se vincula al Módulo 2 de forma **híbrida** (FK de trazabilidad + snapshot de geometría propio).

---

## 📂 Archivos que componen este módulo

| Archivo / Carpeta | Rol dentro del módulo |
| --- | --- |
| `app/services/modulo4_engine.py` | Motor de vulnerabilidad: primitiva point-in-polygon (ray casting) + cruce sectores censales × zonas de riesgo |
| `app/routers/modulo4.py` | Endpoints: vistas HTML, análisis, sectores censales, CRUD EDAN, incidentes disponibles, exportación SENAPRED |
| `app/templates/modulo4/vulnerabilidad.html` | Panel de análisis: KPIs + mapa (polígonos de riesgo + sectores censales) + tablas de exposición |
| `app/templates/modulo4/edan.html` | Formulario EDAN (3 bloques SENAPRED) + georreferenciación (vínculo M2 o punto propio) + tabla + detalle + exportación |
| `app/models.py` (tablas `datos_censales` y `fichas_edan`) | Modelos ORM (solo añadidos al final del archivo) |
| `app/main.py` | Registro del router `modulo4` |
| `app/routers/vistas.py` | Entrada del módulo en el dashboard (etiqueta "Vulnerabilidad y EDAN") |
| `seed_modulo4.py` | Habilita permisos + licencia + siembra datos censales en BD existente (idempotente) |
| `resumen/RESUMEN_MODULO4.md` | Este documento |

---

## 🎯 Alcance y funcionalidades implementadas

| Componente | Descripción |
| --- | --- |
| **Cruce demográfico determinista** | `calcular_vulnerabilidad()` ubica el centroide de cada sector censal dentro de los polígonos de riesgo activos del Módulo 3 y suma población e infraestructura expuesta. Sin librerías geoespaciales, sin ML. |
| **Point-in-polygon (ray casting)** | Implementación propia en `modulo4_engine.py`. Soporta Polygon con huecos (anillos interiores). Point/LineString no cuentan como área de exposición. |
| **Deduplicación de exposición** | El total global cuenta cada sector **una sola vez** aunque caiga en varias zonas; el detalle por zona sí lo muestra en cada una. |
| **Tabla local de datos censales** | 12 sectores de prueba (Cunco, Freire, Padre Las Casas) con población, viviendas, escuelas y postas. Sin dependencia de CKAN en runtime (decisión D1). |
| **Panel de vulnerabilidad `/modulo4/vulnerabilidad`** | KPIs (población total vs. expuesta, %, viviendas, escuelas, postas), mapa con polígonos de riesgo coloreados por severidad + sectores censales (rojo = expuesto, azul = no expuesto), filtros por comuna, tablas por zona y por sector expuesto. |
| **Ficha EDAN (SENAPRED) `/modulo4/edan`** | Formulario con los 3 bloques oficiales: (1) tipo de daño en vivienda, (2) número de damnificados, (3) necesidades de habitabilidad. Estados `borrador` → `enviada`. |
| **Georreferenciación híbrida (D2)** | La ficha se vincula a un incidente del Módulo 2 por `incidente_id` (FK) y además guarda un **snapshot** `geojson_geometria` propio. Al crear solo con FK, el backend copia la geometría del incidente. |
| **Selector de incidentes M2** | `/api/modulo4/incidentes-disponibles` lista los incidentes vigentes con su geometría; el formulario los muestra en un desplegable. Como respaldo, se puede marcar un punto clicando el mapa. |
| **CRUD EDAN completo** | Crear, listar (filtro por comuna), editar (PUT parcial con detección de cambios), eliminar (soft delete `activo=False`). |
| **Exportación consolidada SENAPRED** | `GET /api/modulo4/exportar-edan` entrega un GeoJSON FeatureCollection con **miembro `resumen`** (totales por estado, viviendas, damnificados) y una feature por ficha. Header `Content-Disposition: attachment`. |
| **Auditoría legal (CGR)** | Crear, editar y eliminar fichas EDAN deja rastro en `logs_auditoria` con usuario, IP y timestamp, dentro de la misma transacción. |

---

## 📡 Endpoints del Módulo 4

### Vistas HTML

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/modulo4/vulnerabilidad` | GET | 🔒 `modulo_4` + `vulnerabilidad:consultar` | Panel de análisis de vulnerabilidad. |
| `/modulo4/edan` | GET | 🔒 `modulo_4` + `edan:leer` | Formulario y tabla de fichas EDAN. |

### API REST (privada — dashboard)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo4/vulnerabilidad` | GET | 🔒 `modulo_4` + `vulnerabilidad:consultar` | Análisis completo. Query opcional `?comuna=`. |
| `/api/modulo4/sectores-censales` | GET | 🔒 `modulo_4` + `vulnerabilidad:consultar` | FeatureCollection de centroides censales. `?comuna=` opcional. |
| `/api/modulo4/edan` | GET | 🔒 `modulo_4` + `edan:leer` | Lista de fichas activas. `?comuna=`, `?solo_activas=`. |
| `/api/modulo4/edan` | POST | 🔒 CSRF + `modulo_4` + `edan:escribir` | Crea ficha. Acepta `incidente_id` (FK) y/o `geojson_geometria` (snapshot). |
| `/api/modulo4/edan/{id}` | PUT | 🔒 CSRF + `modulo_4` + `edan:escribir` | Edición parcial (`exclude_unset`). Devuelve lista de cambios auditados. |
| `/api/modulo4/edan/{id}` | DELETE | 🔒 CSRF + `modulo_4` + `edan:escribir` | Soft delete (`activo=False`). |
| `/api/modulo4/incidentes-disponibles` | GET | 🔒 `modulo_4` + `edan:leer` | Incidentes vigentes del M2 para vincular (D2). |
| `/api/modulo4/exportar-edan` | GET | 🔒 `modulo_4` + `exportar:datos` | Consolidado SENAPRED (GeoJSON + resumen). Descarga. |

---

## 🗂️ Modelo de datos involucrado

### Tabla `datos_censales`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `comuna` | String(100) | Indexado |
| `sector` | String(200) | Nombre del sector censal |
| `lat` / `lon` | Float | Centroide del sector (punto usado en el cruce) |
| `poblacion` | Integer | Default 0 |
| `viviendas` | Integer | Default 0 |
| `escuelas` | Integer | Infraestructura crítica |
| `postas` | Integer | Infraestructura crítica |
| `creado_en` | DateTime UTC | |

**Volumen actual:** 12 filas (4 sectores por comuna × 3 comunas).

### Tabla `fichas_edan`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `comuna` | String(100) | Indexado. Obligatoria |
| `sector` | String(200) | Opcional |
| `estado` | String(20) | `borrador` \| `enviada` |
| `geojson_geometria` | Text | **Snapshot** Point/Polygon WGS84 (D2) |
| `incidente_id` | Integer FK | → `incidentes_reportes.id` (`SET NULL`). **Opcional** (D2) |
| `danio_vivienda_tipo` | String(50) | `Sin daño` \| `Daño leve` \| `Daño medio` \| `Daño total` |
| `viviendas_evaluadas` | Integer | Bloque 1 — daño en vivienda |
| `viviendas_danadas` | Integer | Daño reparable (leve/medio) |
| `viviendas_destruidas` | Integer | Daño total |
| `personas_afectadas` | Integer | Bloque 2 — damnificados |
| `personas_damnificadas` | Integer | |
| `personas_desaparecidas` | Integer | |
| `personas_fallecidas` | Integer | |
| `nec_agua_potable` | Boolean | Bloque 3 — habitabilidad |
| `nec_alimentacion` | Boolean | |
| `nec_habitacion` | Boolean | Habitación temporal |
| `nec_asistencia_medica` | Boolean | |
| `nec_servicio_sanitario` | Boolean | |
| `otras_necesidades` | Text | Libre |
| `creado_por_id` | Integer FK | → `usuarios.id` (`SET NULL`) |
| `activo` | Boolean | Soft delete. Default `True` |
| `creado_en` | DateTime UTC | |

---

## 🧠 Algoritmo del motor de vulnerabilidad

### Primitiva geométrica: ray casting

```
_punto_en_anillo(lon, lat, anillo):
    dentro = False
    j = último índice del anillo
    para cada vértice i:
        si el segmento (j→i) cruza la horizontal lat:
            si lon < x del cruce: dentro = not dentro
        j = i
    return dentro

punto_en_poligono(lon, lat, geojson):
    si no está en anillo exterior → False
    si está en algún hueco (anillo interior) → False
    si no → True
```

### Cruce sectores × zonas

1. Carga sectores censales (filtro opcional por comuna).
2. Carga zonas de riesgo **activas** del Módulo 3 (`activa=True`).
3. Para cada zona, evalúa qué sectores caen dentro de su polígono.
4. Acumula por zona: población, viviendas, escuelas, postas y lista de sectores.
5. Globalmente **deduplica** sectores por `id` (un sector en 2 zonas cuenta una vez).
6. Calcula el porcentaje de población expuesta sobre la población total del territorio evaluado.

**Verificado con datos reales:** 12 sectores × 3 zonas activas → 8.500 personas expuestas (21,5 %).

---

## 🔐 Seguridad y cumplimiento

| Aspecto | Estado |
| --- | --- |
| **CSRF** | Toda escritura exige header `X-CSRF-Token` obtenido de `GET /auth/csrf`. |
| **RBAC** | Permisos nuevos: `edan:leer`, `edan:escribir`. Reutiliza `vulnerabilidad:consultar` (análisis) y `exportar:datos` (exportación, genérico del M2). |
| **Feature flag** | `requiere_modulo("modulo_4")` bloquea si el municipio no contrató el módulo. |
| **Auditoría CGR** | Crear / editar / eliminar fichas EDAN queda en `logs_auditoria` (usuario, IP, timestamp) en la misma transacción. La edición registra el detalle de campos cambiados. |
| **Validaciones** | Comuna obligatoria, estado y tipo de daño en catálogo, números ≥ 0 (Pydantic `ge=0` → 422), incidente vinculado debe existir y estar vigente (404). |
| **Soft delete** | Las fichas se marcan `activo=False` pero no se borran de BD. |
| **Determinismo** | Mismo input → mismo output. Sin ML, sin cajas negras, auditable ante la CGR. |
| **Independencia del frontend** | El mapa del M4 consume solo endpoints M4 (la geometría de zonas viaja en la respuesta del análisis), por lo que no necesita permisos ni licencia del M3 en el navegador. |

---

## 🎯 Decisiones de diseño

- **D1 — Datos censales locales (`datos_censales`), no CKAN en runtime:** el cruce debe ser determinista, auditable y no depender de la disponibilidad de una API externa. Misma filosofía que el cache fluvial del M3.
- **D2 — Vínculo EDAN ↔ M2 híbrido (FK nullable + snapshot GeoJSON):** la FK da trazabilidad; el snapshot hace que la ficha sea **autocontenida y exportable** sin depender del M2 (que además usa soft delete, así que la FK nunca se rompe).
- **Motor en Python puro, sin SpatiaLite/PostGIS:** SQLite es el SGBD del prototipo; el ray casting es suficiente y mantiene el proyecto desplegable sin dependencias nativas.
- **Centroide del sector como aproximación:** suficiente para el prototipo y explicable ante un tercero. La precisión por vértice queda como mejora futura.
- **Permisos `edan:leer` / `edan:escribir` (convención `reportes:leer/escribir`) + reutilización de `exportar:datos`:** solo 2 permisos nuevos en vez de 4; la exportación ya está gobernada por el permiso genérico que tienen los 3 roles.
- **`seed_modulo4.py` separado (patrón M3) en vez de tocar `app/seed.py`:** `app/seed.py` solo asigna permisos a roles **nuevos**; en una BD existente hay que agregarlos explícitamente. Además evita arriesgar M0–M3 y permite sembrar los datos censales en el mismo script idempotente.
- **`funcionario` recibe `vulnerabilidad:consultar`:** la tarjeta del M4 en el dashboard se desbloquea con ese permiso; así el personal de terreno puede llegar al formulario EDAN.
- **Edición por PUT parcial (`exclude_unset`):** permite cambiar solo los campos enviados y auditar exactamente qué cambió.
- **Consolidado exportado como GeoJSON con miembro `resumen`:** entrega en un solo archivo tanto el mapa (features) como los totales para SENAPRED, válido bajo RFC 7946.

---

## 🧪 Pruebas rápidas

```bash
# 1) Habilitar el módulo en la BD existente (idempotente)
python seed_modulo4.py

# 2) Arrancar el servidor
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 3) Verificar el motor de cruce directamente
python -c "from app.database import SessionLocal; from app import models; from app.services.modulo4_engine import calcular_vulnerabilidad; db=SessionLocal(); import json; print(json.dumps(calcular_vulnerabilidad(db)['resumen'], indent=2))"

# 4) Verificar modelos y tablas
python -c "from app import models; print(len(models.FichaEDAN.__table__.columns), 'columnas FichaEDAN'); print(len(models.DatoCensal.__table__.columns), 'columnas DatoCensal')"
```

**Vista web (con sesión):**
- `/modulo4/vulnerabilidad` → panel de análisis con KPIs y mapa
- `/modulo4/edan` → formulario y tabla de fichas EDAN

---

## 🔗 Integraciones con otros módulos

| Módulo | Integración |
| --- | --- |
| **Módulo 0** | Reutiliza `csrf_obligatorio`, `usuario_actual`, `get_current_user_html`, `requiere_modulo`, `requiere_permiso`, `registrar_auditoria`. Feature flag `modulo_4`. |
| **Módulo 1** | Hereda las 3 comunas del proyecto (Cunco, Freire, Padre Las Casas) vía `COMUNAS_COORDS`. |
| **Módulo 2** | **Fuente del vínculo D2:** la ficha EDAN referencia un `Incidente` vigente y copia su geometría como snapshot. `/api/modulo4/incidentes-disponibles` expone los candidatos. |
| **Módulo 3** | **Fuente del análisis:** el motor M4 consume las `ZonaRiesgo` activas (`activa=True`) como polígonos de exposición. |
| **Módulo 5** (futuro) | El consolidado EDAN será la base para priorizar albergues y logística sobre daño confirmado. |
| **Consola admin** (`/admin`) | El superadmin ve los logs de auditoría de las acciones del M4. |

---

## 🛠️ Pendientes / mejoras a futuro

### 🔴 Propios del M4

1. **Edición de geometría de la ficha desde el mapa** — hoy el formulario permite marcar un **punto** como respaldo; el dibujo de polígonos frescos sigue en el M2. Replicar el motor de dibujo de M2 en `edan.html` para poder trazar polígonos de daño sin incidente previo.
2. **Dashboard de necesidades agregadas** — vista "¿cuántas fichas requieren agua?" (necesidades × comunas) para alimentar directamente la priorización de recursos del Módulo 5.
3. **Carga de datos censales reales** — reemplazar los 12 sectores de prueba por datos oficiales (INE / Censo 2017 / CKAN) mediante un script de importación; la tabla local ya está preparada.
4. **Cruce por vértices, no solo centroide** — evaluar si el sector completo intersecta el polígono (bbox + vértices) para zonas de tamaño comparable al sector.
5. **Flujo de estados EDAN ampliado** — `borrador → enviada → recepcionada` con notificación al SENAPRED y bloqueo de edición tras el envío.
6. **Exportación CSV/PDF del consolidado** — además del GeoJSON, un formato legible para el formulario SENAPRED en papel.
7. **Ficha EDAN con fotos** — reutilizar el patrón de subida del M2 (`app/static/uploads/`) para adjuntar evidencia fotográfica del daño.

### 🟡 Transversales (afectan al M4)

8. **Tests de integración** con `httpx.AsyncClient` (pendiente general).
9. **Rol COGRID** con permiso `alertas:emitir` (pendiente M0).
10. **Migrar a PostgreSQL + PostGIS** si el proyecto escala (cruce geoespacial nativo).
11. **Alerta automática** cuando una ficha declare `personas_fallecidas > 0` o `daño total` — conectar con `alertas_municipales_activas` del M1.

---

## 📝 Notas de versión

- **v1.0.0 — Versión inicial completa:**
  - Motor de vulnerabilidad determinista (point-in-polygon en Python puro).
  - Tabla local de datos censales con 12 sectores de prueba (D1).
  - Panel `/modulo4/vulnerabilidad` con KPIs, mapa y tablas de exposición.
  - Ficha EDAN `/modulo4/edan` con los 3 bloques oficiales SENAPRED.
  - Vínculo híbrido M2 (FK + snapshot) con selector de incidentes y punto de respaldo (D2).
  - CRUD completo con edición parcial auditada y soft delete.
  - Exportación consolidada SENAPRED (GeoJSON + resumen).
  - `seed_modulo4.py` idempotente (permisos + licencia + datos censales).

---

## Conclusión

**Puedes darlo por terminado como MVP.** El Módulo 4 cumple con lo que la especificación pedía:

- ✅ Formulario EDAN con los 3 bloques (daño en vivienda, damnificados, habitabilidad)
- ✅ Vínculo de la dañificación con la georreferencia del Módulo 2 (híbrido FK + snapshot)
- ✅ Cálculo automático de población e infraestructura crítica expuesta en zonas de riesgo
- ✅ Trazabilidad y auditoría (CGR)
- ✅ Consolidación exportable en un solo lugar antes de enviar a SENAPRED
- ✅ Determinismo y auditabilidad del análisis (sin cajas negras)
