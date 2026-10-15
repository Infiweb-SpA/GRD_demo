# Sistema GRD Comunal – Módulo 0: Core (Autenticación, Roles y Licenciamiento)

## 📌 Estado actual

- **Finalizado** ✅
- Versión: **v1.1.0** (agregada Consola de Súper Administrador)
- Base de datos: SQLite (archivo `grd.db`)
- Entorno: `.venv` con FastAPI + Uvicorn
- Python: 3.14 (compatible, aunque se recomienda 3.12 para producción)

---

## 📂 Archivos que componen este módulo

| Archivo / Carpeta | Rol dentro del módulo |
| --- | --- |
| `app/routers/auth.py` | Login, logout, resolución de clave temporal, reset por API |
| `app/routers/vistas.py` | Vistas HTML: `/`, `/auth/login`, `/dashboard` |
| `app/routers/permisos.py` | **NUEVO v1.1.0**: CRUD de roles, permisos y usuarios (solo superadmin) |
| `app/templates/auth/login.html` | Formulario de ingreso + modal de cambio de clave |
| `app/templates/dashboard.html` | Hub interno con sidebar dinámico por permisos y licencia |
| `app/templates/permisos/index.html` | **NUEVO v1.1.0**: consola de superadmin (tabs Roles / Usuarios) |
| `app/deps.py` | Dependencias: CSRF, sesión, RBAC, licencias, auditoría |
| `app/models.py` | Tablas `usuarios`, `roles`, `permisos`, `roles_permisos`, `logs_auditoria`, `modulos_licencia` |
| `app/security.py` | Bcrypt, generación de claves temporales, tokens CSRF |
| `app/seed.py` | Datos iniciales: roles, permisos, comunas de prueba, superadmin |
| `app/config.py` | Variables de entorno (SECRET_KEY, sesión, DB URL) |
| `app/main.py` | Punto de entrada, middlewares y registro de routers |
| `app/database.py` | Engine SQLAlchemy, sesión, `init_db()` |

---

## 👥 Usuarios de prueba

| Comuna | Rol Admin | Rol Funcionario | Clave temporal |
| --- | --- | --- | --- |
| **Cunco** | `admin_cunco` | `funcionario_cunco` | `MuniCunco2026!` |
| **Freire** | `admin_freire` | `funcionario_freire` | `MuniFreire2026!` |
| **Padre Las Casas** | `admin_padre_las_casas` | `funcionario_padre_las_casas` | `MuniPadreLasCasas2026!` |

**Superadmin por defecto:** `superadmin` / `Admin@1234`

> Todas las cuentas se crean con `requiere_cambio_clave = True` y obligatoriedad de cambiar o mantener la clave al primer ingreso.

---

## 🔐 Características de seguridad

| Característica | Descripción |
| --- | --- |
| **RBAC** | Tres roles base: `superadmin`, `administrador`, `funcionario`. **Extensible** mediante la consola `/admin` (v1.1.0). |
| **CSRF Tokens** | Toda petición de escritura exige header `X-CSRF-Token` obtenido de `GET /auth/csrf`. |
| **Validación de contraseña** | Flujo "clave temporal → cambio obligatorio". El usuario decide cambiar o mantener. |
| **Licenciamiento por módulo** | Feature flags en tabla `modulos_licencia`. Cada municipio activa módulos según contrato. |
| **Auditoría CGR** | Cada acción de escritura queda en `logs_auditoria` con usuario, IP y timestamp (misma transacción). |
| **Session fixation** | El login limpia la sesión antes de fijar `user_id` y rota el token CSRF. |
| **Auto-protección de superadmin** | No puede auto-degradarse, auto-desactivarse ni auto-eliminarse. |
| **Rol `superadmin` protegido** | No se puede renombrar ni eliminar; siempre conserva TODOS los permisos. |
| **Último superadmin** | No se puede degradar ni eliminar al último superadmin del sistema. |
| **Soft delete de usuarios** | Al eliminar, se marca `activo=False` para preservar trazabilidad de `logs_auditoria`. |

---

## 📡 Endpoints principales (API REST)

### Autenticación

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/api/salud` | GET | 🌐 Público | Estado y versión del servicio. |
| `/auth/csrf` | GET | 🌐 Público | Token CSRF para peticiones posteriores. |
| `/auth/login` | POST | 🌐 Público (CSRF) | Autenticación con clave temporal o definitiva. |
| `/auth/clave/resolver` | POST | 🌐 Público (CSRF) | Cambiar o mantener la clave temporal. |
| `/auth/me` | GET | 🔒 Sesión | Datos del usuario autenticado + permisos + rol. |
| `/auth/logout` | POST | 🔒 CSRF | Cierra sesión. Devuelve `{"redirect": "/modulo1/landing"}`. |
| `/auth/usuarios/{id}/reset-clave` | POST | 🔒 CSRF + `usuarios:gestionar` | Reset de clave para un usuario (soporta `{"comuna": "Cunco"}`). |

### Consola de Súper Administrador (NUEVO v1.1.0)

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/admin` | GET | 🔒 superadmin | Vista HTML con tabs Roles / Usuarios. |
| `/admin/roles` | GET | 🔒 superadmin | Lista roles con permisos y nº de usuarios. |
| `/admin/permisos-disponibles` | GET | 🔒 superadmin | Catálogo completo de permisos del sistema. |
| `/admin/roles` | POST | 🔒 CSRF + superadmin | Crea un rol nuevo con permisos. |
| `/admin/roles/{id}` | PUT | 🔒 CSRF + superadmin | Modifica nombre, descripción y permisos. |
| `/admin/roles/{id}` | DELETE | 🔒 CSRF + superadmin | Elimina un rol (bloqueado si tiene usuarios). |
| `/admin/usuarios` | GET | 🔒 superadmin | Lista usuarios con estado activo e info de clave. |
| `/admin/usuarios` | POST | 🔒 CSRF + superadmin | Crea usuario y **devuelve clave temporal legible**. |
| `/admin/usuarios/{id}` | PUT | 🔒 CSRF + superadmin | Cambia rol y/o estado activo. |
| `/admin/usuarios/{id}` | DELETE | 🔒 CSRF + superadmin | Soft delete (`activo=False`). |
| `/admin/usuarios/{id}/reset-clave` | POST | 🔒 CSRF + superadmin | Regenera clave temporal (se muestra UNA vez). |

