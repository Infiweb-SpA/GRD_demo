# verificar_v2.py
"""Verifica la matriz de amenazas y el estado antes/después del motor v2."""
from app.database import SessionLocal
from app import models
from app.services.modulo3_engine import (
    AMENAZAS_CONFIG, _config_amenaza, _normalizar,
)

db = SessionLocal()

print("=" * 78)
print("1) MATRIZ DE AMENAZAS CARGADA")
print("=" * 78)
for k, cfg in AMENAZAS_CONFIG.items():
    print(f"  {k:22s} → {cfg['nombre']:22s} [{cfg['familia']:5s}]  pesos={cfg['pesos']}")

print()
print("=" * 78)
print("2) MATCH DE AMENAZAS REALES EN BD")
print("=" * 78)
for inc in db.query(models.Incidente).filter(models.Incidente.eliminado == False).all():
    cfg = _config_amenaza(inc.amenaza_tipo)
    estado = "OK  " if cfg else "FALTA"
    familia = cfg["familia"] if cfg else "—"
    print(f"  #{inc.id} '{inc.amenaza_tipo}' → norm='{_normalizar(inc.amenaza_tipo)}' "
          f"[{estado}] familia={familia}")

print()
print("=" * 78)
print("3) ZONAS ACTIVAS ACTUALES (del motor v1, se reemplazarán)")
print("=" * 78)
zonas = db.query(models.ZonaRiesgo).filter(models.ZonaRiesgo.activa == True).all()
for z in zonas:
    print(f"  #{z.id} {z.nombre:28s} sev={z.severidad:7s} | {z.motivo[:70]}...")
print(f"\n  Total zonas activas: {len(zonas)}")

print()
print("→ Reinicia el server y corre test_m3.ps1 para regenerar con el motor v2.")
db.close()