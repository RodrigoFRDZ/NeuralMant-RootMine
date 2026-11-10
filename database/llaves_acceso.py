import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import LlaveAcceso

ROLES_CON_LLAVE = {"supervisor", "coordinador_mantenimiento", "coordinador", "jefe", "ingeniero", "subgerente", "analizador_materiales"}
ITERACIONES = 600_000
ITERACIONES_ANTERIORES = 210_000
# Process-local throttle; production deployment should replace with shared DB/Redis
# limits if more than one server instance is used.
_INTENTOS = {}
_INTENTOS_LOCK = Lock()

def intento_permitido(correo: str) -> bool:
    correo = (correo or "").strip().lower()
    with _INTENTOS_LOCK:
        registro = _INTENTOS.get(correo)
        if not registro:
            return True
        fallos, inicio = registro
        if datetime.now() - inicio > timedelta(minutes=15):
            _INTENTOS.pop(correo, None)
            return True
        return fallos < 5

def registrar_intento(correo: str, correcto: bool) -> None:
    correo = (correo or "").strip().lower()
    with _INTENTOS_LOCK:
        if correcto:
            _INTENTOS.pop(correo, None)
        else:
            fallos, inicio = _INTENTOS.get(correo, (0, datetime.now()))
            if datetime.now() - inicio > timedelta(minutes=15):
                fallos, inicio = 0, datetime.now()
            _INTENTOS[correo] = (fallos + 1, inicio)

ROLES_AUTOACTIVACION = {"tecnico", "senior", "programador_mantenimiento", "ingeniero_confiabilidad", "ingeniero_procesos"}

def puede_autoactivar(usuario: dict | None) -> bool:
    return bool(usuario and usuario.get("activo", True) and
                not usuario.get("es_admin", False) and
                str(usuario.get("rol") or "").strip().lower() in ROLES_AUTOACTIVACION)



def requiere_llave(usuario: dict | None) -> bool:
    if not usuario:
        return False
    return True


def _derivar(llave: str, salt: bytes, iteraciones: int = ITERACIONES) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", llave.encode("utf-8"), salt, iteraciones)


def tiene_llave(correo: str) -> bool:
    correo = (correo or "").strip().lower()
    if not correo:
        return False
    with Session(engine) as session:
        return session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo)) is not None


def crear_llave(correo: str, llave: str) -> None:
    correo = (correo or "").strip().lower()
    llave = (llave or "").strip()
    if len(llave) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")
    if tiene_llave(correo):
        raise ValueError("Este usuario ya tiene una llave creada.")

    salt = os.urandom(16)
    digest = _derivar(llave, salt)
    with Session(engine) as session:
        session.add(
            LlaveAcceso(
                correo=correo,
                salt_b64=base64.b64encode(salt).decode("ascii"),
                hash_b64=base64.b64encode(digest).decode("ascii"),
                fecha_creacion=datetime.now(),
            )
        )
        session.commit()


def validar_llave(correo: str, llave: str) -> bool:
    """Admite claves existentes (210k) y nuevas (600k), migrando al validar.

    No altera ninguna clave cuando la contraseña es incorrecta.
    """
    correo = (correo or "").strip().lower()
    with Session(engine) as session:
        registro = session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo))
        if not registro:
            return False
        salt = base64.b64decode(registro.salt_b64.encode("ascii"))
        esperado = base64.b64decode(registro.hash_b64.encode("ascii"))
        # Nunca eliminar espacios de una contraseña ya establecida: son significativos.
        clave = llave or ""
        actual = _derivar(clave, salt, ITERACIONES)
        if hmac.compare_digest(esperado, actual):
            return True
        anterior = _derivar(clave, salt, ITERACIONES_ANTERIORES)
        if not hmac.compare_digest(esperado, anterior):
            return False
        # Rehash transparente al algoritmo actual, con sal nueva.
        sal_nueva = os.urandom(16)
        registro.salt_b64 = base64.b64encode(sal_nueva).decode("ascii")
        registro.hash_b64 = base64.b64encode(_derivar(clave, sal_nueva, ITERACIONES)).decode("ascii")
        session.commit()
        return True


def eliminar_llave(correo: str) -> bool:
    correo = (correo or "").strip().lower()
    with Session(engine) as session:
        registro = session.scalar(select(LlaveAcceso).where(LlaveAcceso.correo == correo))
        if not registro:
            return False
        session.delete(registro)
        session.commit()
        return True
