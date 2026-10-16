# GRD_demo
prototipo escalable de plataforma a escala comunal de gestión de riesgo y desastre

## Módulos

| Módulo | Estado | Vista |
| --- | --- | --- |
| 0 — Seguridad, RBAC, auditoría, licencias | ✅ Operativo | `/admin`, `/permisos` |
| 1 — Visor público + alertas municipales | ✅ Operativo | `/modulo1/mapa` |
| 2 — Reporte de incidentes georreferenciados | ✅ Operativo | `/modulo2/reportes` |
| 3 — Inteligencia predictiva de zonas de riesgo | ✅ Operativo | `/modulo3/zonas` |
| 4 — Vulnerabilidad + Ficha EDAN (SENAPRED) | ✅ Operativo | `/modulo4/vulnerabilidad`, `/modulo4/edan` |
| 5 — Albergues y logística | ✅ Operativo | `/modulo5/albergues`, `/modulo5/recursos` |

Cada módulo tiene su detalle en `resumen/RESUMEN_MODULO<N>.md`.

## Arranque rápido

```bash
# 1) Arrancar el servidor (crea tablas y datos base, idempotente)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 2) Habilitar un módulo en una BD existente (idempotente, una sola vez)
python seed_modulo3.py
python seed_modulo4.py
python seed_modulo5.py

# 3) Entrar con el superadmin por defecto: superadmin / Admin@1234
```
