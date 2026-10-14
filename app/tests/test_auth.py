# tests/test_auth.py
"""Pruebas automatizadas del Módulo 0 (Autenticación, RBAC, CSRF y cambio de clave)."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_salud():
    """Endpoint público de salud."""
    response = client.get("/api/salud")
    assert response.status_code == 200
    data = response.json()
    assert data["estado"] == "ok"
    assert data["version"] == "1.0.0"


def test_obtener_csrf():
    """Se debe poder obtener un CSRF token válido."""
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    csrf_token = response.json()["csrf_token"]
    assert len(csrf_token) > 20


def test_login_con_clave_temporal():
    """Login con credenciales válidas."""
    # 1️⃣ Obtener CSRF nuevo
    csrf_resp = client.get("/auth/csrf")
    csrf = csrf_resp.json()["csrf_token"]

    # 2️⃣ Login con credenciales válidas
    login_resp = client.post(
        "/auth/login",
        json={"username": "admin_cunco", "password": "Cunco2026Segura"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    
    # 🔧 CORRECCIÓN: Verificar estructura real de respuesta
    assert data["estado"] == "ok"
    assert "usuario" in data
    assert "csrf_token" in data
    assert data["usuario"]["username"] == "admin_cunco"


def test_cambiar_clave_y_obtener_permisos():
    """Cambiar la clave y obtener perfil de usuario."""
    # 1️⃣ Login inicial con clave actual
    csrf_resp = client.get("/auth/csrf")
    csrf = csrf_resp.json()["csrf_token"]

    login_resp = client.post(
        "/auth/login",
        json={"username": "admin_cunco", "password": "Cunco2026Segura"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login_resp.status_code == 200

    # 2️⃣ Obtener perfil de usuario autenticado
    profile_resp = client.get("/auth/me", headers={"X-CSRF-Token": csrf})
    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()
    assert profile_data["username"] == "admin_cunco"
    assert "permisos" in profile_data


def test_logout():
    """Cierre de sessión exitosa."""
    # 1️⃣ Login rápido para tener sessión
    csrf_resp = client.get("/auth/csrf")
    csrf = csrf_resp.json()["csrf_token"]

    login_resp = client.post(
        "/auth/login",
        json={"username": "admin_cunco", "password": "Cunco2026Segura"},
        headers={"X-CSRF-Token": csrf},
    )
    assert login_resp.status_code == 200
    
    # 🔧 CORRECCIÓN: Usar el CSRF token de la respuesta del login
    new_csrf = login_resp.json()["csrf_token"]

    # 2️⃣ Cerrar sessón con el nuevo CSRF token
    logout = client.post(
        "/auth/logout",
        headers={"X-CSRF-Token": new_csrf},  # Usar el token actualizado
    )
    assert logout.status_code == 200
    assert logout.json()["estado"] == "sesion_cerrada"