# Sistema GRD Comunal – Módulo 5: Albergues y Logística

## 📌 Estado actual

- **Operativo (MVP)** ✅
- Versión: **v1.0.0**
- Dependencias clave: FastAPI · SQLAlchemy · Jinja2 · Tailwind CSS (CDN) · Leaflet 1.9.4 · SQLite
- Entorno: `.venv` con FastAPI + Uvicorn
- Python: 3.14 (compatible)
- Cumplimiento: **Ley 21.364** (Sistema Nacional de Prevención y Respuesta ante Desastres)
- **Decisiones de diseño relevantes:** inventario en **una sola tabla con discriminador** de categoría (D3) y vínculos a zonas/incidentes **estrictamente opcionales** (D4). El catastro de albergues se publica de forma saneada en el visor ciudadano del Módulo 1.

---

## 📂 Archivos que componen este módulo

| Archivo / Carpeta | Rol dentro del módulo |
| --- | --- |
| `app/routers/modulo5.py` | Endpoints: vistas HTML, CRUD de albergues, CRUD de recursos, resumen de inventario, consolidado logístico y catálogos para vínculos opcionales |
| `app/templates/modulo5/albergues.html` | Catastro: KPIs + mapa (Leaflet) + formulario con servicios + tabla + detalle |
| `app/templates/modulo5/recursos.html` | Inventario: KPIs por categoría + formulario (discriminador D3 + asignación) + panel logístico + tabla filtrable |
| `app/models.py` (tablas `albergues` y `recursos_inventario`) | Modelos ORM (solo añadidos al final del archivo) |
| `app/routers/modulo1.py` (`/api/modulo1/albergues-publicos`) | Endpoint público saneado para el visor ciudadano (Ley 21.364) |
| `app/templates/modulo1/mapa.html` | Nueva capa conmutable "Albergues" + leyenda en el mapa público |
| `app/main.py` | Registro del router `modulo5` |
| `app/routers/vistas.py` | Entrada del módulo en el dashboard (tarjeta "Albergues y Logística") |
| `seed_modulo5.py` | Habilita permisos + licencia + siembra datos demo en BD existente (idempotente) |
| `resumen/RESUMEN_MODULO5.md` | Este documento |

---

## 🎯 Alcance y funcionalidades implementadas

| Componente | Descripción |
| --- | --- |
| **Catastro de albergues** | Dónde puede refugiarse la población: nombre, comuna, dirección, coordenadas, capacidad y estado (`activo` / `mantencion` / `inactivo`). |
| **Servicios del albergue** | Cinco indicadores que permiten priorizar en una emergencia: agua potable, electricidad, sanitarios, cocina e internet. |
| **Mapa de albergues** | Vista Leaflet con marcadores coloreados por estado; clic en el mapa fija las coordenadas del albergue en edición. |
| **Inventario único con categorías (D3)** | Una sola tabla `recursos_inventario` con discriminador `categoria`: **maquinaria · abrigo · alimento**. Permite consultas globales con la misma estructura. |
| **KPIs por categoría** | Panel con cantidad total, número de ítems y cuántos están asignados en cada categoría, filtrable por comuna. |
| **Asignación logística** | Un recurso puede destinarse a un albergue (`albergue_id`). El sistema **normaliza el estado**: al asignar pasa a `asignado`, al desasignar vuelve a `disponible`. |
| **Panel logístico consolidado** | Cruza cada albergue activo con los recursos asignados (chips por recurso) y totales por categoría + capacidad total del sistema. |
| **Vínculos opcionales (D4)** | Un albergue puede asociarse a una zona de riesgo del M3; un recurso, a un incidente del M2. **Ambos vínculos son opcionales** y no bloquean el alta. |
| **Visor público de albergues** | `/api/modulo1/albergues-publicos` expone los albergues **activos con coordenadas** (nombre, comuna, dirección, capacidad y servicios). **No** expone datos de contacto (privacidad). Nueva capa en el mapa ciudadano. |
| **CRUD completo con soft delete** | Albergues y recursos: crear, listar (con filtros), editar (PUT parcial con detección de cambios) y eliminar (borrado lógico `activo=False`). |
| **Auditoría legal (CGR)** | Cada alta, edición y baja de albergue/recurso queda en `logs_auditoria` (usuario, IP, timestamp) dentro de la misma transacción. |
| **Datos demo** | `seed_modulo5.py` siembra 3 albergues (uno por comuna) y 11 recursos repartidos en las 3 categorías. |