### Vistas HTML

| Ruta | Método | Auth | Descripción |
| --- | --- | --- | --- |
| `/` | GET | 🌐 Público | Redirige 303 a `/modulo1/landing`. |
| `/auth/login` | GET | 🌐 Público | Formulario de login. Expulsa a usuarios ya logueados. |
| `/dashboard` | GET | 🔒 Sesión | Hub con sidebar dinámico por permisos y licencia. |

---

## 🗂️ Estructura de tablas SQL

### Tabla `usuarios`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `username` | String(50) | Único, indexado |
| `password_hash` | String(255) | Bcrypt (12 rounds) |
| `role_id` | Integer FK | → `roles.id`, `RESTRICT` |
| `requiere_cambio_clave` | Boolean | Default `False` |
| `activo` | Boolean | Default `True` |
| `creado_en` | DateTime | UTC |

### Tabla `roles`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `nombre` | String(50) | Único (`superadmin`, `administrador`, `funcionario`, + personalizados) |
| `descripcion` | String(255) | Opcional |

### Tabla `permisos`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `codigo` | String(100) | Único (ej. `reportes:leer`, `logs:ver`) |
| `descripcion` | String(255) | Opcional |

### Tabla `roles_permisos` (N:M)

| Columna | Tipo |
| --- | --- |
| `role_id` | Integer FK → `roles.id` |
| `permiso_id` | Integer FK → `permisos.id` |

### Tabla `logs_auditoria`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `usuario_id` | Integer FK | → `usuarios.id`, `SET NULL` |
| `accion_realizada` | String(255) | Texto descriptivo |
| `tabla_afectada` | String(100) | Ej: `incidentes_reportes` |
| `registro_id` | Integer | ID del registro afectado |
| `direccion_ip` | String(45) | IPv4/IPv6 |
| `fecha_hora` | DateTime | UTC, indexado |

### Tabla `modulos_licencia`

| Columna | Tipo | Notas |
| --- | --- | --- |
| `id` | Integer PK | |
| `codigo` | String(50) | Único (`modulo_0` ... `modulo_4`) |
| `nombre` | String(100) | |
| `activo` | Boolean | Default `False` |

---

## 🎯 Decisiones de diseño

- **Rol `superadmin` inmutable**: no se puede renombrar ni eliminar. Siempre tiene todos los permisos.
- **Soft delete de usuarios**: al eliminar, se marca `activo=False` para preservar trazabilidad en `logs_auditoria`.
- **Rol no eliminable si tiene usuarios**: evita registros huérfanos por FK `RESTRICT`.
- **Claves temporales one-shot**: el backend las devuelve una sola vez; el frontend las muestra en un modal con `select-all`.
- **Logout devuelve redirect**: el backend decide el destino (`/modulo1/landing`), el frontend lo respeta.
- **Mini-migrador idempotente** en `seed.py`: agrega columnas nuevas sin Alembic ni pérdida de datos.
- **Normalización de nombres de rol**: los espacios se convierten en guiones bajos automáticamente.

---

## 🛠️ Pendientes / próximos pasos

1. **Rol COGRID** (Comité de Gestión del Riesgo de Desastres):
   - Crear rol `cogrid` con permiso `alertas:emitir`.
   - Conectar tabla `alertas_municipales_activas` a la landing del Módulo 1.
   - Reemplazar la lista hardcodeada `ALERTAS_INTERNAS` en `modulo1.py`.
2. **Paginación de logs de auditoría** en la consola de superadmin (actualmente limitada a 100 eventos en Módulo 2).
3. **Doble confirmación** para acciones destructivas (eliminar rol con usuarios, resetear clave del superadmin).
4. **Tests de integración** con `httpx.AsyncClient` contra el servidor real.
5. **Despliegue en Railway** con variables de entorno (`SECRET_KEY`, `DATABASE_URL`, `ENVIRONMENT=production`).
6. **Migrar a PostgreSQL + PostGIS** cuando el proyecto escale más allá del prototipo municipal.

---

## 🧪 Pruebas rápidas

```bash
# 1) Estado del servicio
curl http://localhost:8000/api/salud

# 2) CSRF y login
curl -c cookies.txt http://localhost:8000/auth/csrf
curl -b cookies.txt -c cookies.txt -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -H "X-CSRF-Token: <token>" \
     -d '{"username":"superadmin","password":"Admin@1234"}'

# 3) Info del usuario autenticado
curl -b cookies.txt http://localhost:8000/auth/me | jq

# 4) Listar roles como superadmin
curl -b cookies.txt http://localhost:8000/admin/roles | jq

# 5) Verificar tabla de licencias
sqlite3 grd.db "SELECT codigo, activo FROM modulos_licencia;"