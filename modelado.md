# Especificación de Requisitos y Arquitectura: Sistema GRD Comunal v1.0

Este documento define la estructura modular, las vistas de usuario y los requerimientos funcionales y legales para el desarrollo del prototipo del Sistema de Gestión del Riesgo de Desastres (GRD) Comunal utilizando **FastAPI** y **SQLite + SpatiaLite** para su despliegue en **Railway**.

---

## 1. Módulos del Sistema (Estructura ERP Desacoplada)

El sistema está diseñado de forma modular, permitiendo activar o desactivar componentes comerciales mediante variables de licenciamiento (*Feature Flags*) en la base de datos.

### 📦 Módulo 0: Autenticación, Roles y Licenciamiento (CORE - OBLIGATORIO)
*   **Descripción:** Motor de seguridad y gestión de accesos.
*   **Dependencia:** Ninguna.
*   **Funcionalidades:**
    *   Control de Accesos Basado en Roles (RBAC).
    *   Validación de seguridad mediante **CSRF Tokens** en todas las peticiones de escritura.
    *   Gestión de contraseñas administrativas (Flujo sin correo): el Administrador genera una clave temporal por defecto. Al iniciar sesión, el sistema solicita obligatoriamente el cambio de contraseña al funcionario o permite mantenerla.
    *   Habilitador de módulos contratados por el municipio.

### 📦 Módulo 1: Visor Público y Landing Informativa (Comercial 1)
*   **Descripción:** Interfaz ciudadana transparente y de libre acceso.
*   **Dependencia:** Independiente.
*   **Funcionalidades:**
    *   Renderizado del mapa base en Leaflet.
    *   Consumo en tiempo real de alertas climáticas (Open-Meteo).
    *   Visualización de gráficos analíticos generales y consolidados del estado de la comuna.

### 📦 Módulo 2: Registro de Incidentes Históricos y Trazabilidad (Comercial 2)
*   **Descripción:** Bitácora digital pos-terreno para funcionarios municipales.
*   **Dependencia:** Módulo 0.
*   **Funcionalidades:**
    *   Ingreso alfanumérico y espacial de incidentes recopilados en zonas rurales/urbanas.
    *   Herramientas de dibujo vectorial sobre el mapa base (Leaflet Geoman).
    *   **Registro de Logs (Auditoría Legal):** Tabla estricta que almacena qué funcionario creó, modificó o eliminó un dato, junto con su *Timestamp* exacto y dirección IP.
    *   **Exportación de Datos:** Botón para descargar de forma inmediata los polígonos e incidentes en formato estándar **GeoJSON** para ser entregados a SENAPRED, Ministerios o la IDE Chile.

### 📦 Módulo 3: Inteligencia Predictiva de Zonas de Riesgo (Comercial 3)
*   **Descripción:** Generación automática de polígonos de peligro basados en datos empíricos.
*   **Dependencia:** Módulo 2 (Requiere la data histórica del Módulo 2).
*   **Funcionalidades:**
    *   Algoritmo que intersecta temporalidad, mm de lluvia acumulada y recurrencia geográfica.
    *   Consolidación y proyección automática en el mapa público de "Zonas de Riesgo Oficiales" bajo los estándares de la Ley 21.364 de Chile.

### 📦 Módulo 4: Análisis de Vulnerabilidad Socioeconómica (Comercial 4)
*   **Descripción:** Cruce de datos demográficos y geoespaciales.
*   **Dependencia:** Módulo 2 o Módulo 3.
*   **Funcionalidades:**
    *   Conexión a endpoints de CKAN o almacenamiento censal local.
    *   Cálculo automático de población e infraestructura crítica (escuelas, postas rurales) expuesta dentro de los polígonos de riesgo dibujados.

---

## 2. Definición de Vistas del Frontend (Interfaz de Usuario)

El sistema se compone de **5 vistas principales** implementadas en plantillas Jinja2 (HTML5 + Tailwind CSS).

### Vista 1: Landing Page Informativa (`/`)
*   **Acceso:** Todo público (Sin credenciales).
*   **Propósito:** Canal de comunicación oficial hacia el ciudadano.
*   **Elementos Visuales:**
    *   Sección de bienvenida y estado de alertas comunales activas.
    *   **Gráficos Estadísticos Generales:** Gráficos de barras o circulares (renderizados en el cliente mediante *Chart.js*) que muestran métricas simples, tales como: cantidad de incidentes reportados en el mes, mm de agua caídos en las últimas 24 horas y porcentaje de efectividad de limpieza de canales.
    *   Acceso directo al Visor Cartográfico Ciudadano.