---

## 📡 Endpoints del Módulo 5

### Vistas HTML

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/modulo5/albergues` | GET | 🔒 `modulo_5` + `albergues:leer` | Catastro de albergues (mapa, formulario y tabla). |
| `/modulo5/recursos` | GET | 🔒 `modulo_5` + `recursos:leer` | Inventario y panel logístico. |

### API REST privada (dashboard)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo5/albergues` | GET | 🔒 `modulo_5` + `albergues:leer` | Lista de albergues activos. `?comuna=`, `?solo_activos=`. |
| `/api/modulo5/albergues` | POST | 🔒 CSRF + `modulo_5` + `albergues:escribir` | Crea albergue. Acepta `zona_riesgo_id` opcional (D4). |
| `/api/modulo5/albergues/{id}` | PUT | 🔒 CSRF + `modulo_5` + `albergues:escribir` | Edición parcial (`exclude_unset`). Devuelve campos cambiados. |
| `/api/modulo5/albergues/{id}` | DELETE | 🔒 CSRF + `modulo_5` + `albergues:escribir` | Soft delete (`activo=False`). |
| `/api/modulo5/zonas-disponibles` | GET | 🔒 `modulo_5` + `albergues:leer` | Zonas de riesgo activas del M3 para el vínculo opcional (D4). |
| `/api/modulo5/recursos` | GET | 🔒 `modulo_5` + `recursos:leer` | Lista de recursos. `?comuna=`, `?categoria=`, `?estado=`. |
| `/api/modulo5/recursos` | POST | 🔒 CSRF + `modulo_5` + `recursos:escribir` | Crea recurso. Acepta `albergue_id` e `incidente_id` opcionales (D4). |
| `/api/modulo5/recursos/{id}` | PUT | 🔒 CSRF + `modulo_5` + `recursos:escribir` | Edición parcial + asignación/desasignación con normalización de estado. |
| `/api/modulo5/recursos/{id}` | DELETE | 🔒 CSRF + `modulo_5` + `recursos:escribir` | Soft delete (`activo=False`). |
| `/api/modulo5/incidentes-disponibles` | GET | 🔒 `modulo_5` + `recursos:leer` | Incidentes vigentes del M2 para el vínculo opcional (D4). |
| `/api/modulo5/inventario-resumen` | GET | 🔒 `modulo_5` + `recursos:leer` | Totales por categoría (ítems, cantidad, asignados, disponibles, mantención). |
| `/api/modulo5/logistica` | GET | 🔒 `modulo_5` + `recursos:leer` | Consolidado: albergues activos con sus recursos asignados y totales. `?comuna=`. |

### API REST pública (visor ciudadano)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo1/albergues-publicos` | GET | 🌐 Público | FeatureCollection de albergues activos con coordenadas. Datos saneados (sin contacto). |

---

## 🗂️ Modelo de datos involucrado

