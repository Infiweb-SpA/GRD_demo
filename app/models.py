from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
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
    # True cuando el admin reinicia la clave: obliga a elegir una nueva o mantener la temporal
    requiere_cambio_clave: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    rol: Mapped[Rol] = relationship(back_populates="usuarios", lazy="joined")


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