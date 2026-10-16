from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Tabla intermedia: muchos a muchos entre roles y permisos (Matriz de Permisos)
roles_permisos = Table(
    "roles_permisos",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", Integer, ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True),
)


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    permisos: Mapped[list["Permiso"]] = relationship(
        secondary=roles_permisos, back_populates="roles", lazy="selectin"
    )
    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="rol")


class Permiso(Base):
    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Rol]] = relationship(
        secondary=roles_permisos, back_populates="permisos"
    )


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    requiere_cambio_clave: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    rol: Mapped[Rol] = relationship(back_populates="usuarios", lazy="joined")


class Incidente(Base):
    """Incidentes registrados en terreno (Módulo 2 – tabla incidentes_reportes)."""

    __tablename__ = "incidentes_reportes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amenaza_tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    comentario: Mapped[str | None] = mapped_column(String(1000))
    geojson_geometria: Mapped[str] = mapped_column(Text, nullable=False)
    imagenes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    eliminado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_por_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    creado_por: Mapped["Usuario"] = relationship()


class ModuloLicencia(Base):
    """Feature flags: módulos contratados por el municipio."""

    __tablename__ = "modulos_licencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LogAuditoria(Base):
    """Auditoría legal: quién hizo qué, cuándo y desde qué IP."""

    __tablename__ = "logs_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    accion_realizada: Mapped[str] = mapped_column(String(255), nullable=False)
    tabla_afectada: Mapped[str] = mapped_column(String(100), nullable=False)
    registro_id: Mapped[int | None] = mapped_column(Integer)
    direccion_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    usuario: Mapped[Usuario | None] = relationship(lazy="joined")


class AlertaMunicipalActiva(Base):
    """Alertas tempranas o climáticas registradas manualmente por operadores municipales."""

    __tablename__ = "alertas_municipales_activas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # línea corrupta limpiada
    comuna: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tipo_alerta: Mapped[str] = mapped_column(String(100), nullable=False)
    intensidad: Mapped[str] = mapped_column(String(50), nullable=False)
    periodo_estimado: Mapped[str] = mapped_column(String(255), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    
# =========================================================================
# MÓDULO 3 — Inteligencia Predictiva de Zonas de Riesgo
# =========================================================================
from sqlalchemy import Date, Float, UniqueConstraint  # añadir a imports si no están


class DatoFluvialHistorico(Base):
    """
    Cache de la API Open-Meteo Flood.
    Almacena caudal diario (m³/s) por comuna para poder calcular
    percentiles P90/P95 y detectar crecidas en ventanas temporales.
    """
    __tablename__ = "datos_fluviales_historicos"

    id = Column(Integer, primary_key=True)
    comuna = Column(String(100), index=True, nullable=False)
    fecha = Column(Date, index=True, nullable=False)
    caudal_m3_s = Column(Float, nullable=False)
    lat = Column(Float)
    lon = Column(Float)

    __table_args__ = (
        UniqueConstraint("comuna", "fecha", name="uq_fluvial_comuna_fecha"),
    )


class ZonaRiesgo(Base):
    """
    Polígono de riesgo oficial consolidado (Ley 21.364).
    Puede ser generado automáticamente por el motor del Módulo 3
    o creado/ajustado manualmente por un administrador.
    """
    __tablename__ = "zonas_riesgo"

    id = Column(Integer, primary_key=True)
    comuna = Column(String(100), index=True, nullable=False)
    nombre = Column(String(200), nullable=False)
    severidad = Column(String(20), nullable=False)  # bajo|medio|alto|critico
    geojson_geometria = Column(Text, nullable=False)  # Polygon WGS84
    motivo = Column(String(500))  # resumen legible (para el ciudadano)
    datos_origen = Column(Text)   # JSON con scores, P90/P95, incidentes vinculados
    activa = Column(Boolean, default=True, index=True)
    generado_automaticamente = Column(Boolean, default=True)
    creado_por_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    fecha_generacion = Column(DateTime, default=datetime.utcnow, index=True)


# =========================================================================
# MÓDULO 4 — Análisis de Vulnerabilidad y Evaluación de Daños (EDAN)
# =========================================================================


class DatoCensal(Base):
    """Datos demográficos e infraestructura crítica por sector (Módulo 4).

    Decisión D1: se almacenan en una tabla LOCAL en lugar de consultar un
    endpoint CKAN en runtime. Así el cruce es determinista, auditable y no
    depende de la disponibilidad de una API externa (misma filosofía que el
    motor del Módulo 3).

    El par (lat, lon) representa el centroide del sector y se usa para el
    cruce point-in-polygon con los polígonos de riesgo del Módulo 3.
    """

    __tablename__ = "datos_censales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comuna: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    sector: Mapped[str] = mapped_column(String(200), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    poblacion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    viviendas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escuelas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    postas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class FichaEDAN(Base):
    """Ficha EDAN (Evaluación de Daños y Necesidades) — SENAPRED.

    Concentra la evaluación post-terreno en un solo lugar antes de enviarla
    a SENAPRED. Vincula la dañificación con la georreferencia del Módulo 2
    de forma HÍBRIDA (decisión D2):

      * ``incidente_id`` (FK nullable) → trazabilidad hacia el incidente de M2.
      * ``geojson_geometria`` (snapshot) → copia de la geometría para que la
        ficha sea autocontenida y exportable sin depender de M2.

    Campos organizados según los tres bloques oficiales del EDAN:
    tipo de daño en vivienda · número de damnificados · necesidades de
    habitabilidad.
    """

    __tablename__ = "fichas_edan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Identificación ---
    comuna: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(
        String(20), default="borrador", nullable=False
    )  # borrador | enviada

    # --- Georreferenciación (D2: híbrido FK + snapshot) ---
    geojson_geometria: Mapped[str | None] = mapped_column(Text)  # Point/Polygon WGS84
    incidente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("incidentes_reportes.id", ondelete="SET NULL")
    )

    # --- 1) Tipo de daño en vivienda ---
    danio_vivienda_tipo: Mapped[str] = mapped_column(
        String(50), default="Sin daño", nullable=False
    )  # Sin daño | Daño leve | Daño medio | Daño total
    viviendas_evaluadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    viviendas_danadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    viviendas_destruidas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- 2) Número de damnificados ---
    personas_afectadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    personas_damnificadas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    personas_desaparecidas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    personas_fallecidas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- 3) Necesidades de habitabilidad ---
    nec_agua_potable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nec_alimentacion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nec_habitacion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nec_asistencia_medica: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nec_servicio_sanitario: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    otras_necesidades: Mapped[str | None] = mapped_column(Text)

    # --- Trazabilidad ---
    creado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    creado_por: Mapped["Usuario | None"] = relationship()
    incidente: Mapped["Incidente | None"] = relationship()


