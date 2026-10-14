# Sistema GRD Comunal – Módulo 1: Visor Público y Landing Informativa

## 📌 Estado actual

* **Finalizado** ✅
* Versión: **v1.0.0**
* Dependencias clave: FastAPI, Jinja2, Tailwind CSS, Chart.js, Httpx, SQLite / SQLAlchemy (`AlertaMunicipalActiva`).

## 🗺️ Alcance y Funcionalidades Principales

| Componente | Descripción |
| --- | --- |
| **Landing Page Ciudadana (`/modulo1/landing`)** | Interfaz pública y transparente orientada a la ciudadanía para el monitoreo de las comunas de **Cunco**, **Freire** y **Padre Las Casas**. |
| **Indicadores Climáticos en Tiempo Real** | Consumo dinámico de la API oficial de **Open-Meteo** para temperatura actual, acumulado de agua caída de las últimas 24 horas y ráfagas de viento máximas (`windgusts_10m`). |
| **Gráfico Histórico Dinámico (2015 - 2026)** | Selector temporal que permite consultar y renderizar mediante Chart.js el acumulado mensual de precipitaciones de cualquier año histórico desde el 2015 en adelante. |
| **Gráfico Comparativo Intercomunal** | Gráfico de barras simultáneo que evalúa de forma cruzada el impacto de precipitaciones de las tres comunas controladas en las últimas 24 horas. |
| **Gestión de Alertas Operativas Manuales** | Sistema híbrido de alertas preventivas (ej. tormentas eléctricas o vientos críticos > 70 km/h) registradas por el operador municipal e integradas directamente desde la base de datos local. |
| **Visor Cartográfico Público (`/modulo1/mapa`)** | Vista orientada a la visualización de capas georreferenciadas base (sin herramientas de edición para usuarios públicos). |

## 📡 Endpoints Principales del Módulo 1 (API REST)

| Ruta | Método | Descripción |
| --- | --- | --- |
| `/modulo1/landing` | `GET` | Renderiza la plantilla HTML Jinja2 de la Landing Ciudadana. |
| `/modulo1/mapa` | `GET` | Renderiza el visor cartográfico base. |
| `/api/modulo1/estadisticas` | `GET` | Parámetros: `comuna` y `anio`. Retorna clima actual, agua 24h, ráfagas, efectividad de limpieza, histórico anual y estado de alerta manual activa. |
| `/api/modulo1/comparativa-comunas` | `GET` | Retorna el consolidado multi-comuna de precipitaciones de las últimas 24 horas. |

---

## 🛠️ Siguientes Pasos: Módulo 2

Una vez guardado este documento en tu entorno, podemos avanzar al diseño e implementación del **Módulo 2 (Registro de Incidentes Históricos y Trazabilidad)**, el cual incorporará:

1. Formularios estructurados para funcionarios municipales según la matriz de **SENAPRED**.
2. Integración de **Leaflet Geoman** sobre el mapa de edición para el levantamiento de polígonos y puntos vectoriales en terreno.
3. La estricta tabla de **Logs de Auditoría (Normativa CGR)** para registrar trazabilidad de autor, IPs y timestamps exactos.
4. Funcionalidad de exportación inmediata de capas espaciales a formatos estándar **GeoJSON**.

¿Procedemos a redactar y estructurar el código base del **Módulo 2**?