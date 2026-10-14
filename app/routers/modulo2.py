import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter, Depends, File, HTTPException, Request, UploadFile, status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import (
    csrf_obligatorio,
    get_current_user_html,
    registrar_auditoria,
    requiere_modulo,
    requiere_permiso,
    usuario_actual,
)
from app.models import Incidente, LogAuditoria, Usuario

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))

UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "incidentes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGENES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMG_BYTES = 5 * 1024 * 1024  # 5 MB por archivo

CATEGORIAS_SENAPRED = [
    "Inundación",
    "Deslizamiento",
    "Incendio Forestal",
    "Temporal",
    "Terremoto",
    "Erupción Volcánica",
    "Ola de Calor",
    "Sequía",
]


def _geometry(incidente: Incidente) -> dict | None:
    try:
        return json.loads(incidente.geojson_geometria)
    except (TypeError, ValueError):
        return None


def _imagenes(incidente: Incidente) -> list[str]:
    try:
        return json.loads(incidente.imagenes or "[]")
    except (TypeError, ValueError):
        return []


# -------------------------------------------------------------------
# Vistas HTML
# -------------------------------------------------------------------
@router.get(
    "/modulo2/reportes",
    response_class=HTMLResponse,
    dependencies=[
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:leer")),
    ],
)
async def pagina_reportes(
    request: Request,
    usuario: Usuario = Depends(get_current_user_html),
):
    template = env.get_template("modulo2/reportes.html")
    html = template.render(
        request=request,
        categorias=CATEGORIAS_SENAPRED,
        usuario=usuario,
    )
    return HTMLResponse(html)


