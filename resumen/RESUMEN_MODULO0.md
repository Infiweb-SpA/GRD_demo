# Sistema GRD Comunal – Módulo 0: Core (Autenticación, Roles y Licenciamiento)

## 📌 Estado actual
- **Finalizado** ✅
- Versión: **v1.0.0**
- Base de datos: SQLite + SpatiaLite (archivo `grd.db`)
- Entorno: `.venv` con FastAPI + Uvicorn

## 👥 Usuarios de prueba (3 comunas)

| Comuna      | Rol Admin          | Rol Funcionario   | Clave temporal |
|-------------|-------------------|-------------------|----------------|
| **Cunco**   | `admin_cunco`     | `funcionario_cunco` | `MuniCunco2026!` |
| **Freire**  | `admin_freire`    | `funcionario_freire` | `MuniFreire2026!` |
| **Padre Las Casas** | `admin_padre_las_casas` | `funcionario_padre_las_casas` | `MuniPadreLasCasas2026!` |

> Todas las cuentas tienen `requiere_cambio_clave = True` y obligatoriedad de cambiar la clave al primer ingreso.

## 🔐 Características de seguridad

| Característica | Descripción |
|----------------|-------------|
| **RBAC** | Tres roles: `superadmin`, `administrador`, `funcionario`. Los permisos se asignan por rol y pueden consultarse vía `/auth/me`. |
| **CSRF Tokens** | Cada petición de escritura debe incluir el header `X‑CSRF‑Token` obtenido de `GET /auth/csrf`. |
| **Validación de contraseña** | Flujo “clave temporal → cambio obligatorio”. El admin puede resetear clave y el usuario debe aceptarla o cambiarla. |
| **Habilitador de módulos** | Bandera en BD (`feature_flags`) para activar/desactivar módulos comerciales (1‑4). |

## 📡 Endpoints principales (API REST)

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/salud` | `GET` | Estado y versión del servicio. |
| `/auth/csrf` | `GET` | Obtiene token CSRF para peticiones posteriores. |
| `/auth/login` | `POST` | Autenticación (acepta clave temporal y definitiva). |
| `/auth/clave/resolver` | `POST` | Resolver cambio/ mantención de clave. |
| `/auth/me` | `GET` | Devuelve datos del usuario autenticado + permisos. |
| `/auth/logout` | `POST` | Cierra la sesión y invalida el token. |
| `/auth/usuarios/{id}/reset-clave` | `POST` | Reset de clave para otra comuna (ej. `{"comuna":"Cunco"}`). |

## 🗂️ Estructura de tablas SQL (SQLite + SpatiaLite)

| Tabla | Columnas relevantes |
|-------|----------------------|
| `usuarios` | `id`, `username`, `password_hash`, `role_id`, `requiere_cambio_clave` |
| `incidentes_reportes` | `id`, `amenaza_tipo`, `comentario`, `geojson_geometria`, `creado_por_id`, `fecha_creacion` |
| `logs_auditoria` | `id`, `usuario_id`, `accion_realizada`, `tabla_afectada`, `registro_id`, `direccion_ip`, `fecha_hora` |
| `roles` | `id`, `nombre` (superadmin, administrador, funcionario) |
| `permisos` | `id`, `rol_id`, `recurso`, `acción` (ej. `exportar:datos`, `logs:ver`) |
| `feature_flags` | `modulo`, `activo` (para licenciamiento por comuna) |

## 🛠️ Próximos pasos (fuera del alcance del Módulo 0)

1. **Módulo 1 – Visor Público y Landing** (Comercial 1): mapas Leaflet, gráficos Chart.js, consumo de API Open‑Meteo.  
2. **Pruebas de integración** con `httpx.AsyncClient` contra el servidor real en Railway.  
3. **Despliegue** en Railway con variables de entorno y configuración de SpatiaLite.