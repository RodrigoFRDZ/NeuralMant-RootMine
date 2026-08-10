from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import ADF, ValidacionADF
from database.notificaciones import crear_notificacion


def guardar_adf(datos: dict) -> int:
    with Session(engine) as session:
        adf = ADF(**datos)
        session.add(adf)
        session.commit()
        session.refresh(adf)
        return adf.id


def actualizar_adf(adf_id: int, datos: dict) -> int:
    """Actualiza un ADF existente conservando su ID y trazabilidad de validaciones."""
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            raise ValueError(f"ADF #{adf_id} no existe.")
        campos_permitidos = {
            "creado_por", "creado_por_email", "centro", "planta", "area",
            "numero_equipo", "equipo", "aviso_sap", "tiempo_perdido_h", "relato_original",
            "analisis_ia", "efecto", "investigacion_web", "fuentes_web",
            "ishikawa", "causas_priorizadas", "cadenas_causales", "conclusion",
            "plan_prevencion", "leccion_aprendida",
        }
        for campo, valor in datos.items():
            if campo in campos_permitidos:
                setattr(adf, campo, valor)
        # Al corregir un rechazo, vuelve a borrador hasta que el creador lo reenvíe.
        adf.estado = "Borrador"
        adf.etapa = "Corrección posterior a rechazo"
        adf.comentario_validacion = ""
        adf.fecha_aprobacion_supervisor = None
        adf.fecha_aprobacion_jefe = None
        adf.pdf_archivo = None
        session.commit()
        session.refresh(adf)
        return adf.id


def listar_requiere_correccion_para(email: str) -> list[ADF]:
    email = (email or "").lower().strip()
    if not email:
        return []
    with Session(engine) as session:
        consulta = (
            select(ADF)
            .where(ADF.creado_por_email == email, ADF.estado.in_(["Requiere corrección", "Rechazado"]))
            .order_by(ADF.fecha_actualizacion.desc())
        )
        return list(session.scalars(consulta).all())



def guardar_pdf_adf(adf_id: int, pdf_bytes: bytes) -> None:
    """Persiste el PDF generado para que pueda descargarse desde Historial."""
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            return
        adf.pdf_archivo = pdf_bytes
        session.commit()


def actualizar_plan_prevencion(adf_id: int, plan: list[dict]) -> None:
    """Guarda el seguimiento de acciones y sus respaldos dentro del ADF."""
    import json
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            raise ValueError(f"ADF #{adf_id} no existe.")
        adf.plan_prevencion = json.dumps(plan, ensure_ascii=False)
        adf.fecha_actualizacion = datetime.now()
        session.commit()

def listar_adf() -> list[ADF]:
    with Session(engine) as session:
        consulta = select(ADF).order_by(ADF.fecha_actualizacion.desc())
        return list(session.scalars(consulta).all())


def obtener_adf(adf_id: int) -> ADF | None:
    with Session(engine) as session:
        return session.get(ADF, adf_id)


def listar_pendientes_para(email: str, rol: str, centro: str = "") -> list[ADF]:
    email = (email or "").lower().strip()
    rol = (rol or "").lower().strip()
    centro = str(centro or "").strip()
    with Session(engine) as session:
        consulta = select(ADF)
        if rol == "supervisor":
            consulta = consulta.where(ADF.estado == "Pendiente Supervisor", ADF.supervisor_email == email)
        elif rol == "jefe":
            consulta = consulta.where(ADF.estado == "Pendiente Jefe", ADF.jefe_email == email)
        elif rol in {"ingeniero", "subgerente"}:
            consulta = consulta.where(ADF.estado.in_(["Pendiente Supervisor", "Pendiente Jefe"]))
            # Ingeniero y Subgerente tienen visibilidad transversal dentro de su planta/centro.
            if centro:
                consulta = consulta.where(ADF.centro == centro)
        else:
            return []
        consulta = consulta.order_by(ADF.fecha_actualizacion.desc())
        return list(session.scalars(consulta).all())


