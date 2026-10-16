# seed_modulo3.py
"""
Habilita el Módulo 3 en una BD existente (idempotente).

Ejecutar UNA VEZ desde la raíz del proyecto:
    (.venv) PS> python seed_modulo3.py

Qué hace:
  1. Crea los permisos zonas:leer, zonas:generar, zonas:editar.
  2. Los asigna a los roles superadmin, administrador y funcionario.
  3. Crea/activa la licencia 'modulo_3'.

Se puede correr varias veces sin efectos duplicados.
"""

from app.database import SessionLocal
from app import models


PERMISOS_M3 = [
    ("zonas:leer",    "Ver zonas de riesgo consolidadas en el dashboard"),
    ("zonas:generar", "Ejecutar el motor predictivo y sincronizar datos fluviales"),
    ("zonas:editar",  "Editar, renombrar, activar o desactivar zonas de riesgo"),
]

ASIGNACION = {
    "superadmin":    ["zonas:leer", "zonas:generar", "zonas:editar"],
    "administrador": ["zonas:leer", "zonas:generar", "zonas:editar"],
    "funcionario":   ["zonas:leer"],
}


def main() -> None:
    db = SessionLocal()
    try:
        # 1) Permisos
        for codigo, desc in PERMISOS_M3:
            if not db.query(models.Permiso).filter_by(codigo=codigo).first():
                db.add(models.Permiso(codigo=codigo, descripcion=desc))
                print(f"[+] Permiso creado:   {codigo}")
        db.commit()

        # 2) Asignar permisos a roles
        for nombre_rol, permisos in ASIGNACION.items():
            rol = db.query(models.Rol).filter_by(nombre=nombre_rol).first()
            if not rol:
                print(f"[!] Rol '{nombre_rol}' no existe — omitido")
                continue
            for codigo in permisos:
                permiso = db.query(models.Permiso).filter_by(codigo=codigo).first()
                if permiso and permiso not in rol.permisos:
                    rol.permisos.append(permiso)
                    print(f"[+] {nombre_rol:14s} ← {codigo}")
        db.commit()

        # 3) Licencia del módulo
        lic = db.query(models.ModuloLicencia).filter_by(codigo="modulo_3").first()
        if not lic:
            db.add(models.ModuloLicencia(
                codigo="modulo_3",
                nombre="Inteligencia Predictiva de Zonas de Riesgo",
                activo=True,
            ))
            print("[+] Licencia 'modulo_3' creada y ACTIVA")
        elif not lic.activo:
            lic.activo = True
            print("[+] Licencia 'modulo_3' reactivada")
        else:
            print("[=] Licencia 'modulo_3' ya estaba activa")
        db.commit()

        print("\n[OK] Módulo 3 habilitado. Reinicia el server y vuelve a loguearte.")

    finally:
        db.close()


if __name__ == "__main__":
    main()