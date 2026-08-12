from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from database.conexion import engine, usando_nube, DB_PATH
from database.modelos import UsoIA


TZ_CHILE = ZoneInfo("America/Santiago")
LIMITE_DB_FREE_BYTES = 500 * 1024 * 1024


def _utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def registrar_uso_ia(modelo: str, operacion: str, resultado: str = "ok", usuario_email: str = "") -> None:
    """Registra una llamada enviada a Gemini. Nunca debe interrumpir RootMine si falla el contador."""
    try:
        with Session(engine) as session:
            session.add(UsoIA(
                modelo=(modelo or "")[:120],
                operacion=(operacion or "")[:120],
                resultado=(resultado or "ok")[:40],
                usuario_email=(usuario_email or "").lower()[:180],
            ))
            session.commit()
    except Exception:
        pass


def resumen_uso_ia() -> dict:
    """Cuenta llamadas enviadas por RootMine. Es un contador interno, no el dashboard oficial de Google."""
    ahora_local = datetime.now(TZ_CHILE)
    inicio_hora_utc = _utc_naive(ahora_local - timedelta(hours=1))
    inicio_dia_local = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_dia_utc = _utc_naive(inicio_dia_local)

    try:
        with Session(engine) as session:
            ultima_hora = session.scalar(
                select(func.count(UsoIA.id)).where(UsoIA.fecha >= inicio_hora_utc)
            ) or 0
            hoy = session.scalar(
                select(func.count(UsoIA.id)).where(UsoIA.fecha >= inicio_dia_utc)
            ) or 0
            cuotas = session.scalar(
                select(func.count(UsoIA.id)).where(
                    UsoIA.fecha >= inicio_dia_utc,
                    UsoIA.resultado == "cuota",
                )
            ) or 0
        return {"ultima_hora": int(ultima_hora), "hoy": int(hoy), "rechazos_cuota_hoy": int(cuotas)}
    except Exception as exc:
        return {"ultima_hora": 0, "hoy": 0, "rechazos_cuota_hoy": 0, "error": str(exc)}


def uso_base_datos() -> dict:
    """Devuelve uso de la base operacional. En Supabase Free la cuota de DB es 500 MB."""
    try:
        if usando_nube() and engine.dialect.name == "postgresql":
            with engine.connect() as conn:
                usados = int(conn.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0)
            limite = LIMITE_DB_FREE_BYTES
            return {
                "backend": "Supabase PostgreSQL",
                "usados_bytes": usados,
                "limite_bytes": limite,
                "disponibles_bytes": max(0, limite - usados),
                "porcentaje": min(100.0, usados / limite * 100 if limite else 0.0),
            }

        ruta = Path(DB_PATH)
        usados = ruta.stat().st_size if ruta.exists() else 0
        return {
            "backend": "SQLite local",
            "usados_bytes": usados,
            "limite_bytes": 0,
            "disponibles_bytes": 0,
            "porcentaje": 0.0,
        }
    except Exception as exc:
        return {
            "backend": "No disponible",
            "usados_bytes": 0,
            "limite_bytes": 0,
            "disponibles_bytes": 0,
            "porcentaje": 0.0,
            "error": str(exc),
        }


def mb(valor: int) -> float:
    return round((valor or 0) / (1024 * 1024), 1)
