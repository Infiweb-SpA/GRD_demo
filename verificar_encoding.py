# verificar_encoding.py
from app.database import SessionLocal
from app import models

db = SessionLocal()
z = db.query(models.ZonaRiesgo).first()
print("=== repr() del motivo (crudo en BD) ===")
print(repr(z.motivo))
print()
print("=== print() normal ===")
print(z.motivo)
print()
print("=== ¿Contiene la palabra 'Inundación' correctamente? ===")
print("Inundación" in z.motivo)
db.close()