### Tabla `albergues`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `nombre` | String(200) | Obligatorio |
| `comuna` | String(100) | Indexado |
| `direccion` | String(300) | Opcional |
| `lat` / `lon` | Float | Coordenadas WGS84 (opcionales) |
| `capacidad` | Integer | Default 0 (personas) |
| `estado` | String(20) | `activo` \| `mantencion` \| `inactivo` |
| `srv_agua_potable` | Boolean | Servicios del albergue |
| `srv_electricidad` | Boolean | |
| `srv_sanitarios` | Boolean | |
| `srv_cocina` | Boolean | |
| `srv_internet` | Boolean | |
| `contacto_nombre` | String(200) | Encargado (no se publica) |
| `contacto_telefono` | String(50) | Encargado (no se publica) |
| `zona_riesgo_id` | Integer FK | → `zonas_riesgo.id` (`SET NULL`). **Opcional** (D4) |
| `creado_por_id` | Integer FK | → `usuarios.id` (`SET NULL`) |
| `activo` | Boolean | Soft delete. Default `True` |
| `creado_en` | DateTime UTC | |

**Volumen actual:** 3 albergues (uno por comuna).

### Tabla `recursos_inventario`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `nombre` | String(200) | Obligatorio |
| `categoria` | String(20) | **Discriminador D3**: `maquinaria` \| `abrigo` \| `alimento` (indexado) |
| `cantidad` | Integer | Default 0 |
| `unidad` | String(50) | Default `unidades` (kg, litros, cajas, kits...) |
| `estado` | String(20) | `disponible` \| `asignado` \| `mantencion` |
| `comuna` | String(100) | Indexado |
| `albergue_id` | Integer FK | → `albergues.id` (`SET NULL`). Destino logístico (opcional) |
| `incidente_id` | Integer FK | → `incidentes_reportes.id` (`SET NULL`). **Opcional** (D4) |
| `notas` | Text | Libre |
| `creado_por_id` | Integer FK | → `usuarios.id` (`SET NULL`) |
| `activo` | Boolean | Soft delete. Default `True` |
| `creado_en` | DateTime UTC | |

**Volumen actual:** 11 recursos demo (4 maquinaria · 4 abrigo · 3 alimento).

---

## 🧠 Lógica del discriminador (D3) y normalización de estado

### Discriminador de categoría

Una sola tabla evita tres tablas casi idénticas y mantiene consultas uniformes:

```
recursos_inventario(categoria = maquinaria | abrigo | alimento)
```

El resumen `inventario-resumen` agrupa dinámicamente por categoría, así agregar
una cuarta categoría (p. ej. `combustible`) solo requiere ampliar la lista
`RECURSO_CATEGORIAS`, sin migraciones.

### Normalización de estado al asignar/desasignar

```
_normalizar_estado_recurso(estado, albergue_id):
    si albergue_id != None y estado == "disponible"  -> "asignado"
    si albergue_id == None y estado == "asignado"    -> "disponible"
    si no                                            -> estado
```

Garantiza coherencia: nunca queda un recurso "disponible" apuntando a un
albergue, ni "asignado" sin destino. El estado `mantencion` se respeta tal cual.

---

## 🔐 Seguridad y cumplimiento

| Aspecto | Estado |
| --- | --- |
| **CSRF** | Toda escritura exige header `X-CSRF-Token` obtenido de `GET /auth/csrf`. |
| **RBAC** | Permisos nuevos: `albergues:leer`, `albergues:escribir`, `recursos:leer`, `recursos:escribir`. |
| **Feature flag** | `requiere_modulo("modulo_5")` bloquea si el municipio no contrató el módulo. |
| **Auditoría CGR** | Alta / edición / baja de albergues y recursos quedan en `logs_auditoria` (usuario, IP, timestamp) en la misma transacción. |
| **Validaciones** | Nombre y comuna obligatorios; estado y categoría en catálogo (400); cantidad ≥ 0 (Pydantic `ge=0` → 422); albergue/incidente/zona vinculados deben existir (404). |
| **Soft delete** | Albergues y recursos se marcan `activo=False` pero no se borran de BD. |
| **Privacidad en el visor público** | El endpoint público **no** expone datos de contacto del encargado ni trazabilidad interna; solo albergues `activo` con coordenadas. |
| **Roles** | Superadmin y administrador: los 4 permisos. Funcionario: `albergues:leer` + `recursos:leer` + `recursos:escribir` (gestiona inventario en terreno, no modifica el catastro). |

