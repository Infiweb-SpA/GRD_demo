import hmac
import secrets

import bcrypt

# Comunas de prueba para generar claves temporales legibles (ej: MuniCunco2026!)
COMUNAS_EJEMPLO = [
    "Cunco",
    "Freire",
    "Padre Las Casas",
]

MIN_LARGO_CLAVE = 8
MAX_BYTES_BCRYPT = 72  # límite de bcrypt


def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    data = password.encode("utf-8")
    if len(data) > MAX_BYTES_BCRYPT:
        raise ValueError("La contraseña no puede superar 72 bytes.")
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def generar_clave_temporal(comuna: str | None = None) -> str:
    """Genera una clave temporal legible, ej: MuniTemuco2026!"""
    from datetime import datetime

    nombre = comuna or secrets.choice(COMUNAS_EJEMPLO)
    nombre = "".join(parte.capitalize() for parte in nombre.split())
    anio = datetime.now().year
    return f"Muni{nombre}{anio}!"


def validar_fortaleza_clave(password: str) -> list[str]:
    """Devuelve la lista de errores de la clave. Lista vacía = clave válida."""
    errores = []
    if len(password) < MIN_LARGO_CLAVE:
        errores.append(f"Debe tener al menos {MIN_LARGO_CLAVE} caracteres.")
    if len(password.encode("utf-8")) > MAX_BYTES_BCRYPT:
        errores.append("No puede superar 72 bytes.")
    if not any(c.isalpha() for c in password):
        errores.append("Debe contener al menos una letra.")
    if not any(c.isdigit() for c in password):
        errores.append("Debe contener al menos un número.")
    return errores


def generar_csrf_token() -> str:
    """Token CSRF aleatorio, criptográficamente seguro."""
    return secrets.token_urlsafe(32)


def comparar_csrf(token_esperado: str | None, token_recibido: str | None) -> bool:
    """Comparación en tiempo constante para evitar ataques de temporización."""
    if not token_esperado or not token_recibido:
        return False
    return hmac.compare_digest(token_esperado, token_recibido)