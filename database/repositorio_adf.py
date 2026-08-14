from datetime import datetime
import base64
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.conexion import engine
from database.modelos import ADF, ValidacionADF, NotificacionInterna
from database.notificaciones import crear_notificacion

ADMIN_CORREOS = {"rfernandezc@agrosuper.com"}


def _codificar_borrador(valor):
    if isinstance(valor, (bytes, bytearray)):
        return {"__rootmine_bytes__": base64.b64encode(bytes(valor)).decode("ascii")}
    if isinstance(valor, dict):
        return {str(k): _codificar_borrador(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_codificar_borrador(v) for v in valor]
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _decodificar_borrador(valor):
    if isinstance(valor, dict):
        if set(valor.keys()) == {"__rootmine_bytes__"}:
            try:
                return base64.b64decode(valor["__rootmine_bytes__"])
            except Exception:
                return None
        return {k: _decodificar_borrador(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_decodificar_borrador(v) for v in valor]
    return valor


def _serializar_borrador(datos: dict) -> str:
    limpio = {k: v for k, v in (datos or {}).items() if k != "pdf_bytes"}
    return json.dumps(_codificar_borrador(limpio), ensure_ascii=False)


def _deserializar_borrador(texto: str) -> dict:
    try:
        return _decodificar_borrador(json.loads(texto or "{}"))
    except Exception:
        return {}


ETAPAS_BORRADOR = {
    1: "Borrador · Contexto",
    2: "Borrador · Diagnóstico",
    3: "Borrador · Ishikawa",
    4: "Borrador · Priorización",
    5: "Borrador · 5 Porqués",
    6: "Borrador · Planes de acción",
    7: "Borrador · Informe",
    8: "Borrador · PDF / envío",
    9: "Borrador · Resumen final",
}


def guardar_borrador_adf(datos: dict, usuario: dict, paso: int) -> int:
    usuario = usuario or {}
    adf_id = datos.get("id_guardado") or datos.get("id_edicion")
    paso = max(1, min(int(paso or 1), 9))
    etapa = ETAPAS_BORRADOR.get(paso, f"Borrador · Etapa {paso}")
    correo = (usuario.get("correo") or "").strip().lower()
    nombre = (usuario.get("nombre") or "Usuario").strip()

    with Session(engine) as session:
        adf = session.get(ADF, int(adf_id)) if adf_id else None
        if adf is None:
            adf = ADF(
                creado_por=nombre, creado_por_email=correo, estado="Borrador", etapa=etapa,
                centro=str(datos.get("centro") or usuario.get("centro") or ""),
                planta=str(datos.get("planta") or usuario.get("planta") or ""),
                area=str(datos.get("area") or "Sin definir"),
                numero_equipo=str(datos.get("numero_equipo") or ""),
                equipo=str(datos.get("equipo") or "ADF en progreso"),
                aviso_sap=str(datos.get("aviso_sap") or ""),
                tiempo_perdido_h=float(datos.get("tiempo_perdido_h") or 0),
                relato_original=str(datos.get("relato_original") or "Borrador en progreso"),
            )
            session.add(adf)
            session.flush()
        elif adf.estado not in {"Borrador", "Requiere corrección", "Rechazado"}:
            return adf.id
        else:
            adf.estado = "Borrador"
            adf.etapa = etapa
            adf.centro = str(datos.get("centro") or adf.centro or "")
            adf.planta = str(datos.get("planta") or adf.planta or "")
            adf.area = str(datos.get("area") or adf.area or "Sin definir")
            adf.numero_equipo = str(datos.get("numero_equipo") or adf.numero_equipo or "")
            adf.equipo = str(datos.get("equipo") or adf.equipo or "ADF en progreso")
            adf.aviso_sap = str(datos.get("aviso_sap") or adf.aviso_sap or "")
            adf.tiempo_perdido_h = float(datos.get("tiempo_perdido_h") or adf.tiempo_perdido_h or 0)
            adf.relato_original = str(datos.get("relato_original") or adf.relato_original or "Borrador en progreso")

        if datos.get("diagnostico") is not None:
            adf.analisis_ia = json.dumps(datos.get("diagnostico"), ensure_ascii=False)
        if datos.get("efecto"):
            adf.efecto = str(datos.get("efecto"))
        if datos.get("principio_funcionamiento"):
            adf.investigacion_web = str(datos.get("principio_funcionamiento"))
        if datos.get("ishikawa_validado"):
            adf.ishikawa = json.dumps(datos.get("ishikawa_validado"), ensure_ascii=False)
        if datos.get("causas_priorizadas"):
            adf.causas_priorizadas = json.dumps(datos.get("causas_priorizadas"), ensure_ascii=False)
        if datos.get("cadenas_causales"):
            adf.cadenas_causales = json.dumps(datos.get("cadenas_causales"), ensure_ascii=False)
        if datos.get("plan_prevencion"):
            adf.plan_prevencion = json.dumps(datos.get("plan_prevencion"), ensure_ascii=False)
        informe = datos.get("informe_final") or {}
        if isinstance(informe, dict):
            adf.conclusion = str(informe.get("conclusion_tecnica") or adf.conclusion or "")
            adf.leccion_aprendida = str(informe.get("leccion_aprendida") or adf.leccion_aprendida or "")

        snapshot = dict(datos)
        snapshot["id_guardado"] = adf.id
        snapshot["paso"] = paso
        adf.borrador_paso = paso
        adf.borrador_json = _serializar_borrador(snapshot)
        adf.fecha_actualizacion = datetime.now()
        session.commit()
        session.refresh(adf)
        return adf.id


def actualizar_contenido_borrador(adf_id: int, datos: dict) -> int:
    with Session(engine) as session:
        adf = session.get(ADF, int(adf_id))
        if not adf:
            raise ValueError(f"ADF #{adf_id} no existe.")
        campos = {
            "creado_por", "creado_por_email", "centro", "planta", "area", "numero_equipo",
            "equipo", "aviso_sap", "tiempo_perdido_h", "relato_original", "analisis_ia",
            "efecto", "investigacion_web", "fuentes_web", "ishikawa", "causas_priorizadas",
            "cadenas_causales", "conclusion", "plan_prevencion", "leccion_aprendida",
        }
        for campo, valor in datos.items():
            if campo in campos:
                setattr(adf, campo, valor)
        adf.estado = "Borrador"
        adf.etapa = "Informe PDF"
        adf.borrador_paso = 8
        adf.fecha_actualizacion = datetime.now()
        session.commit()
        return adf.id


def listar_borradores_para(email: str) -> list[ADF]:
    email = (email or "").strip().lower()
    if not email:
        return []
    with Session(engine) as session:
        consulta = select(ADF).where(
            ADF.creado_por_email == email, ADF.estado == "Borrador"
        ).order_by(ADF.fecha_actualizacion.desc())
        return list(session.scalars(consulta).all())



def buscar_borrador_coincidente(
    email: str,
    numero_equipo: str = "",
    equipo: str = "",
    excluir_id: int | None = None,
) -> dict | None:
    """Busca un borrador del mismo usuario y activo antes de iniciar otro ADF."""
    email = (email or "").strip().lower()
    numero = (numero_equipo or "").strip().lower()
    descripcion = " ".join((equipo or "").strip().lower().split())
    if not email or (not numero and not descripcion):
        return None

    with Session(engine) as session:
        consulta = (
            select(ADF)
            .where(ADF.creado_por_email == email, ADF.estado == "Borrador")
            .order_by(ADF.fecha_actualizacion.desc())
        )
        for adf in session.scalars(consulta).all():
            if excluir_id and int(adf.id) == int(excluir_id):
                continue
            numero_adf = (adf.numero_equipo or "").strip().lower()
            desc_adf = " ".join((adf.equipo or "").strip().lower().split())
            mismo_numero = bool(numero and numero_adf and numero == numero_adf)
            misma_desc = bool(descripcion and desc_adf and (
                descripcion == desc_adf or descripcion in desc_adf or desc_adf in descripcion
            ))
            if mismo_numero or misma_desc:
                return {
                    "id": adf.id,
                    "equipo": adf.equipo or "Análisis sin título",
                    "numero_equipo": adf.numero_equipo or "",
                    "area": adf.area or "",
                    "etapa": adf.etapa or "Borrador",
                    "fecha_actualizacion": adf.fecha_actualizacion,
                }
    return None


def eliminar_borrador_adf(adf_id: int, email: str) -> bool:
    """Elimina solo un borrador propio; no permite borrar ADF enviados/aprobados."""
    email = (email or "").strip().lower()
    if not email:
        return False
    with Session(engine) as session:
        adf = session.get(ADF, int(adf_id))
        if not adf:
            return False
        if (adf.creado_por_email or "").strip().lower() != email:
            raise PermissionError("Solo el creador puede eliminar este borrador.")
        if adf.estado != "Borrador":
            raise ValueError("Solo se pueden eliminar análisis que todavía estén en estado Borrador.")

        validaciones = list(session.scalars(
            select(ValidacionADF).where(ValidacionADF.adf_id == adf.id)
        ).all())
        notificaciones = list(session.scalars(
            select(NotificacionInterna).where(NotificacionInterna.adf_id == adf.id)
        ).all())
        for item in validaciones:
            session.delete(item)
        for item in notificaciones:
            session.delete(item)
        session.delete(adf)
        session.commit()
        return True


def cargar_borrador_adf(adf_id: int, email: str) -> dict | None:
    email = (email or "").strip().lower()
    with Session(engine) as session:
        adf = session.get(ADF, int(adf_id))
        if not adf or adf.estado != "Borrador" or (adf.creado_por_email or "").strip().lower() != email:
            return None
        datos = _deserializar_borrador(adf.borrador_json or "")
        if not datos:
            datos = {
                "paso": int(getattr(adf, "borrador_paso", 1) or 1),
                "centro": adf.centro or "", "planta": adf.planta or "", "area": adf.area or "",
                "numero_equipo": adf.numero_equipo or "", "equipo": adf.equipo or "",
                "aviso_sap": adf.aviso_sap or "", "tiempo_perdido_h": float(adf.tiempo_perdido_h or 0),
                "relato_original": adf.relato_original or "",
            }
        datos["id_guardado"] = adf.id
        datos["paso"] = int(getattr(adf, "borrador_paso", None) or datos.get("paso") or 1)
        datos["estado_validacion"] = adf.estado
        datos["pdf_bytes"] = adf.pdf_archivo
        return datos


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
            consulta = consulta.where(
                ADF.estado.in_(["Pendiente Supervisor", "Devuelto por Jefatura"]),
                ADF.supervisor_email == email,
            )
        elif rol == "jefe":
            consulta = consulta.where(ADF.estado == "Pendiente Jefe", ADF.jefe_email == email)
        elif email in ADMIN_CORREOS or rol == "subgerente":
            consulta = consulta.where(ADF.estado.in_(["Pendiente Supervisor", "Pendiente Jefe", "Devuelto por Jefatura"]))
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
            (adf.estado == "Pendiente Supervisor" and (email == adf.supervisor_email or (email in ADMIN_CORREOS and mismo_centro)))
            or (adf.estado == "Pendiente Jefe" and (email == adf.jefe_email or (email in ADMIN_CORREOS and mismo_centro)))
        )
        if not autorizado:
            raise PermissionError("El usuario no está autorizado para validar este ADF.")

        reemplazo = email in ADMIN_CORREOS and (
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
            if etapa == "Supervisor":
                adf.estado = "Requiere corrección"
                adf.etapa = "Rechazado por Supervisor"
            else:
                adf.estado = "Devuelto por Jefatura"
                adf.etapa = "Revisión Supervisor por observación de Jefatura"
                adf.fecha_aprobacion_jefe = None
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
        if accion == "rechazar":
            if etapa == "Supervisor" and adf.creado_por_email:
                crear_notificacion(
                    adf.creado_por_email,
                    f"ADF #{adf.id} devuelto para corrección",
                    f"Supervisor: {comentario.strip()}",
                    adf_id=adf.id, tipo="rechazo",
                )
            elif etapa == "Jefe" and adf.supervisor_email:
                crear_notificacion(
                    adf.supervisor_email,
                    f"ADF #{adf.id} devuelto por Jefatura",
                    f"Observación de Jefatura: {comentario.strip()}",
                    adf_id=adf.id, tipo="rechazo_jefatura",
                )
        elif accion == "aprobar" and etapa == "Jefe" and adf.creado_por_email:
            crear_notificacion(
                adf.creado_por_email,
                f"ADF #{adf.id} aprobado",
                "El flujo de validación finalizó correctamente.",
                adf_id=adf.id, tipo="aprobado",
            )
        return adf



def resolver_devolucion_jefatura(adf_id: int, usuario: dict, accion: str, comentario: str = "") -> ADF | None:
    accion = (accion or "").strip().lower()
    email = (usuario.get("correo") or "").strip().lower()
    nombre = usuario.get("nombre", "")
    centro_usuario = str(usuario.get("centro", "") or "").strip()

    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            return None
        if adf.estado != "Devuelto por Jefatura":
            raise ValueError("Este ADF ya no está pendiente de revisión por devolución de Jefatura.")

        mismo_centro = centro_usuario == str(adf.centro or "").strip()
        autorizado = email == (adf.supervisor_email or "").lower() or (email in ADMIN_CORREOS and mismo_centro)
        if not autorizado:
            raise PermissionError("El usuario no está autorizado para gestionar esta devolución.")

        observacion_jefatura = adf.comentario_validacion or ""
        comentario_supervisor = (comentario or "").strip()

        if accion == "devolver_creador":
            if not comentario_supervisor:
                raise ValueError("Agrega una indicación para que el creador sepa qué debe corregir.")
            adf.estado = "Requiere corrección"
            adf.etapa = "Devuelto al creador por Supervisor"
            adf.comentario_validacion = (
                f"Jefatura: {observacion_jefatura}\nSupervisor: {comentario_supervisor}"
            ).strip()
            adf.fecha_aprobacion_supervisor = None
            session.add(ValidacionADF(
                adf_id=adf.id, etapa="Supervisor · devolución Jefatura",
                accion="Devuelto al creador", usuario_nombre=nombre,
                usuario_email=email, comentario=comentario_supervisor,
            ))
            session.commit(); session.refresh(adf)
            if adf.creado_por_email:
                crear_notificacion(
                    adf.creado_por_email, f"ADF #{adf.id} requiere corrección",
                    f"Jefatura observó el ADF. Supervisor indica: {comentario_supervisor}",
                    adf_id=adf.id, tipo="rechazo",
                )
            return adf

        if accion == "reenviar_jefe":
            adf.estado = "Pendiente Jefe"
            adf.etapa = "Reenviado a Jefatura por Supervisor"
            if comentario_supervisor:
                adf.comentario_validacion = (
                    f"Jefatura: {observacion_jefatura}\nSupervisor: {comentario_supervisor}"
                ).strip()
            session.add(ValidacionADF(
                adf_id=adf.id, etapa="Supervisor · devolución Jefatura",
                accion="Reenviado a Jefatura", usuario_nombre=nombre,
                usuario_email=email,
                comentario=comentario_supervisor or "Revisión realizada sin cambios al ADF.",
            ))
            session.commit(); session.refresh(adf)
            if adf.jefe_email:
                crear_notificacion(
                    adf.jefe_email, f"ADF #{adf.id} reenviado para aprobación",
                    f"{adf.area} · {adf.equipo} · Supervisor revisó la observación de Jefatura.",
                    adf_id=adf.id, tipo="pendiente",
                )
            return adf

        raise ValueError("Acción de devolución no reconocida.")


def historial_validaciones(adf_id: int) -> list[ValidacionADF]:
    with Session(engine) as session:
        consulta = select(ValidacionADF).where(ValidacionADF.adf_id == adf_id).order_by(ValidacionADF.fecha.asc())
        return list(session.scalars(consulta).all())


def eliminar_adf_completo(adf_id: int) -> dict:
    """Elimina un ADF y sus registros dependientes de validación/notificación.

    Los planes y respaldos están almacenados dentro del propio registro ADF,
    por lo que se eliminan junto con él. Devuelve un resumen de la operación.
    """
    with Session(engine) as session:
        adf = session.get(ADF, adf_id)
        if not adf:
            return {"ok": False, "mensaje": f"ADF #{adf_id} no existe."}

        validaciones = list(session.scalars(
            select(ValidacionADF).where(ValidacionADF.adf_id == adf_id)
        ).all())
        notificaciones = list(session.scalars(
            select(NotificacionInterna).where(NotificacionInterna.adf_id == adf_id)
        ).all())

        for item in validaciones:
            session.delete(item)
        for item in notificaciones:
            session.delete(item)

        resumen = {
            "id": adf.id,
            "equipo": adf.equipo or "",
            "centro": adf.centro or "",
            "area": adf.area or "",
            "estado": adf.estado or "",
            "validaciones_eliminadas": len(validaciones),
            "notificaciones_eliminadas": len(notificaciones),
        }
        session.delete(adf)
        session.commit()
        return {"ok": True, "resumen": resumen}