---

## 🎯 Decisiones de diseño

- **D3 — Tabla única `recursos_inventario` con discriminador `categoria`:** las tres categorías comparten estructura (nombre, cantidad, unidad, estado, comuna); separarlas en tres tablas multiplicaría el CRUD sin beneficio. El discriminador indexado mantiene consultas rápidas y evita migraciones al añadir categorías.
- **D4 — Vínculos estrictamente opcionales (nullable FK):** un albergue puede o no estar en una zona de riesgo; un recurso puede o no estar ligado a un incidente. Ninguno debe bloquear el alta operativa. La trazabilidad se logra sin acoplar los módulos.
- **Asignación logística como FK a albergue (no tabla de asignaciones):** para el MVP el destino actual del recurso se representa con `albergue_id` + `estado`. El historial de asignaciones (quién movió qué y cuándo) queda como mejora futura, cubierto parcialmente por la auditoría.
- **Normalización de estado en el backend:** la UI no tiene que preocuparse por la coherencia entre asignación y estado; el servidor la garantiza.
- **Albergues en el visor público (M1):** la Ley 21.364 exige que la ciudadanía conozca los puntos de refugio. Se reutilizó el patrón del M3 (`zonas-riesgo-publicas`) por consistencia, saneando los datos sensibles.
- **Catálogo de estados/categorías como constantes explícitas:** misma filosofía determinista y auditable que los módulos anteriores; nada de validaciones ocultas.
- **`seed_modulo5.py` separado (patrón M3/M4):** `app/seed.py` solo asigna permisos a roles **nuevos**; en una BD existente hay que agregarlos explícitamente. El script también crea la licencia `modulo_5` y siembra los datos demo, de forma idempotente.

---

## 🧪 Pruebas rápidas

```bash
# 1) Habilitar el módulo en la BD existente (idempotente)
python seed_modulo5.py

# 2) Arrancar el servidor
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 3) Verificar modelos y tablas
python -c "from app import models; print(len(models.Albergue.__table__.columns), 'cols Albergue'); print(len(models.RecursoInventario.__table__.columns), 'cols Recurso')"

# 4) Verificar el endpoint público (sin sesión)
python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/api/modulo1/albergues-publicos'); print(r.json()['type'], len(r.json()['features']), 'albergues públicos')"
```

**Rutas web:**
- `/modulo5/albergues` → catastro con mapa, formulario y tabla
- `/modulo5/recursos` → inventario, panel logístico y asignación

**Resultado del test E2E (v1.0.0):**
- 3 albergues y 11 recursos demo sembrados · resumen por categoría (maq 10 · abrigo 990 · alimento 1.900)
- Crear albergue **con** zona vinculada (D4) → `id=4`; editar capacidad/estado ✓
- Crear recurso sin asignar → `disponible`; asignar a albergue → pasa **automáticamente** a `asignado`; desasignar → vuelve a `disponible` ✓
- Panel logístico refleja la asignación (abrigo = 100) ✓
- Validaciones: nombre/categoría/estado inválidos → 400; cantidad negativa → 422; albergue/zona inexistentes → 404 ✓
- Soft delete + auditoría (3 altas/ediciones/bajas en `albergues`, 4 en `recursos_inventario`) ✓
- Endpoint público: 3 features, coordenadas `[lon, lat]`, sin datos de contacto ✓

---

## 🔗 Integraciones con otros módulos