# -------------------------------------------------------------------
# API: lectura
# -------------------------------------------------------------------
@router.get(
    "/api/modulo2/incidentes",
    dependencies=[
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:leer")),
    ],
)
async def obtener_incidentes(
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    incidentes = (
        db.query(Incidente)
        .filter(Incidente.eliminado.is_(False))
        .order_by(Incidente.fecha_creacion.desc())
        .all()
    )
    features = [
        {
            "type": "Feature",
            "geometry": _geometry(inc),
            "properties": {
                "id": inc.id,
                "amenaza_tipo": inc.amenaza_tipo,
                "comentario": inc.comentario,
                "fecha_creacion": inc.fecha_creacion.isoformat() if inc.fecha_creacion else None,
                "creado_por": inc.creado_por_id,
                "imagenes": _imagenes(inc),
            },
        }
        for inc in incidentes
    ]
    return {"type": "FeatureCollection", "features": features}


# -------------------------------------------------------------------
# API: crear
# -------------------------------------------------------------------
@router.post(
    "/api/modulo2/incidentes",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:escribir")),
    ],
)
async def crear_incidente(
    request: Request,
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    data = await request.json()
    if not data.get("amenaza_tipo") or not data.get("geojson_geometria"):
        raise HTTPException(status_code=400, detail="Faltan datos requeridos")

    nuevo = Incidente(
        amenaza_tipo=data["amenaza_tipo"],
        comentario=data.get("comentario", ""),
        geojson_geometria=json.dumps(data["geojson_geometria"]),
        imagenes="[]",
        eliminado=False,
        creado_por_id=actual_user.id,
        fecha_creacion=datetime.now(timezone.utc),
    )
    db.add(nuevo)
    db.flush()

    registrar_auditoria(
        db, request, actual_user.id,
        f"Creó incidente #{nuevo.id} - {nuevo.amenaza_tipo}",
        "incidentes_reportes", nuevo.id,
    )
    db.commit()
    db.refresh(nuevo)
    return {"estado": "ok", "incidente_id": nuevo.id}


# -------------------------------------------------------------------
# API: editar
# -------------------------------------------------------------------
@router.put(
    "/api/modulo2/incidentes/{incidente_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:escribir")),
    ],
)
async def editar_incidente(
    incidente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    incidente = db.get(Incidente, incidente_id)
    if incidente is None or incidente.eliminado:
        raise HTTPException(404, "Incidente no encontrado")

    data = await request.json()
    cambios = []

    if "amenaza_tipo" in data and data["amenaza_tipo"] != incidente.amenaza_tipo:
        cambios.append(f"amenaza {incidente.amenaza_tipo} → {data['amenaza_tipo']}")
        incidente.amenaza_tipo = data["amenaza_tipo"]

    if "comentario" in data and (data["comentario"] or "") != (incidente.comentario or ""):
        cambios.append("comentario")
        incidente.comentario = data["comentario"]

    if "geojson_geometria" in data and data["geojson_geometria"]:
        cambios.append("geometría")
        incidente.geojson_geometria = json.dumps(data["geojson_geometria"])

    if not cambios:
        return {"estado": "sin_cambios"}

    registrar_auditoria(
        db, request, actual_user.id,
        f"Modificó incidente #{incidente.id} ({', '.join(cambios)})",
        "incidentes_reportes", incidente.id,
    )
    db.commit()
    return {"estado": "ok", "incidente_id": incidente.id}


# -------------------------------------------------------------------
# API: eliminar (soft delete)
# -------------------------------------------------------------------
@router.delete(
    "/api/modulo2/incidentes/{incidente_id}",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:escribir")),
    ],
)
async def eliminar_incidente(
    incidente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    incidente = db.get(Incidente, incidente_id)
    if incidente is None or incidente.eliminado:
        raise HTTPException(404, "Incidente no encontrado")

    incidente.eliminado = True

    registrar_auditoria(
        db, request, actual_user.id,
        f"Eliminó incidente #{incidente.id} - {incidente.amenaza_tipo}",
        "incidentes_reportes", incidente.id,
    )
    db.commit()
    return {"estado": "ok"}


# -------------------------------------------------------------------
# API: subir imágenes a un incidente
# -------------------------------------------------------------------
@router.post(
    "/api/modulo2/incidentes/{incidente_id}/imagenes",
    dependencies=[
        Depends(csrf_obligatorio),
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("reportes:escribir")),
    ],
)
async def subir_imagenes(
    incidente_id: int,
    request: Request,
    archivos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    incidente = db.get(Incidente, incidente_id)
    if incidente is None or incidente.eliminado:
        raise HTTPException(404, "Incidente no encontrado")

    if not archivos:
        raise HTTPException(400, "No se enviaron archivos")

    dir_destino = UPLOAD_DIR / str(incidente_id)
    dir_destino.mkdir(parents=True, exist_ok=True)

    urls = _imagenes(incidente)

    for archivo in archivos:
        if archivo.content_type not in ALLOWED_IMAGENES:
            raise HTTPException(
                400, f"Tipo no permitido: {archivo.content_type}. Usa JPG, PNG o WebP."
            )
        contenido = await archivo.read()
        if len(contenido) > MAX_IMG_BYTES:
            raise HTTPException(400, f"{archivo.filename} supera 5 MB")

        ext = Path(archivo.filename or "").suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        nombre = f"{uuid.uuid4().hex}{ext}"
        (dir_destino / nombre).write_bytes(contenido)
        urls.append(f"/static/uploads/incidentes/{incidente_id}/{nombre}")

    incidente.imagenes = json.dumps(urls)

    registrar_auditoria(
        db, request, actual_user.id,
        f"Adjuntó {len(archivos)} imagen(es) al incidente #{incidente_id}",
        "incidentes_reportes", incidente_id,
    )
    db.commit()
    return {"imagenes": urls}


# -------------------------------------------------------------------
# API: exportar
# -------------------------------------------------------------------
@router.get(
    "/api/modulo2/exportar-datos",
    dependencies=[
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("exportar:datos")),
    ],
)
async def exportar_datos_geojson(
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    incidentes = db.query(Incidente).filter(Incidente.eliminado.is_(False)).all()
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _geometry(inc),
                "properties": {
                    "id": inc.id,
                    "amenaza_tipo": inc.amenaza_tipo,
                    "comentario": inc.comentario,
                    "fecha_creacion": inc.fecha_creacion.isoformat() if inc.fecha_creacion else None,
                    "creado_por": inc.creado_por_id,
                    "imagenes": _imagenes(inc),
                },
            }
            for inc in incidentes
        ],
    }
    return JSONResponse(
        content=geojson,
        headers={"Content-Disposition": "attachment; filename=incidentes_grd.geojson"},
    )


# -------------------------------------------------------------------
# API: logs de auditoría
# -------------------------------------------------------------------
@router.get(
    "/api/modulo2/logs-auditoria",
    dependencies=[
        Depends(requiere_modulo("modulo_2")),
        Depends(requiere_permiso("logs:ver")),
    ],
)
async def obtener_logs_auditoria(
    db: Session = Depends(get_db),
    actual_user: Usuario = Depends(usuario_actual),
):
    logs = db.query(LogAuditoria).order_by(LogAuditoria.fecha_hora.desc()).limit(100).all()
    return {
        "logs": [
            {
                "id": log.id,
                "fecha_hora": log.fecha_hora.isoformat(),
                "usuario_id": log.usuario_id,
                "usuario": log.usuario.username if log.usuario else "—",
                "accion": log.accion_realizada,
                "ip": log.direccion_ip,
            }
            for log in logs
        ]
    }