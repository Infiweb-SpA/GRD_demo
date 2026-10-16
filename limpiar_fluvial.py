"""Limpia la tabla de datos fluviales para forzar un backfill limpio."""
import sqlite3

con = sqlite3.connect("grd.db")
cur = con.cursor()

# 1) ¿Qué tablas existen?
tablas = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]
print("Tablas en grd.db:")
for t in tablas:
    print(f"  - {t}")

# 2) ¿Existen las tablas del Módulo 3?
faltan = [t for t in ("datos_fluviales_historicos", "zonas_riesgo") if t not in tablas]
if faltan:
    print(f"\n[!] FALTAN tablas: {faltan}")
    print("    → El modelo no se cargó bien en models.py. Reinicia el server.")
else:
    print("\n[OK] Ambas tablas del Módulo 3 existen.")

# 3) Si existe, limpiar
if "datos_fluviales_historicos" in tablas:
    n = cur.execute("SELECT COUNT(*) FROM datos_fluviales_historicos").fetchone()[0]
    cur.execute("DELETE FROM datos_fluviales_historicos")
    con.commit()
    print(f"[OK] {n} registros eliminados de datos_fluviales_historicos.")

con.close()