| Módulo | Integración |
| --- | --- |
| **Módulo 0** | Reutiliza `csrf_obligatorio`, `usuario_actual`, `get_current_user_html`, `requiere_modulo`, `requiere_permiso`, `registrar_auditoria`. Feature flag `modulo_5`. |
| **Módulo 1** | **Salida pública:** `/api/modulo1/albergues-publicos` alimenta la capa "Albergues" del visor ciudadano (Leaflet). |
| **Módulo 2** | Vínculo opcional recurso → incidente (`incidente_id`, D4). El formulario ofrece un desplegable con los incidentes vigentes. |
| **Módulo 3** | Vínculo opcional albergue → zona de riesgo (`zona_riesgo_id`, D4). Permite planificar evacuación desde zonas de riesgo hacia albergues. |
| **Módulo 4** | El consolidado EDAN (daño confirmado + necesidades) es la entrada natural para priorizar la asignación de recursos del M5. |
| **Consola admin** (`/admin`) | El superadmin ve los logs de auditoría de las acciones del M5. |

---

## 🛠️ Pendientes / mejoras a futuro

### 🔴 Propios del M5

1. **Historial de asignaciones** — tabla `asignaciones_recursos` (fecha, origen, destino, usuario) para reconstruir la logística completa; hoy solo se guarda el destino actual + auditoría.
2. **Control de ocupación en tiempo real** — registrar cuántas personas hay efectivamente en cada albergue (`ocupacion_actual`) para comparar con `capacidad` y ver el % de uso en el mapa.
3. **Reglas de suficiencia** — cruzar la demanda EDAN (M4) con el inventario (M5) y alertar cuando abrigo/alimento no alcanzan para la población damnificada de una comuna.
4. **Movimientos con bodega de origen** — modelar bodegas además de albergues como destino (maquinaria suele ir a un frente de trabajo, no a un albergue).
5. **Reserva temporal (soft hold)** — marcar recursos como "comprometidos" para un incidente antes de asignarlos físicamente.
6. **Adjuntos** — reutilizar la subida de archivos del M2 para fotos/actas de entrega de recursos.

### 🟡 Transversales (afectan al M5)

7. **Tests de integración** con `httpx.AsyncClient` (pendiente general).
8. **Migrar a PostgreSQL + PostGIS** si el proyecto escala (índice geoespacial para "albergues más cercanos a esta zona").
9. **Mapa público**: además de la capa de albergues, mostrar rutas de evacuación hacia el albergue más cercano (requiere servicios de ruteo).
10. **Estaciones fluviales** (pendiente del M1) podrían convertirse en un catálogo de infraestructura más dentro del inventario del M5.

---

## 📝 Notas de versión

- **v1.0.0 — Versión inicial completa:**
  - Catastro de albergues con servicios, capacidad, estado y mapa.
  - Inventario único de recursos con discriminador de categoría (D3): maquinaria · abrigo · alimento.
  - Asignación logística recurso → albergue con normalización automática de estado.
  - Panel logístico consolidado (albergue ↔ recursos, totales por categoría y capacidad total).
  - Vínculos opcionales a zonas de riesgo (M3) e incidentes (M2) — D4.
  - CRUD completo con edición parcial auditada y soft delete.
  - Endpoint público saneado + capa "Albergues" en el visor ciudadano (M1).
  - `seed_modulo5.py` idempotente (permisos + licencia + 3 albergues y 11 recursos demo).

---

## Conclusión

**Puedes darlo por terminado como MVP.** El Módulo 5 cumple con lo que la especificación pedía:

- ✅ Catastro de albergues con capacidad y servicios para saber dónde refugiarse
- ✅ Inventario logístico de maquinaria, abrigo y alimento en una estructura única y consultable
- ✅ Asignación de recursos a albergues (logística) con estados coherentes
- ✅ Trazabilidad y auditoría (CGR) en todas las operaciones
- ✅ Vínculos opcionales con zonas de riesgo (M3) e incidentes (M2) sin acoplar los módulos (D4)
- ✅ Visor público de albergues para la ciudadanía (Ley 21.364)
- ✅ Determinismo y auditabilidad (sin cajas negras)

Con esto quedan operativos los Módulos 0 a 5 del prototipo GRD Comunal.
