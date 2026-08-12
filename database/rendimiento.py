from __future__ import annotations
import json
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, load_only
from database.conexion import engine
from database.modelos import ADF

def resumen_dashboard() -> dict:
    with Session(engine) as session:
        aprobados = session.scalar(select(func.count(ADF.id)).where(ADF.estado == "Aprobado")) or 0
        equipos = session.scalar(select(func.count(distinct(ADF.equipo))).where(ADF.estado == "Aprobado", ADF.equipo.is_not(None), ADF.equipo != "")) or 0
        areas = session.scalar(select(func.count(distinct(ADF.area))).where(ADF.estado == "Aprobado", ADF.area.is_not(None), ADF.area != "")) or 0
        con_ia = session.scalar(select(func.count(ADF.id)).where(ADF.analisis_ia.is_not(None), ADF.analisis_ia != "")) or 0
        planes_texto = session.scalars(select(ADF.plan_prevencion).where(ADF.plan_prevencion.is_not(None), ADF.plan_prevencion != "")).all()
    acciones = 0
    for texto in planes_texto:
        try:
            data = json.loads(texto or "[]")
            if isinstance(data, list): acciones += len(data)
        except Exception: pass
    return {"aprobados": int(aprobados), "equipos": int(equipos), "areas": int(areas), "con_ia": int(con_ia), "acciones": int(acciones)}

def borradores_livianos(email: str, limite: int = 8):
    email=(email or "").strip().lower()
    if not email: return []
    with Session(engine) as session:
        q=(select(ADF).options(load_only(ADF.id,ADF.estado,ADF.etapa,ADF.centro,ADF.area,ADF.equipo,ADF.creado_por_email,ADF.fecha_actualizacion)).where(ADF.creado_por_email==email,ADF.estado=="Borrador").order_by(ADF.fecha_actualizacion.desc()).limit(limite))
        return list(session.scalars(q).all())

def correcciones_livianas(email: str, limite: int = 12):
    email=(email or "").strip().lower()
    if not email: return []
    with Session(engine) as session:
        q=(select(ADF).options(load_only(ADF.id,ADF.estado,ADF.etapa,ADF.area,ADF.equipo,ADF.creado_por_email,ADF.comentario_validacion,ADF.fecha_actualizacion)).where(ADF.creado_por_email==email,ADF.estado.in_(["Requiere corrección","Rechazado"])).order_by(ADF.fecha_actualizacion.desc()).limit(limite))
        return list(session.scalars(q).all())

def contar_pendientes(email: str, rol: str, centro: str = "") -> int:
    email=(email or "").strip().lower(); rol=(rol or "").strip().lower(); centro=str(centro or "").strip()
    if not email: return 0
    with Session(engine) as session:
        q=select(func.count(ADF.id))
        if rol=="supervisor": q=q.where(ADF.estado.in_(["Pendiente Supervisor","Devuelto por Jefatura"]),ADF.supervisor_email==email)
        elif rol=="jefe": q=q.where(ADF.estado=="Pendiente Jefe",ADF.jefe_email==email)
        elif rol in {"ingeniero","subgerente"}:
            q=q.where(ADF.estado.in_(["Pendiente Supervisor","Pendiente Jefe","Devuelto por Jefatura"]))
            if centro: q=q.where(ADF.centro==centro)
        else: return 0
        return int(session.scalar(q) or 0)


def recientes_livianos(limite: int = 6):
    """Últimos ADF para el dashboard sin cargar PDFs, respaldos ni análisis extensos."""
    with Session(engine) as session:
        q = (
            select(ADF)
            .options(load_only(
                ADF.id,
                ADF.estado,
                ADF.centro,
                ADF.planta,
                ADF.area,
                ADF.numero_equipo,
                ADF.equipo,
                ADF.efecto,
                ADF.conclusion,
                ADF.fecha_actualizacion,
            ))
            .order_by(ADF.fecha_actualizacion.desc())
            .limit(limite)
        )
        return list(session.scalars(q).all())