# =========================================================================
# MÓDULO 5 — Albergues y Logística
# =========================================================================


class Albergue(Base):
    """Catastro de albergues municipales (Módulo 5).

    Registra dónde puede refugiarse la población y con qué servicios cuenta.
    El vínculo con una zona de riesgo del Módulo 3 es estrictamente OPCIONAL
    (decisión D4): sirve para planificar evacuación, no es obligatorio para
    dar de alta un albergue.
    """

    __tablename__ = "albergues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    comuna: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    direccion: Mapped[str | None] = mapped_column(String(300))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    capacidad: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="activo", nullable=False
    )  # activo | mantencion | inactivo

    # --- Servicios disponibles --- (permiten priorizar en una emergencia)
    srv_agua_potable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    srv_electricidad: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    srv_sanitarios: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    srv_cocina: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    srv_internet: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Contacto (encargado del albergue) ---
    contacto_nombre: Mapped[str | None] = mapped_column(String(200))
    contacto_telefono: Mapped[str | None] = mapped_column(String(50))

    # --- D4: vínculo estrictamente opcional con zona de riesgo del M3 ---
    zona_riesgo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("zonas_riesgo.id", ondelete="SET NULL")
    )

    # --- Trazabilidad ---
    creado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    creado_por: Mapped["Usuario | None"] = relationship()
    zona_riesgo: Mapped["ZonaRiesgo | None"] = relationship()


class RecursoInventario(Base):
    """Inventario de recursos logísticos con discriminador de categoría (D3).

    Una sola tabla para las 3 categorías del inventario — ``maquinaria``,
    ``abrigo`` y ``alimento`` — diferenciadas por ``categoria``. Evita 3 tablas
    casi idénticas y permite consultas globales ("¿cuánto abrigo hay en la
    comuna?") con la misma estructura.

    La asignación logística es un FK opcional a ``albergues``: si
    ``estado='asignado'``, el recurso está destinado a ese albergue. El vínculo
    con un incidente del Módulo 2 también es estrictamente opcional (D4).
    """

    __tablename__ = "recursos_inventario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria: Mapped[str] = mapped_column(
        String(20), index=True, nullable=False
    )  # maquinaria | abrigo | alimento  (D3)
    cantidad: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unidad: Mapped[str] = mapped_column(String(50), default="unidades", nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="disponible", nullable=False
    )  # disponible | asignado | mantencion
    comuna: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # --- Logística: destino del recurso (opcional) ---
    albergue_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("albergues.id", ondelete="SET NULL")
    )
    # --- D4: vínculo estrictamente opcional al incidente que lo activó ---
    incidente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("incidentes_reportes.id", ondelete="SET NULL")
    )
    notas: Mapped[str | None] = mapped_column(Text)

    # --- Trazabilidad ---
    creado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    creado_por: Mapped["Usuario | None"] = relationship()
    albergue: Mapped["Albergue | None"] = relationship()
    incidente: Mapped["Incidente | None"] = relationship()