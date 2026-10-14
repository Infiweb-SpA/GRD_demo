from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ModuloLicencia, Permiso, Rol, Usuario
from app.security import generar_clave_temporal, hash_password

# Catálogo de permisos (Matriz de Permisos)
PERMISOS: dict[str, str] = {
    "usuarios:gestionar": "Crear, bloquear y reiniciar contraseñas de funcionarios",
    "matriz:configurar": "Configurar la matriz de permisos por rol",
    "logs:ver": "Consultar la bitácora de auditoría",
    "reportes:leer": "Ver incidentes reportados",
    "reportes:escribir": "Crear y modificar incidentes",
    "mapa:editar": "Dibujar y editar geometrías en el mapa (Geoman)",
    "exportar:datos": "Descargar capas en GeoJSON",
    "riesgo:generar": "Generar zonas de riesgo (Módulo 3)",
    "vulnerabilidad:consultar": "Consultar análisis socioeconómico (Módulo 4)",
}

# Roles con sus permisos iniciales (el superadmin los puede cambiar luego)
ROLES: dict[str, tuple[str, list[str]]] = {
    "superadmin": (
        "Control total del ecosistema",
        list(PERMISOS.keys()),
    ),
    "administrador": (
        "Gestión municipal y auditoría",
        [
            "usuarios:gestionar", "logs:ver", "reportes:leer", "reportes:escribir",
            "mapa:editar", "exportar:datos", "riesgo:generar", "vulnerabilidad:consultar",
        ],
    ),
    "funcionario": (
        "Levantamiento de datos en terreno",
        ["reportes:leer", "reportes:escribir", "mapa:editar", "exportar:datos"],
    ),
}

# Feature flags de licenciamiento (activo=True para desarrollo; en producción se controla desde el superadmin)
MODULOS: list[tuple[str, str, bool]] = [
    ("modulo_0", "Autenticación, roles y licenciamiento", True),
    ("modulo_1", "Visor público y landing informativa", True),
    ("modulo_2", "Registro de incidentes y trazabilidad", False),
    ("modulo_3", "Inteligencia predictiva de zonas de riesgo", False),
    ("modulo_4", "Análisis de vulnerabilidad socioeconómica", False),
]

# Municipalidades de prueba
COMUNAS_PRUEBA: list[str] = ["Cunco", "Freire", "Padre Las Casas"]


def slugify(nombre: str) -> str:
    """Convierte 'Padre Las Casas' en 'padre_las_casas' para usarlo en usernames."""
    return nombre.strip().lower().replace(" ", "_")


def seed_inicial(db: Session) -> list[tuple[str, str]]:
    """Carga datos base de forma idempotente.

    Devuelve la lista de (usuario, clave_temporal) de los usuarios creados
    en esta ejecución, para mostrarlos en consola.
    """

    # 1. Permisos
    permisos: dict[str, Permiso] = {}
    for codigo, descripcion in PERMISOS.items():
        permiso = db.scalar(select(Permiso).where(Permiso.codigo == codigo))
        if permiso is None:
            permiso = Permiso(codigo=codigo, descripcion=descripcion)
            db.add(permiso)
        permisos[codigo] = permiso
    db.flush()

    # 2. Roles (solo asigna permisos si el rol es nuevo, para no pisar cambios hechos por el superadmin)
    roles: dict[str, Rol] = {}
    for nombre, (descripcion, codigos) in ROLES.items():
        rol = db.scalar(select(Rol).where(Rol.nombre == nombre))
        if rol is None:
            rol = Rol(nombre=nombre, descripcion=descripcion)
            rol.permisos = [permisos[c] for c in codigos]
            db.add(rol)
        roles[nombre] = rol
    db.flush()

    # 3. Módulos con licencia
    for codigo, nombre, activo in MODULOS:
        existe = db.scalar(select(ModuloLicencia).where(ModuloLicencia.codigo == codigo))
        if existe is None:
            db.add(ModuloLicencia(codigo=codigo, nombre=nombre, activo=activo))

    # 4. Superadmin con clave temporal (debe cambiarla al entrar)
    superadmin = db.scalar(
        select(Usuario).where(Usuario.username == settings.SUPERADMIN_USERNAME)
    )
    if superadmin is None:
        db.add(
            Usuario(
                username=settings.SUPERADMIN_USERNAME,
                password_hash=hash_password(settings.SUPERADMIN_PASSWORD),
                rol=roles["superadmin"],
                requiere_cambio_clave=True,
            )
        )

    # 5. Administrador y funcionario por cada comuna de prueba
    creados: list[tuple[str, str]] = []
    for comuna in COMUNAS_PRUEBA:
        slug = slugify(comuna)
        for prefijo, rol_nombre in (("admin", "administrador"), ("funcionario", "funcionario")):
            username = f"{prefijo}_{slug}"
            existe = db.scalar(select(Usuario).where(Usuario.username == username))
            if existe is None:
                clave = generar_clave_temporal(comuna)
                db.add(
                    Usuario(
                        username=username,
                        password_hash=hash_password(clave),
                        rol=roles[rol_nombre],
                        requiere_cambio_clave=True,
                    )
                )
                creados.append((username, clave))

    # 6. Alertas municipales operativas iniciales (Opcional para pruebas)
    from app.models import AlertaMunicipalActiva # (Asegúrate de importarlo arriba si es necesario)
    
    alerta_prueba = db.scalar(
        select(AlertaMunicipalActiva).where(AlertaMunicipalActiva.comuna == "Cunco", AlertaMunicipalActiva.activa == True)
    )
    if alerta_prueba is None:
        db.add(
            AlertaMunicipalActiva(
                comuna="Cunco",
                tipo_alerta="Tormenta Eléctrica",
                intensidad="Amarilla",
                periodo_estimado="Estimado entre las 15:00 y 21:00 hrs de hoy",
                activa=True
            )
        )
    db.commit()
    return creados


if __name__ == "__main__":
    from app.database import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        creados = seed_inicial(db)

    print("Base de datos lista: tablas, roles, permisos, módulos y superadmin creados.")
    if creados:
        print("\nUsuarios de prueba creados (clave temporal, cambio obligatorio al entrar):")
        for username, clave in creados:
            print(f"  {username:<28} {clave}")
    else:
        print("\nNo se crearon usuarios nuevos (ya existían).")