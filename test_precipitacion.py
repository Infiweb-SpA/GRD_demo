# test_precipitacion.py
"""Verifica que _fetch_precipitacion devuelve datos para fechas recientes."""
from datetime import date, timedelta
from app.services.modulo3_engine import _fetch_precipitacion

comunas = ["Cunco", "Freire", "Padre Las Casas"]

# Probamos 3 ventanas: hace 1 día, hace 5 días, hace 60 días
for offset in (1, 5, 60):
    centro = date.today() - timedelta(days=offset)
    ini = centro - timedelta(days=3)
    fin = centro + timedelta(days=3)
    print(f"\n=== Ventana centrada hace {offset} días ({ini} → {fin}) ===")
    for c in comunas:
        p = _fetch_precipitacion(c, ini, fin)
        total = sum(p.values())
        print(f"  {c:18s} → {len(p)} días, total {total:.2f} mm")