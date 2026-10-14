# Sistema GRD Comunal – Módulo 2: Registro de Incidentes y Trazabilidad

## 📌 Estado actual

* **Completo y operativo** ✅
* Versión: **v1.0.0**
* Dependencias clave: FastAPI · SQLAlchemy · Jinja2 · Tailwind CSS (CDN) ·
  Leaflet 1.9.4 (sin Geoman) · SQLite.
* **Decisión de diseño relevante:** se reemplazó Leaflet-Geoman por **dibujo
  manual con Leaflet puro** para soportar el flujo *clic-izq arma / clic-der
  dibuja* solicitado. Geoman no ofrece ese patrón de forma nativa.

---

## 🎯 Alcance y funcionalidades implementadas

| Componente | Descripción |
| --- | --- |
| **Vista de Reportes (`/modulo2/reportes`)** | Panel operativo para funcionarios autenticados con permisos `reportes:leer` y `reportes:escribir`. Layout de 2 columnas: mapa vectorial + formulario de registro. |
| **Formulario estructurado SENAPRED** | Selector con catálogo oficial (Inundación, Deslizamiento, Incendio Forestal, Temporal, Terremoto, Erupción Volcánica, Ola de Calor, Sequía) + comentario libre. |
| **Dibujo vectorial manual** | Flujo clic-izq arma → clic-der dibuja. Soporta **Punto**, **Línea** y **Polígono**. Clic-der cierra el trazado; **Esc** o botón Cancelar aborta. Feedback visual por banner + resaltado del botón activo + contador de vértices. |
| **Serialización GeoJSON** | Salida `{"type":"Point|LineString|Polygon","coordinates":[...]}` con precisión WGS84 (7 decimales). Se vuelca al `<textarea>` readonly antes de guardar. |
| **Subida de imágenes** | Hasta N archivos JPG/PNG/WebP por incidente, máx 5 MB c/u. Se almacenan en `static/uploads/incidentes/{id}/` con nombres UUID. Se pueden añadir **al crear** y **al editar**. |
| **Tabla de incidentes** | Listado con ID, tipo, comentario, fecha, número de imágenes y acciones (Editar / Eliminar). Clic en fila abre el modal de detalle. |
| **Modal de detalle** | Muestra tipo de amenaza, fecha, comentario, geometría (JSON pretty-print) y galería de imágenes. Clic sobre una imagen → **lightbox** a pantalla completa. |
| **Edición de incidentes** | Modifica tipo, comentario y añade imágenes nuevas. Cada cambio queda auditado con el detalle de qué campos cambiaron. |
| **Eliminación lógica (soft delete)** | Marca `eliminado=True`. El registro sigue en BD para trazabilidad y auditoría, pero se oculta del mapa, la tabla y el visor público. |
| **Auditoría legal (Normativa CGR)** | Registra quién hizo qué, cuándo y desde qué IP. **Cada acción va en la misma transacción** que la operación: crear, editar, adjuntar imágenes, eliminar. |
| **Visor de logs** | Tabla con los últimos 100 eventos (fecha, usuario, acción, IP). |
| **Exportación GeoJSON** | `GET /api/modulo2/exportar-datos` → archivo `incidentes_grd.geojson` con `Content-Disposition: attachment`. Excluye incidentes eliminados. |
| **Integración con Módulo 1** | Endpoint público `GET /api/modulo1/incidentes-publicos` sirve los incidentes al visor ciudadano. Capa conmutable "Incidentes Históricos" con popups e imágenes. |
| **Botón de cierre de sesión** | En el header. Llama a `POST /auth/logout` con CSRF y redirige a `/auth/login`. |
| **Panel intermedio `/dashboard`** | Nuevo hub con sidebar de módulos filtrados por permiso y licencia. Todos los logins aterrizan aquí en vez de ir directo a `/modulo2/reportes`. |

---

## 📡 Endpoints del Módulo 2

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/modulo2/reportes` | GET | 🔒 `modulo_2` + `reportes:leer` | Vista HTML con mapa, formulario y tabla. |
| `/api/modulo2/incidentes` | GET | 🔒 `modulo_2` + `reportes:leer` | Incidentes no eliminados como `FeatureCollection` con `imagenes`. |
| `/api/modulo2/incidentes` | POST | 🔒 CSRF + `modulo_2` + `reportes:escribir` | Crea un incidente y su log de auditoría. |
| `/api/modulo2/incidentes/{id}` | PUT | 🔒 CSRF + `modulo_2` + `reportes:escribir` | Edita tipo, comentario y/o geometría. Registra el diff en auditoría. |
| `/api/modulo2/incidentes/{id}` | DELETE | 🔒 CSRF + `modulo_2` + `reportes:escribir` | Soft delete (`eliminado=True`). Registra en auditoría. |
| `/api/modulo2/incidentes/{id}/imagenes` | POST | 🔒 CSRF + `modulo_2` + `reportes:escribir` | Sube 1..N imágenes `multipart/form-data`. Devuelve la lista de URLs. |
| `/api/modulo2/exportar-datos` | GET | 🔒 `modulo_2` + `exportar:datos` | Descarga `incidentes_grd.geojson`. |
| `/api/modulo2/logs-auditoria` | GET | 🔒 `modulo_2` + `logs:ver` | Últimos 100 eventos de auditoría. |

### Endpoints modificados en el Módulo 1

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/modulo1/incidentes-publicos` | GET | 🌐 Público | Sirve los incidentes vigentes al visor ciudadano. **No expone** autor, IP ni ids internos de usuario. |
| `/auth/login` | GET | 🌐 Público | Ahora expulsa a usuarios ya logueados con `RedirectResponse 303`. |
| `/dashboard` | GET | 🔒 Sesión activa | Nuevo hub con sidebar dinámico por permisos y licencia. |