def registrar_envio_validacion(adf_id: int, supervisor: dict | None, jefe: dict | None) -> None:
    supervisor = supervisor or {}
    jefe = jefe or {}
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            return
        adf.estado = "Pendiente Supervisor"
        adf.etapa = "Validación Supervisor"
        adf.supervisor_nombre = supervisor.get("nombre", "")
        adf.supervisor_email = supervisor.get("correo", "").lower()
        adf.jefe_nombre = jefe.get("nombre", "")
        adf.jefe_email = jefe.get("correo", "").lower()
        adf.fecha_envio_validacion = datetime.now()
        adf.comentario_validacion = ""
        destino = adf.supervisor_nombre or "Ingeniero de mantenimiento (reemplazo)"
        session.add(ValidacionADF(
            adf_id=adf_id, etapa="Envío", accion="Enviado",
            usuario_nombre=adf.creado_por, usuario_email=adf.creado_por_email,
            comentario=f"Enviado a {destino} para validación.",
        ))
        session.commit()
        if adf.supervisor_email:
            crear_notificacion(
                adf.supervisor_email,
                f"ADF #{adf.id} pendiente de validación",
                f"{adf.area} · {adf.equipo} · requiere validación de Supervisor.",
                adf_id=adf.id, tipo="pendiente",
            )


def aplicar_validacion(adf_id: int, usuario: dict, accion: str, comentario: str = "") -> ADF | None:
    accion = accion.strip().lower()
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            return None
        rol = usuario.get("rol", "").lower()
        email = usuario.get("correo", "").lower()
        nombre = usuario.get("nombre", "")
        etapa = "Supervisor" if adf.estado == "Pendiente Supervisor" else "Jefe"

        mismo_centro = str(usuario.get("centro", "")).strip() == str(adf.centro or "").strip()
        autorizado = (
            (adf.estado == "Pendiente Supervisor" and (email == adf.supervisor_email or (rol == "ingeniero" and mismo_centro)))
            or (adf.estado == "Pendiente Jefe" and (email == adf.jefe_email or (rol == "ingeniero" and mismo_centro)))
        )
        if not autorizado:
            raise PermissionError("El usuario no está autorizado para validar este ADF.")

        reemplazo = rol == "ingeniero" and (
            (etapa == "Supervisor" and email != adf.supervisor_email)
            or (etapa == "Jefe" and email != adf.jefe_email)
        )
        comentario_registro = comentario.strip()
        if reemplazo:
            prefijo = f"Aprobación extraordinaria como reemplazo de {etapa}." if accion == "aprobar" else f"Rechazo extraordinario como reemplazo de {etapa}."
            comentario_registro = f"{prefijo} {comentario_registro}".strip()

        if accion == "rechazar":
            if not comentario.strip():
                raise ValueError("El rechazo requiere un comentario.")
            adf.estado = "Requiere corrección"
            adf.etapa = f"Rechazado por {etapa}"
            adf.comentario_validacion = comentario_registro
        elif accion == "aprobar":
            if etapa == "Supervisor":
                adf.estado = "Pendiente Jefe"
                adf.etapa = "Validación Jefe"
                adf.fecha_aprobacion_supervisor = datetime.now()
                adf.comentario_validacion = comentario_registro
            else:
                adf.estado = "Aprobado"
                adf.etapa = "ADF Aprobado"
                adf.fecha_aprobacion_jefe = datetime.now()
                adf.comentario_validacion = comentario_registro
        else:
            raise ValueError("Acción de validación no reconocida.")

        adf.ultima_validacion_por = email
        session.add(ValidacionADF(
            adf_id=adf_id, etapa=etapa, accion=accion.capitalize(),
            usuario_nombre=nombre, usuario_email=email, comentario=comentario_registro,
        ))
        session.commit()
        session.refresh(adf)

        if accion == "aprobar" and etapa == "Supervisor" and adf.jefe_email:
            crear_notificacion(
                adf.jefe_email, f"ADF #{adf.id} pendiente de aprobación final",
                f"{adf.area} · {adf.equipo} · validación de Supervisor completada.",
                adf_id=adf.id, tipo="pendiente",
            )
        if adf.creado_por_email:
            if accion == "rechazar":
                crear_notificacion(
                    adf.creado_por_email, f"ADF #{adf.id} rechazado",
                    f"{etapa}: {comentario.strip()}", adf_id=adf.id, tipo="rechazo",
                )
            elif etapa == "Jefe":
                crear_notificacion(
                    adf.creado_por_email, f"ADF #{adf.id} aprobado",
                    "El flujo de validación finalizó correctamente.", adf_id=adf.id, tipo="aprobado",
                )
        return adf


def historial_validaciones(adf_id: int) -> list[ValidacionADF]:
    with Session(engine) as session:
        consulta = select(ValidacionADF).where(ValidacionADF.adf_id == adf_id).order_by(ValidacionADF.fecha.asc())
        return list(session.scalars(consulta).all())