### Vista 2: Visor Cartográfico Público (`/mapa`)
*   **Acceso:** Todo público (Sin credenciales).
*   **Propósito:** Visualización geográfica del riesgo en tiempo real.
*   **Elementos Visuales:**
    *   Mapa de Leaflet a pantalla completa.
    *   Capas conmutables (Zonas de riesgo consolidadas, estaciones fluviales de la comuna).
    *   Bloqueo automático de cualquier herramienta de edición o dibujo.

### Vista 3: Portal de Autenticación (`/auth/login`)
*   **Acceso:** Todo público.
*   **Propósito:** Validación de funcionarios.
*   **Flujo Especial de Credenciales:**
    *   Si el usuario ingresa por primera vez con la clave temporal asignada por el Súper Admin, la vista renderiza un formulario emergente obligatorio: `"Cambiar contraseña o Mantener clave actual"`.
    *   Contiene protección nativa contra ataques CSRF.

### Vista 4: Panel de Gestión ERP Municipal (`/dashboard`)
*   **Acceso:** Solo Funcionarios y Administradores Autenticados.
*   **Propósito:** Centro operativo del sistema.
*   **Elementos Visuales:**
    *   Barra lateral de módulos dinámicos (los botones se ocultan o bloquean con un candado si el municipio no ha contratado el módulo o si el usuario no posee el permiso en su rol).
    *   **Sección de Reportes:** Formulario estructurado según la matriz de SENAPRED para formalizar los incidentes levantados en terreno (subida de imágenes, campo de descripción, coordenadas).
    *   **Mapa de Edición:** Activa Leaflet Geoman para que el funcionario dibuje el área de afectación rural/urbana.
    *   Botón de **Exportación de Datos**: Descarga de archivos comprimidos con el `JSON/GeoJSON` de las capas espaciales de la comuna.

### Vista 5: Consola de Súper Administrador (`/admin`)
*   **Acceso:** Exclusivo para el rol `superadmin`.
*   **Propósito:** Control del ecosistema e infraestructura del software.
*   **Elementos Visuales:**
    *   **Gestor de Usuarios:** Listado de funcionarios municipales. Botón de `"Reiniciar Contraseña"` que genera un string aleatorio legible (ej: `MuniTemuco2026!`) para entregárselo directamente al usuario por canales internos del municipio en caso de olvido.
    *   **Matriz de Permisos:** Configuración fina de lectura/escritura por rol.
    *   **Sección de Logs e Historial (Auditoría CGR):** Tabla de visualización de registros de eventos del sistema. Permite filtrar y auditar de la siguiente forma: `[Fecha/Hora] | [Usuario: j.perez] | [Acción: Modificó Polígono ID 45] | [IP: 192.168.1.50]`.

---

## 3. Matriz de Trazabilidad de Base de Datos (Estructura de Tablas en SQLite)

Para dar soporte a los requerimientos de auditoría legal chilena y la flexibilidad de claves, los esquemas relacionales base de SQLite se diseñan bajo la siguiente lógica estructural:

### Tabla: `usuarios`
*   `id` (Integer, PK)
*   `username` (String, Único)
*   `password_hash` (String)
*   `role_id` (Integer, FK)
*   `requiere_cambio_clave` (Boolean, por defecto `True` cuando el admin la resetea)

### Tabla: `incidentes_reportes`
*   `id` (Integer, PK)
*   `amenaza_tipo` (String) -> *Bajo catálogo oficial SENAPRED*
*   `comentario` (Text)
*   `geojson_geometria` (Text) -> *Almacena el polígono o punto WGS84*
*   `creado_por_id` (Integer, FK -> `usuarios.id`)
*   `fecha_creacion` (Timestamp)

### Tabla: `logs_auditoria` (Requisito de Normativa Municipal)
*   `id` (Integer, PK)
*   `usuario_id` (Integer, FK -> `usuarios.id`)
*   `accion_realizada` (String) -> *Ej: "Modificó geometría del reporte #12"*
*   `tabla_afectada` (String) -> *Ej: "incidentes_reportes"*
*   `registro_id` (Integer)
*   `direccion_ip` (String)
*   `fecha_hora` (Timestamp)