---

## 🗂️ Modelo de datos involucrado

### Tabla `incidentes_reportes`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `amenaza_tipo` | String(100) | Catálogo SENAPRED |
| `comentario` | String(1000) | Libre |
| `geojson_geometria` | Text | GeoJSON serializado |
| `imagenes` | Text | JSON con la lista de URLs. Default `'[]'` |
| `eliminado` | Boolean | Soft delete. Default `0` |
| `creado_por_id` | Integer FK | → `usuarios.id` |
| `fecha_creacion` | DateTime UTC | |

> **Nota:** las columnas `imagenes` y `eliminado` fueron añadidas en la
> iteración actual mediante un **mini-migrador idempotente** embebido en
> `app/seed.py` (`_migrar_esquema()`), que ejecuta `ALTER TABLE ... ADD COLUMN`
> cuando detecta columnas faltantes. No requiere Alembic y no pierde datos.

### Tabla `logs_auditoria` (fuente: Módulo 0)

Se reutiliza sin cambios. Cada acción agrega una fila con
`tabla_afectada = "incidentes_reportes"` y `registro_id = <id del incidente>`.

Acciones auditadas actualmente:
- `Creó incidente #N - <amenaza>`
- `Modificó incidente #N (amenaza X → Y, comentario, geometría)`
- `Adjuntó N imagen(es) al incidente #N`
- `Eliminó incidente #N - <amenaza>`

---

## 🖥️ Vistas HTML

### `templates/modulo2/reportes.html`

- **Header**: nombre de usuario, rol, enlace a `/dashboard` y botón **Cerrar sesión**.
- **Columna izquierda (2/3)**: mapa Leaflet + botones **Punto / Línea / Polígono / Cancelar** + banner de estado dinámico.
- **Columna derecha (1/3)**: formulario de creación con amenaza, comentario, `<textarea>` de GeoJSON (readonly), input de imágenes múltiple y botones **Guardar** / **Exportar**.
- **Tabla de incidentes**: ID, tipo, comentario, fecha, número de imágenes, acciones. Clic en fila abre el detalle.
- **Modal de edición**: tipo, comentario, miniaturas de imágenes actuales, input de nuevas imágenes.
- **Modal de detalle**: comentario completo, geometría JSON pretty-print, galería de imágenes.
- **Lightbox**: previsualización de imagen a pantalla completa con Esc / clic-fuera para cerrar.
- **Tabla de logs de auditoría** al pie.

### `templates/dashboard.html` (nuevo)

- Header con usuario y logout.
- **Sidebar** con los 3 módulos comerciales. Cada tarjeta se muestra:
  - ✅ Habilitado si `licencia activa AND permiso del rol`.
  - 🔒 Bloqueado si falta cualquiera de los dos, con tooltip explicando cuál.
- Tarjetas resumen con acceso directo a cada módulo.

### `templates/modulo1/mapa.html` (modificado)

- Nuevo `layerGroup` `capaIncidentes`.
- Render con `L.geoJSON()`: puntos → `circleMarker` púrpura; líneas y polígonos con estilo púrpura translúcido.
- Popup con tipo, comentario, fecha e imágenes (máx 3 miniaturas).
- Checkbox **Incidentes Históricos** funcional (antes decorativo).

---

## 🔐 Seguridad y cumplimiento

| Aspecto | Estado |
| --- | --- |
| **CSRF** | Toda escritura exige header `X-CSRF-Token` obtenido de `GET /auth/csrf`. Incluye subida de imágenes. |
| **RBAC** | Cada ruta valida el permiso correspondiente (`reportes:leer`, `reportes:escribir`, `exportar:datos`, `logs:ver`). |
| **Feature flag** | `requiere_modulo("modulo_2")` bloquea el acceso si el municipio no contrató el módulo. |
| **Auditoría CGR** | Cada acción deja rastro en `logs_auditoria` dentro de la misma transacción que el cambio. |
| **Soft delete** | El borrado lógico preserva el histórico auditable y evita romper integridad referencial. |
| **Validación de archivos** | Whitelist `{image/jpeg, image/png, image/webp}` y límite de 5 MB por archivo. |
| **Exposición pública** | El endpoint del visor ciudadano no expone autor, IP ni identificadores internos. |
| **Autoría del registro** | `creado_por_id` se toma siempre de la sesión, **nunca del payload** del cliente. |
| **Session fixation** | El login limpia la sesión antes de fijar el `user_id` y rota el token CSRF. |
| **Expulsión de usuarios logueados** | `GET /auth/login` con sesión activa redirige 303 a `/dashboard` o `/auth/clave/resolver`. |

---

## 🧪 Pruebas manuales sugeridas

```bash
# 1) Endpoint público: FeatureCollection con los incidentes vigentes
curl http://localhost:8000/api/modulo1/incidentes-publicos | jq

# 2) Autenticación exigida en endpoints privados
curl -i http://localhost:8000/api/modulo2/incidentes        # → 401

# 3) Exportación como adjunto
curl -i -b cookies.txt http://localhost:8000/api/modulo2/exportar-datos

# 4) Verificar migración SQLite
sqlite3 grd.db "PRAGMA table_info(incidentes_reportes);"
# Debe incluir: imagenes | eliminado