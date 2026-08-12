from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import UsuarioRootMine

RUTA_USUARIOS = Path("data/usuarios_adf.json")  # semilla inicial, no fuente operacional
RUTA_CENTROS = Path("data/centros.json")

ROLES_TECNICOS = {
    "tecnico", "senior", "programador_mantenimiento",
    "ingeniero_confiabilidad", "ingeniero_procesos",
}
ROLES_VALIDADORES = {"supervisor", "jefe", "ingeniero", "subgerente"}

ETIQUETAS_ROL = {
    "tecnico": "Técnico",
    "senior": "Senior",
    "programador_mantenimiento": "Programador de Mantenimiento",
    "ingeniero_confiabilidad": "Ingeniero de Confiabilidad",
    "ingeniero_procesos": "Ingeniero de Procesos",
    "supervisor": "Supervisor",
    "jefe": "Jefe",
    "ingeniero": "Ingeniero de Mantenimiento",
    "subgerente": "Subgerente",
}


def etiqueta_rol(rol: str) -> str:
    return ETIQUETAS_ROL.get((rol or "").strip().lower(), (rol or "").replace("_", " ").title())


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").strip().upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("ADM / DESPACHO", "ADM-DESP").replace("ADM/DESPACHO", "ADM-DESP")
    return " ".join(texto.split())


def cargar_centros() -> dict:
    if not RUTA_CENTROS.exists():
        return {}
    return json.loads(RUTA_CENTROS.read_text(encoding="utf-8"))


def nombre_centro(codigo: str) -> str:
    centro = cargar_centros().get(str(codigo), {})
    return centro.get("nombre", "")


def etiqueta_centro(codigo: str, planta: str = "") -> str:
    codigo = str(codigo or "").strip()
    planta = (planta or nombre_centro(codigo)).strip()
    if codigo and planta:
        return f"{codigo} - {planta}"
    return codigo or planta or "Centro no configurado"


def _resp_lista(valor) -> list[str]:
    if not valor:
        return []
    if isinstance(valor, list):
        return [str(x).strip() for x in valor if str(x).strip()]
    if isinstance(valor, str):
        try:
            parsed = json.loads(valor)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
        return [x.strip() for x in valor.replace(";", ",").split(",") if x.strip()]
    return []


def _normalizar_usuario(usuario: dict) -> dict:
    u = dict(usuario)
    u["correo"] = (u.get("correo") or "").strip().lower()
    u["nombre"] = (u.get("nombre") or "").strip()
    u["centro"] = str(u.get("centro") or "").strip()
    u["planta"] = (u.get("planta") or nombre_centro(u["centro"])).strip()
    u["area"] = (u.get("area") or "").strip()
    u["rol"] = (u.get("rol") or "tecnico").strip().lower()
    u["job_code"] = (u.get("job_code") or "").strip()
    u["rut"] = (u.get("rut") or "").strip()
    u["responsable_de"] = _resp_lista(u.get("responsable_de"))
    u["activo"] = bool(u.get("activo", True))
    u["es_admin"] = bool(u.get("es_admin", False))
    # La cuenta maestra histórica nace como administrador en una instalación nueva.
    if u["correo"] == "rfernandezc@agrosuper.com":
        u["es_admin"] = True
    return u


def _a_dict(reg: UsuarioRootMine) -> dict:
    return {
        "rut": reg.rut or "", "nombre": reg.nombre or "", "correo": reg.correo or "",
        "area": reg.area or "", "job_code": reg.job_code or "", "rol": reg.rol or "tecnico",
        "centro": reg.centro or "", "planta": reg.planta or "", "activo": bool(reg.activo), "es_admin": bool(reg.es_admin),
        "responsable_de": _resp_lista(reg.responsable_de),
    }


def inicializar_maestro_usuarios() -> None:
    """Si la tabla está vacía, importa una sola vez la semilla JSON incluida en el proyecto."""
    with Session(engine) as session:
        if session.scalar(select(UsuarioRootMine.id).limit(1)) is not None:
            return
        if not RUTA_USUARIOS.exists():
            return
        try:
            semillas = json.loads(RUTA_USUARIOS.read_text(encoding="utf-8"))
        except Exception:
            semillas = []
        vistos = set()
        for item in semillas:
            u = _normalizar_usuario(item)
            if not u["correo"] or u["correo"] in vistos:
                continue
            vistos.add(u["correo"])
            session.add(UsuarioRootMine(
                rut=u["rut"], nombre=u["nombre"], correo=u["correo"], area=u["area"],
                job_code=u["job_code"], rol=u["rol"], centro=u["centro"], planta=u["planta"],
                activo=u["activo"], es_admin=u["es_admin"], responsable_de=json.dumps(u["responsable_de"], ensure_ascii=False),
            ))
        session.commit()


def cargar_todos_usuarios() -> list[dict]:
    inicializar_maestro_usuarios()
    with Session(engine) as session:
        regs = list(session.scalars(select(UsuarioRootMine).order_by(UsuarioRootMine.nombre.asc())).all())
        return [_a_dict(r) for r in regs]


