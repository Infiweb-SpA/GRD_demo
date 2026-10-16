# seed_modulo5.py
"""
Habilita el Módulo 5 (Albergues y Logística) en una BD existente (idempotente).

Ejecutar UNA VEZ desde la raíz del proyecto:
    (.venv) PS> python seed_modulo5.py

Qué hace:
  1. Crea los permisos albergues:leer/escribir y recursos:leer/escribir.
  2. Los asigna a los roles superadmin, administrador y funcionario.
     NOTA: app/seed.py solo asigna permisos a roles NUEVOS, por lo que en una
     BD ya existente hay que agregarlos explícitamente (mismo motivo por el
     que existen seed_modulo3.py y seed_modulo4.py).
  3. Crea/activa la licencia 'modulo_5'.
  4. Si las tablas albergues / recursos_inventario están vacías, siembra datos
     de demostración (3 albergues, uno por comuna, y un inventario variado).

Se puede correr varias veces sin efectos duplicados.
"""

from app.database import SessionLocal, init_db
from app import models


PERMISOS_M5 = [
    ("albergues:leer",    "Ver el catastro de albergues y su capacidad"),
    ("albergues:escribir", "Crear, editar y desactivar albergues"),
    ("recursos:leer",     "Ver el inventario de recursos logísticos"),
    ("recursos:escribir", "Crear, editar, asignar y dar de baja recursos"),
]

ASIGNACION = {
    "superadmin":    ["albergues:leer", "albergues:escribir", "recursos:leer", "recursos:escribir"],
    "administrador": ["albergues:leer", "albergues:escribir", "recursos:leer", "recursos:escribir"],
    # El funcionario de terreno gestiona el inventario y consulta albergues,
    # pero no modifica el catastro (lo administra el nivel central).
    "funcionario":   ["albergues:leer", "recursos:leer", "recursos:escribir"],
}

# --- Datos de demostración ---
# (nombre, comuna, direccion, lat, lon, capacidad, estado,
#  agua, luz, sanitarios, cocina, internet, contacto_nombre, contacto_telefono)
ALBERGUES_DEMO = [
    ("Escuela Municipal Cunco", "Cunco", "Av. Alemania 450", -38.9328, -72.0320, 120,
     "activo", True, True, True, True, False, "María Soto", "+56 45 211 3344"),
    ("Gimnasio Municipal Freire", "Freire", "Calle Prat 210", -38.9530, -72.6270, 200,
     "activo", True, True, True, True, True, "Pedro Ramírez", "+56 45 233 1188"),
    ("Liceo Bicentenario Padre Las Casas", "Padre Las Casas", "Camino Viejo 1500", -38.7674, -72.5956, 180,
     "activo", True, True, True, False, True, "Carolina Muñoz", "+56 45 255 9001"),
]

# (nombre, categoria, cantidad, unidad, estado, comuna, notas)
RECURSOS_DEMO = [
    # Maquinaria
    ("Retroexcavadora",     "maquinaria", 2,  "unidades", "disponible", "Cunco",           "Municipal, operativa"),
    ("Camión aljibe",       "maquinaria", 1,  "unidades", "disponible", "Freire",          "Capacidad 10.000 L"),
    ("Generador eléctrico", "maquinaria", 3,  "unidades", "disponible", "Padre Las Casas", "Bencina, 5 kVA"),
    ("Motobomba",           "maquinaria", 4,  "unidades", "mantencion", "Cunco",           "Una en reparación"),
    # Abrigo
    ("Frazadas",            "abrigo",   400,  "unidades", "disponible", "Cunco",           ""),
    ("Colchonetas",         "abrigo",   250,  "unidades", "disponible", "Freire",          ""),
    ("Carpas familiares",   "abrigo",    40,  "unidades", "disponible", "Padre Las Casas", ""),
    ("Ropa de abrigo",      "abrigo",   300,  "unidades", "disponible", "Freire",          "Tallas mixtas"),
    # Alimento
    ("Agua embotellada",    "alimento", 1200, "litros",   "disponible", "Cunco",           ""),
    ("Raciones de alimento","alimento", 500,  "cajas",    "disponible", "Padre Las Casas", "No perecible"),
    ("Kits de aseo",        "alimento", 200,  "kits",     "disponible", "Freire",          ""),
]


def main() -> None:
    # Crea las tablas que falten (albergues, recursos_inventario) en una BD
    # existente, para que el script funcione sin depender de haber arrancado
    # el servidor antes. create_all es idempotente (solo crea las ausentes).
    init_db()

    db = SessionLocal()
    try:
        # 1) Permisos (idempotente)
        for codigo, desc in PERMISOS_M5:
            if not db.query(models.Permiso).filter_by(codigo=codigo).first():
                db.add(models.Permiso(codigo=codigo, descripcion=desc))
                print(f"[+] Permiso creado:   {codigo}")
        db.commit()

        # 2) Asignar permisos a roles existentes
        for nombre_rol, permisos in ASIGNACION.items():
            rol = db.query(models.Rol).filter_by(nombre=nombre_rol).first()
            if not rol:
                print(f"[!] Rol '{nombre_rol}' no existe — omitido")
                continue
            for codigo in permisos:
                permiso = db.query(models.Permiso).filter_by(codigo=codigo).first()
                if permiso and permiso not in rol.permisos:
                    rol.permisos.append(permiso)
                    print(f"[+] {nombre_rol:14s} <- {codigo}")
        db.commit()

        # 3) Licencia del módulo
        lic = db.query(models.ModuloLicencia).filter_by(codigo="modulo_5").first()
        if not lic:
            db.add(models.ModuloLicencia(
                codigo="modulo_5",
                nombre="Albergues y Logística",
                activo=True,
            ))
            print("[+] Licencia 'modulo_5' creada y ACTIVA")
        elif not lic.activo:
            lic.activo = True
            print("[+] Licencia 'modulo_5' reactivada")
        else:
            print("[=] Licencia 'modulo_5' ya estaba activa")
        db.commit()

        # 4) Albergues de demostración (solo si la tabla está vacía)
        if db.query(models.Albergue).count() == 0:
            for (nom, com, dir_, lat, lon, cap, est,
                 agua, luz, sanit, cocina, internet, cnom, ctel) in ALBERGUES_DEMO:
                db.add(models.Albergue(
                    nombre=nom, comuna=com, direccion=dir_, lat=lat, lon=lon,
                    capacidad=cap, estado=est,
                    srv_agua_potable=agua, srv_electricidad=luz, srv_sanitarios=sanit,
                    srv_cocina=cocina, srv_internet=internet,
                    contacto_nombre=cnom, contacto_telefono=ctel,
                ))
            print(f"[+] Sembrados {len(ALBERGUES_DEMO)} albergues")
            db.commit()
        else:
            print(f"[=] albergues ya tiene {db.query(models.Albergue).count()} filas — omitido")

        # 5) Inventario de demostración (solo si la tabla está vacía)
        if db.query(models.RecursoInventario).count() == 0:
            for nom, cat, cant, unid, est, com, notas in RECURSOS_DEMO:
                db.add(models.RecursoInventario(
                    nombre=nom, categoria=cat, cantidad=cant, unidad=unid,
                    estado=est, comuna=com, notas=notas or None,
                ))
            print(f"[+] Sembrados {len(RECURSOS_DEMO)} recursos de inventario")
            db.commit()
        else:
            print(f"[=] recursos_inventario ya tiene {db.query(models.RecursoInventario).count()} filas — omitido")

        print("\n[OK] Modulo 5 habilitado. Reinicia el server y vuelve a loguearte.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
