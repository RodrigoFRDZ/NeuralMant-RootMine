"""Períodos de efectividad por ADF, fijados al iniciar seguimiento."""
from datetime import date
from sqlalchemy import text
from database.conexion import engine

def obtener_o_fijar_periodo(adf_id, inicio, plazo, fundamento, confianza):
    """Retorna (dias, fundamento, confianza). No recalcula una vez registrado."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS adf_periodos_efectividad (
                adf_id INTEGER PRIMARY KEY,
                inicio DATE NOT NULL,
                plazo_dias INTEGER NOT NULL,
                fundamento TEXT NOT NULL,
                confianza VARCHAR(30) NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        registro = conn.execute(text("""
            SELECT inicio, plazo_dias, fundamento, confianza
            FROM adf_periodos_efectividad WHERE adf_id=:id
        """), {"id":int(adf_id)}).mappings().first()
        if registro:
            # La fecha real corregida requiere revisión administrativa;
            # no alterar automáticamente el plazo histórico.
            return (int(registro["plazo_dias"]), str(registro["fundamento"]),
                    str(registro["confianza"]), str(registro["inicio"]))
        conn.execute(text("""
            INSERT INTO adf_periodos_efectividad
            (adf_id,inicio,plazo_dias,fundamento,confianza)
            VALUES (:id,:inicio,:plazo,:fundamento,:confianza)
        """), {"id":int(adf_id),"inicio":inicio,"plazo":int(plazo),
               "fundamento":fundamento,"confianza":confianza})
        return int(plazo),fundamento,confianza,str(inicio)