def guardar_usuarios(usuarios: list[dict]) -> None:
    """Compatibilidad: reemplaza el maestro persistente por la lista recibida."""
    normalizados = [_normalizar_usuario(u) for u in usuarios]
    with Session(engine) as session:
        existentes = {r.correo: r for r in session.scalars(select(UsuarioRootMine)).all()}
        correos_nuevos = {u["correo"] for u in normalizados}
        for correo, reg in existentes.items():
            if correo not in correos_nuevos:
                session.delete(reg)
        for u in normalizados:
            reg = existentes.get(u["correo"])
            if reg is None:
                reg = UsuarioRootMine(correo=u["correo"], nombre=u["nombre"])
                session.add(reg)
            reg.rut=u["rut"]; reg.nombre=u["nombre"]; reg.area=u["area"]; reg.job_code=u["job_code"]
            reg.rol=u["rol"]; reg.centro=u["centro"]; reg.planta=u["planta"]; reg.activo=u["activo"]; reg.es_admin=u["es_admin"]
            reg.responsable_de=json.dumps(u["responsable_de"], ensure_ascii=False)
        session.commit()


def cargar_usuarios() -> list[dict]:
    return [u for u in cargar_todos_usuarios() if u.get("activo", True)]


def crear_usuario(usuario: dict) -> None:
    nuevo = _normalizar_usuario(usuario)
    if not nuevo["correo"] or "@" not in nuevo["correo"]:
        raise ValueError("Debes ingresar un correo válido.")
    if not nuevo["nombre"]:
        raise ValueError("Debes ingresar el nombre del usuario.")
    with Session(engine) as session:
        if session.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == nuevo["correo"])):
            raise ValueError("Ya existe una cuenta con ese correo.")
        session.add(UsuarioRootMine(
            rut=nuevo["rut"], nombre=nuevo["nombre"], correo=nuevo["correo"], area=nuevo["area"],
            job_code=nuevo["job_code"], rol=nuevo["rol"], centro=nuevo["centro"], planta=nuevo["planta"],
            activo=nuevo["activo"], es_admin=nuevo["es_admin"], responsable_de=json.dumps(nuevo["responsable_de"], ensure_ascii=False),
        ))
        session.commit()


def actualizar_usuario(correo_original: str, cambios: dict) -> None:
    original = (correo_original or "").strip().lower()
    with Session(engine) as session:
        reg = session.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == original))
        if not reg:
            raise ValueError("No se encontró la cuenta a editar.")
        base = _a_dict(reg)
        actualizado = _normalizar_usuario({**base, **cambios})
        if not actualizado["correo"] or "@" not in actualizado["correo"]:
            raise ValueError("Debes ingresar un correo válido.")
        duplicado = session.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == actualizado["correo"], UsuarioRootMine.id != reg.id))
        if duplicado:
            raise ValueError("Ya existe otra cuenta con ese correo.")
        reg.rut=actualizado["rut"]; reg.nombre=actualizado["nombre"]; reg.correo=actualizado["correo"]
        reg.area=actualizado["area"]; reg.job_code=actualizado["job_code"]; reg.rol=actualizado["rol"]
        reg.centro=actualizado["centro"]; reg.planta=actualizado["planta"]; reg.activo=actualizado["activo"]; reg.es_admin=actualizado["es_admin"]
        reg.responsable_de=json.dumps(actualizado["responsable_de"], ensure_ascii=False)
        session.commit()


def eliminar_usuario(correo: str) -> bool:
    objetivo = (correo or "").strip().lower()
    with Session(engine) as session:
        reg = session.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == objetivo))
        if not reg:
            return False
        session.delete(reg)
        session.commit()
        return True


def buscar_usuario_por_correo(correo: str) -> dict | None:
    objetivo = (correo or "").strip().lower()
    if not objetivo:
        return None
    inicializar_maestro_usuarios()
    with Session(engine) as session:
        reg = session.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == objetivo, UsuarioRootMine.activo.is_(True)))
        return _a_dict(reg) if reg else None


def _areas_responsabilidad(usuario: dict) -> set[str]:
    explicitas = _resp_lista(usuario.get("responsable_de"))
    if explicitas:
        return {_norm(x) for x in explicitas}
    area = (usuario.get("area") or "").replace("ADM / DESPACHO", "ADM-DESP")
    return {_norm(x) for x in area.split("/") if x.strip()}


def _resolver_responsable(centro: str, area: str, rol: str) -> dict | None:
    centro_objetivo = str(centro or "").strip()
    area_objetivo = _norm(area)
    candidatos = []
    for usuario in cargar_usuarios():
        if usuario.get("rol", "").lower() != rol.lower():
            continue
        if str(usuario.get("centro", "")).strip() != centro_objetivo:
            continue
        areas = _areas_responsabilidad(usuario)
        if "TODAS" in areas or area_objetivo in areas:
            candidatos.append(usuario)
    return sorted(candidatos, key=lambda x: (x.get("nombre", ""), x.get("correo", "")))[0] if candidatos else None


def resolver_supervisor(centro: str, area: str) -> dict | None:
    return _resolver_responsable(centro, area, "supervisor")


def resolver_jefe(centro: str, area: str) -> dict | None:
    return _resolver_responsable(centro, area, "jefe")


def resumen_maestro() -> dict:
    usuarios = cargar_usuarios()
    conteo = {}
    centros = set()
    for u in usuarios:
        rol = etiqueta_rol(u.get("rol", "sin rol"))
        conteo[rol] = conteo.get(rol, 0) + 1
        if u.get("centro"):
            centros.add(str(u["centro"]))
    return {"total": len(usuarios), "roles": conteo, "centros": len(centros)}
