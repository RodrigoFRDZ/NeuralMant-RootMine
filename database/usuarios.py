import json
import unicodedata
from pathlib import Path

RUTA_USUARIOS = Path("data/usuarios_adf.json")
RUTA_CENTROS = Path("data/centros.json")


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


def cargar_todos_usuarios() -> list[dict]:
    if not RUTA_USUARIOS.exists():
        return []
    return json.loads(RUTA_USUARIOS.read_text(encoding="utf-8"))


def guardar_usuarios(usuarios: list[dict]) -> None:
    RUTA_USUARIOS.parent.mkdir(parents=True, exist_ok=True)
    RUTA_USUARIOS.write_text(
        json.dumps(usuarios, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cargar_usuarios() -> list[dict]:
    return [u for u in cargar_todos_usuarios() if u.get("activo", True)]


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
    responsabilidades = u.get("responsable_de") or []
    if isinstance(responsabilidades, str):
        responsabilidades = [x.strip() for x in responsabilidades.replace(";", ",").split(",") if x.strip()]
    u["responsable_de"] = responsabilidades
    u["activo"] = bool(u.get("activo", True))
    return u


def crear_usuario(usuario: dict) -> None:
    nuevo = _normalizar_usuario(usuario)
    if not nuevo["correo"] or "@" not in nuevo["correo"]:
        raise ValueError("Debes ingresar un correo válido.")
    if not nuevo["nombre"]:
        raise ValueError("Debes ingresar el nombre del usuario.")
    usuarios = cargar_todos_usuarios()
    if any((u.get("correo") or "").lower() == nuevo["correo"] for u in usuarios):
        raise ValueError("Ya existe una cuenta con ese correo.")
    usuarios.append(nuevo)
    guardar_usuarios(usuarios)


def actualizar_usuario(correo_original: str, cambios: dict) -> None:
    original = (correo_original or "").strip().lower()
    usuarios = cargar_todos_usuarios()
    indice = next((i for i, u in enumerate(usuarios) if (u.get("correo") or "").lower() == original), None)
    if indice is None:
        raise ValueError("No se encontró la cuenta a editar.")
    actualizado = _normalizar_usuario({**usuarios[indice], **cambios})
    if not actualizado["correo"] or "@" not in actualizado["correo"]:
        raise ValueError("Debes ingresar un correo válido.")
    if any(i != indice and (u.get("correo") or "").lower() == actualizado["correo"] for i, u in enumerate(usuarios)):
        raise ValueError("Ya existe otra cuenta con ese correo.")
    usuarios[indice] = actualizado
    guardar_usuarios(usuarios)


def eliminar_usuario(correo: str) -> bool:
    objetivo = (correo or "").strip().lower()
    usuarios = cargar_todos_usuarios()
    nuevos = [u for u in usuarios if (u.get("correo") or "").lower() != objetivo]
    if len(nuevos) == len(usuarios):
        return False
    guardar_usuarios(nuevos)
    return True


def buscar_usuario_por_correo(correo: str) -> dict | None:
    objetivo = (correo or "").strip().lower()
    coincidencias = [u for u in cargar_usuarios() if u.get("correo", "").lower() == objetivo]
    if not coincidencias:
        return None
    prioridad = {"subgerente": 6, "jefe": 5, "ingeniero": 4, "supervisor": 3, "senior": 2, "tecnico": 1}
    usuario = max(coincidencias, key=lambda u: prioridad.get(u.get("rol", "").lower(), 0)).copy()
    usuario.setdefault("centro", "")
    usuario.setdefault("planta", nombre_centro(usuario.get("centro", "")))
    usuario.setdefault("responsable_de", [])
    return usuario


def _areas_responsabilidad(usuario: dict) -> set[str]:
    explicitas = usuario.get("responsable_de") or []
    if isinstance(explicitas, str):
        explicitas = [p.strip() for p in explicitas.replace(";", ",").split(",") if p.strip()]
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
    if not candidatos:
        return None
    return sorted(candidatos, key=lambda x: (x.get("nombre", ""), x.get("correo", "")))[0]


def resolver_supervisor(centro: str, area: str) -> dict | None:
    return _resolver_responsable(centro, area, "supervisor")


def resolver_jefe(centro: str, area: str) -> dict | None:
    return _resolver_responsable(centro, area, "jefe")


def resumen_maestro() -> dict:
    usuarios = cargar_usuarios()
    conteo = {}
    centros = set()
    for u in usuarios:
        rol = u.get("rol", "sin rol").capitalize()
        conteo[rol] = conteo.get(rol, 0) + 1
        if u.get("centro"):
            centros.add(str(u["centro"]))
    return {"total": len(usuarios), "roles": conteo, "centros": len(centros)}
