# seed_modulo4.py
"""
Habilita el Módulo 4 (Vulnerabilidad + Ficha EDAN) en una BD existente (idempotente).

Ejecutar UNA VEZ desde la raíz del proyecto:
    (.venv) PS> python seed_modulo4.py

Qué hace:
  1. Crea los permisos vulnerabilidad:consultar, edan:leer y edan:escribir
     (vulnerabilidad:consultar ya existe en app/seed.py; se repite por
     robustez y solo se crea si falta).
  2. Los asigna a los roles superadmin, administrador y funcionario.
     NOTA: app/seed.py solo asigna permisos a roles NUEVOS, por lo que en una
     BD ya existente hay que agregarlos explícitamente (mismo motivo por el
     que existe seed_modulo3.py).
  3. Crea/activa la licencia 'modulo_4'.
  4. Si la tabla datos_censales está vacía, siembra sectores de prueba
     (decisión D1: datos locales, sin consultar CKAN en runtime).

Se puede correr varias veces sin efectos duplicados.
"""

from app.database import SessionLocal, init_db
from app import models


PERMISOS_M4 = [
    ("vulnerabilidad:consultar", "Consultar análisis socioeconómico (Módulo 4)"),
    ("edan:leer",               "Ver el panel de vulnerabilidad y las fichas EDAN"),
    ("edan:escribir",           "Crear y editar fichas EDAN (SENAPRED)"),
]

# El exportar:datos (Genérico, usado por M2) ya lo tienen los 3 roles.
ASIGNACION = {
    "superadmin":    ["vulnerabilidad:consultar", "edan:leer", "edan:escribir"],
    "administrador": ["vulnerabilidad:consultar", "edan:leer", "edan:escribir"],
    # El funcionario necesita vulnerabilidad:consultar para desbloquear la
    # tarjeta del M4 en el dashboard y llegar así al formulario EDAN.
    "funcionario":   ["vulnerabilidad:consultar", "edan:leer", "edan:escribir"],
}

# Sectores censales de prueba (D1: datos locales).
# Coordenadas cerca del centro de cada comuna (COMUNAS_COORDS del Módulo 3)
# para que el cruce point-in-polygon con las zonas de riesgo sea representativo.
# (comuna, sector, lat, lon, poblacion, viviendas, escuelas, postas)
SECTORES_CENSALES = [
    ("Cunco",           "Cunco Centro",    -38.9328, -72.0320,  8500, 2100, 6, 2),
    ("Cunco",           "Molco",           -38.8600, -71.9500,  2400,  600, 2, 1),
    ("Cunco",           "Quillen",         -38.9900, -71.9600,  1200,  300, 1, 1),
    ("Cunco",           "Rio Cunco",       -38.9400, -72.1100,  1800,  450, 1, 1),
    ("Freire",          "Freire Centro",   -38.9530, -72.6270,  6200, 1550, 5, 2),
    ("Freire",          "Pishiquin",       -38.9900, -72.6900,  1500,  380, 1, 1),
    ("Freire",          "Lican Rio",       -38.9400, -72.5500,  1100,  280, 1, 1),
    ("Freire",          "Pilpilco",        -39.0100, -72.5600,   900,  230, 1, 0),
    ("Padre Las Casas", "PL Casas Centro", -38.7674, -72.5956, 11000, 2750, 7, 3),
    ("Padre Las Casas", "Antren",          -38.7200, -72.6500,  2100,  520, 2, 1),
    ("Padre Las Casas", "Los Riscos",      -38.8100, -72.5500,  1600,  400, 1, 1),
    ("Padre Las Casas", "Rio Claro",       -38.8300, -72.6100,  1300,  330, 1, 1),
]


def main() -> None:
    # Crea las tablas que falten (datos_censales, fichas_edan) en una BD
    # existente, para que el script funcione sin depender de haber arrancado
    # el servidor antes. create_all es idempotente (solo crea las ausentes).
    init_db()

    db = SessionLocal()
    try:
        # 1) Permisos (idempotente)
        for codigo, desc in PERMISOS_M4:
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
        lic = db.query(models.ModuloLicencia).filter_by(codigo="modulo_4").first()
        if not lic:
            db.add(models.ModuloLicencia(
                codigo="modulo_4",
                nombre="Análisis de Vulnerabilidad y Evaluación de Daños (EDAN)",
                activo=True,
            ))
            print("[+] Licencia 'modulo_4' creada y ACTIVA")
        elif not lic.activo:
            lic.activo = True
            print("[+] Licencia 'modulo_4' reactivada")
        else:
            print("[=] Licencia 'modulo_4' ya estaba activa")
        db.commit()

        # 4) Datos censales de prueba (solo si la tabla está vacía)
        if db.query(models.DatoCensal).count() == 0:
            for comuna, sector, lat, lon, pob, viv, esc, pos in SECTORES_CENSALES:
                db.add(models.DatoCensal(
                    comuna=comuna, sector=sector, lat=lat, lon=lon,
                    poblacion=pob, viviendas=viv, escuelas=esc, postas=pos,
                ))
            print(f"[+] Sembrados {len(SECTORES_CENSALES)} sectores censales")
            db.commit()
        else:
            n = db.query(models.DatoCensal).count()
            print(f"[=] datos_censales ya tiene {n} filas — omitido")

        print("\n[OK] Modulo 4 habilitado. Reinicia el server y vuelve a loguearte.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
