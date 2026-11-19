import base64
import json
import io
import pandas as pd
from datetime import date, datetime, timedelta

import streamlit as st

from database.repositorio_adf import listar_adf, actualizar_plan_prevencion
from ia.cliente import revisar_evidencia_plan, mensaje_amigable_ia


def _json(texto, defecto):
    try:
        return json.loads(texto or "")
    except Exception:
        return defecto


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def estado_calculado(accion: dict) -> str:
    if accion.get("eliminado_administrador"):
        return "Eliminado (archivado)"
    if accion.get("estado_administrativo") == "Cancelado":
        return "Cancelado"
    if accion.get("estado_respaldo") == "Requiere corrección":
        return "Requiere corrección"
    estado = (accion.get("estado_ejecucion") or "Pendiente").strip()
    if estado in {"Ejecutado", "Ejecutado verificado"}:
        return "Ejecutado"
    compromiso = _fecha(accion.get("fecha_compromiso"))
    if not compromiso:
        return "Sin fecha"
    hoy = date.today()
    if compromiso < hoy:
        return "Atrasado"
    if compromiso <= hoy + timedelta(days=7):
        return "Por vencer"
    return "Pendiente"


def _decode_respaldo(r):
    try:
        return base64.b64decode(r.get("b64") or "")
    except Exception:
        return None


def _respaldos_guardados(accion: dict) -> list[dict]:
    respaldos = accion.get("respaldos") or []
    if respaldos:
        return [r for r in respaldos if isinstance(r, dict)]
    # Compatibilidad con el formato anterior de un solo respaldo.
    if accion.get("respaldo_b64"):
        return [{
            "tipo": "Respaldo anterior",
            "nombre": accion.get("respaldo_nombre", "Respaldo"),
            "mime": accion.get("respaldo_mime", "image/png"),
            "b64": accion.get("respaldo_b64", ""),
        }]
    return []



MAX_RESPALDO_BYTES = 10 * 1024 * 1024


def _texto_plan(accion: dict) -> str:
    return " ".join([
        str(accion.get("accion") or ""),
        str(accion.get("objetivo") or ""),
        str(accion.get("relacion_con_causa") or ""),
        str(accion.get("evidencia_de_implementacion") or ""),
    ]).lower()


def _requisitos_especiales(accion: dict) -> list[tuple[str, str]]:
    """Devuelve (tipo_interno, descripción) de respaldos obligatorios por tipo de plan."""
    texto = _texto_plan(accion)
    req: list[tuple[str, str]] = []

    es_capacitacion = any(x in texto for x in [
        "capacita", "charla", "entrenamiento", "inducción", "induccion", "formación", "formacion"
    ])
    es_poev = "poev" in texto or "procedimiento operacional estándar visual" in texto or "procedimiento operacional estandar visual" in texto
    es_lup = "lup" in texto or "lección de un punto" in texto or "leccion de un punto" in texto

    if es_capacitacion:
        req.extend([
            ("Foto capacitación / charla", "Foto que evidencie la realización de la capacitación o charla."),
            ("Registro firmado capacitación", "Registro firmado de asistencia/capacitación. El tema visible en la parte superior debe coincidir con el plan."),
        ])
    if es_poev:
        req.extend([
            ("Documento POEV", "POEV implementado, con título/tema coherente con el plan."),
            ("Registro firmado difusión POEV", "Registro firmado que evidencie la difusión/capacitación del POEV."),
        ])
    if es_lup:
        req.extend([
            ("Documento LUP", "LUP implementada, con título/tema coherente con el plan."),
            ("Registro firmado difusión LUP", "Registro firmado que evidencie la difusión/capacitación de la LUP."),
        ])
    return req


def _faltantes_requisitos(accion: dict, respaldos: list[dict]) -> list[str]:
    presentes = {str(r.get("tipo") or "") for r in respaldos}
    return [descripcion for tipo, descripcion in _requisitos_especiales(accion) if tipo not in presentes]


def _agregar_archivos(destino: list[dict], archivos, tipo: str):
    if not archivos:
        return
    if not isinstance(archivos, list):
        archivos = [archivos]
    existentes = {(r.get("tipo"), r.get("nombre"), len(r.get("b64", ""))) for r in destino}
    for archivo in archivos:
        data = archivo.getvalue()
        if len(data) > MAX_RESPALDO_BYTES:
            st.error(f"{archivo.name}: el respaldo supera 10 MB. Reduce el tamaño antes de cargarlo.")
            continue
        item = {
            "tipo": tipo,
            "nombre": archivo.name,
            "mime": archivo.type or "application/octet-stream",
            "b64": base64.b64encode(data).decode("ascii"),
        }
        clave = (tipo, archivo.name, len(item["b64"]))
        if clave not in existentes:
            destino.append(item)
            existentes.add(clave)


def _partes_ia(respaldos: list[dict]):
    salida = []
    for r in respaldos:
        data = _decode_respaldo(r)
        if data:
            salida.append({"data": data, "mime": r.get("mime", "image/png"), "label": f"{r.get('tipo','Respaldo')}: {r.get('nombre','')}"})
    return salida


def _evaluar_respaldo(rev: dict) -> tuple[bool, bool, str]:
    """(aprobado, con_observacion, texto); confianza no es avance físico."""
    try:
        confianza = float(str(rev.get("confianza", "")).replace("%", "").replace(",", "."))
    except (ValueError, TypeError):
        return False, False, "No se obtuvo una confianza válida para aprobar el respaldo."
    confirmado = rev.get("ejecucion_confirmada") is True
    coherente = rev.get("veredicto") == "Ejecución respaldada"
    if not confirmado or not coherente:
        return False, False, "La evidencia no confirma la ejecución o presenta inconsistencias."
    if confianza <= 50:
        return False, False, f"Confianza {confianza:g}%: se requiere mejorar la evidencia."
    if confianza <= 80:
        partes = rev.get("observaciones") or rev.get("faltantes") or []
        if isinstance(partes, str): partes = [partes]
        detalle = "; ".join(str(x) for x in partes if x)
        return True, True, (f"Respaldo aprobado con observación ({confianza:g}%). "
                            + (detalle or "Evidencia aceptada con confianza moderada; revisar calidad del respaldo en seguimiento."))
    return True, False, f"Respaldo aprobado ({confianza:g}%)."


def _mostrar_revision(rev: dict):
    ver = rev.get("veredicto", "—")
    conf = rev.get("confianza", "—")
    if ver == "Ejecución respaldada":
        st.success(f"✅ {ver} · Confianza {conf}%")
    elif ver == "Evidencia inconsistente":
        st.error(f"❌ {ver} · Confianza {conf}%")
    else:
        st.warning(f"⚠️ {ver} · Confianza {conf}%")
    if rev.get("aprobado_con_observacion"):
        st.warning("Respaldo aprobado con observación: " + str(rev.get("observacion_aprobacion", "")))
    elif rev.get("aprobado"):
        st.success("Respaldo aprobado")
    st.write(rev.get("resumen", ""))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Lectura SAP / OT**")
        st.write(f"**OT detectada:** {rev.get('orden_trabajo_detectada') or 'No verificable'}")
        st.write(f"**Encabezado / texto breve:** {rev.get('encabezado_orden') or rev.get('descripcion_orden') or 'No verificable'}")
        st.write(f"**Status de usuario:** {rev.get('status_usuario_detectado') or 'No verificable'}")
        st.write(f"**Fecha fin extrema:** {rev.get('fecha_fin_extrema_detectada') or 'No verificable'}")
        st.write(f"**NOTI:** {rev.get('noti_detectada') or 'No verificable'}")
        if rev.get("mov_mercancias_detectado"):
            st.write(f"**MOV mercancías:** {rev.get('mov_mercancias_detectado')}")
        if rev.get("gasto_detectado"):
            st.write(f"**Gasto visible:** {rev.get('gasto_detectado')}")
        st.write("**CTEC + NOTI / señal de ejecución:** " + ("Sí" if rev.get("status_indica_ejecucion") else "No / no verificable"))
    with c2:
        st.markdown("**Coherencia con el plan**")
        st.write(f"**Resultado:** {rev.get('coherencia_plan','No verificable')}")
        if rev.get("comparacion_antes_despues"):
            st.write(f"**Antes vs. después:** {rev.get('comparacion_antes_despues')}")
        if rev.get("fecha_ejecucion_estimada"):
            st.write(f"**Fecha de ejecución estimada:** {rev.get('fecha_ejecucion_estimada')}")
        st.write("**Ejecución confirmada por IA:** " + ("Sí" if rev.get("ejecucion_confirmada") else "No"))
    if rev.get("observaciones"):
        st.markdown("**Observaciones**")
        for x in rev["observaciones"]:
            st.write(f"• {x}")
    if rev.get("faltantes"):
        st.markdown("**Información faltante / no verificable**")
        for x in rev["faltantes"]:
            st.write(f"• {x}")


def _es_creacion_plan_mantenimiento(accion: dict) -> bool:
    """Solo para compromisos de crear/programar un plan, no de ejecutarlo."""
    import unicodedata
    texto = unicodedata.normalize("NFKD", " ".join(str(accion.get(k) or "") for k in ("accion", "objetivo"))).encode("ascii", "ignore").decode().lower()
    verbos = ("crear", "elaborar", "generar", "disenar", "implementar", "programar")
    objetos = ("plan de mantenimiento", "pauta de mantenimiento", "hoja de ruta", "plan preventivo")
    return any(v in texto for v in verbos) and any(o in texto for o in objetos)


def _confirmacion_mantenimiento(accion: dict, adf_id: int, indice: int, plan: list):
    """Seguimiento posterior separado del cumplimiento del ADF."""
    if accion.get("estado_ejecucion") != "Ejecutado verificado" or not _es_creacion_plan_mantenimiento(accion):
        return
    st.markdown("#### 📅 Confirmación posterior del mantenimiento programado")
    st.caption("La acción ADF fue crear/programar el mantenimiento. Su ejecución futura se controla aparte y NO revierte la aprobación del plan de acción.")
    conf = accion.get("confirmacion_mantenimiento") or {}
    if not isinstance(conf, dict):
        conf = {}
    fecha = _fecha(conf.get("fecha_programada"))
    with st.form(f"pa_conf_mant_{adf_id}_{indice}"):
        fecha_programada = st.date_input("Fecha programada del mantenimiento", value=fecha or date(2026, 12, 12), key=f"pa_prog_{adf_id}_{indice}")
        ejecutado = st.checkbox("Confirmo que el mantenimiento se ejecutó", value=bool(conf.get("ejecutado")), key=f"pa_ok_{adf_id}_{indice}")
        ot = st.text_input("OT SAP ejecutada (si corresponde)", value=str(conf.get("ot_sap") or ""), key=f"pa_ot_conf_{adf_id}_{indice}")
        evidencia = st.text_area("Descripción o evidencia de ejecución", value=str(conf.get("evidencia") or ""), key=f"pa_ev_conf_{adf_id}_{indice}")
        if st.form_submit_button("Guardar confirmación / programación"):
            if ejecutado and not (ot.strip() or evidencia.strip()):
                st.error("Para confirmar la ejecución, ingresa una OT SAP o una descripción verificable.")
            elif ejecutado and fecha_programada > date.today():
                st.error("No se puede confirmar como ejecutado un mantenimiento con fecha futura.")
            else:
                accion["confirmacion_mantenimiento"] = {
                    "fecha_programada": fecha_programada.isoformat(),
                    "ejecutado": ejecutado,
                    "ot_sap": ot.strip(),
                    "evidencia": evidencia.strip(),
                    "fecha_confirmacion": date.today().isoformat() if ejecutado else None,
                }
                actualizar_plan_prevencion(adf_id, plan)
                st.success("Confirmación guardada. No se modificó el estado de aprobación del plan ADF.")
                st.rerun()
    if conf.get("ejecutado"):
        st.success("Mantenimiento posterior confirmado. Este registro no sustituye la verificación de efectividad.")
    else:
        st.info("Mantenimiento programado, pendiente de confirmar ejecución. El plan de creación permanece ejecutado.")


def mostrar_planes_accion() -> None:
    st.markdown('<div class="hero"><div class="eyebrow">ROOTMINE · SEGUIMIENTO</div><h1>Planes de acción</h1><p>Respalda la ejecución con OT SAP y/o evidencia fotográfica. GearBot interpreta directamente los respaldos.</p></div>', unsafe_allow_html=True)
    registros = listar_adf()
    con_planes = [(adf, _json(adf.plan_prevencion, [])) for adf in registros if _json(adf.plan_prevencion, [])]
    if not con_planes:
        st.info("Aún no existen planes de acción registrados.")
        return

    usuario = st.session_state.get("usuario_actual") or {}
    es_admin = usuario.get("es_admin") is True

    # Exportación general: no depende de filtros de pantalla.
    filas = []
    for adf, acciones in con_planes:
        for numero, accion in enumerate(acciones, 1):
            ac = accion if isinstance(accion, dict) else {"accion": str(accion)}
            if ac.get("estado_administrativo") == "Cancelado" or ac.get("eliminado_administrador"):
                continue
            estado_raw = str(ac.get("estado_ejecucion") or "Pendiente").strip().lower()
            if estado_raw in {"ejecutado", "ejecutado verificado", "completado", "cerrado", "anulado"}:
                continue
            fecha = _fecha(ac.get("fecha_compromiso"))
            filas.append({
                "ADF": adf.id, "Centro": adf.centro or "", "Área": adf.area or "",
                "Equipo": adf.equipo or "", "Estado ADF": adf.estado or "",
                "N° acción": numero, "Plan de acción": ac.get("accion") or "",
                "Objetivo": ac.get("objetivo") or "",
                "Responsable": ac.get("responsable_sugerido") or "Sin asignar",
                "Fecha compromiso": fecha.isoformat() if fecha else "Sin fecha",
                "Días de atraso": max(0, (date.today()-fecha).days) if fecha else "",
                "Estado del plan": estado_calculado(ac),
            })
    if filas:
        df = pd.DataFrame(filas)
        df = df.sort_values(["Días de atraso", "Fecha compromiso"], ascending=[False, True], key=lambda x: pd.to_numeric(x,errors="coerce").fillna(-1) if x.name=="Días de atraso" else x)
        resumen = df.groupby(["Área", "Responsable", "Estado del plan"], dropna=False).size().reset_index(name="Acciones pendientes")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Planes pendientes", index=False)
            resumen.to_excel(writer, sheet_name="Resumen responsables", index=False)
            for hoja in writer.sheets.values():
                hoja.freeze_panes = "A2"
                hoja.auto_filter.ref = hoja.dimensions
                for columna in hoja.columns:
                    letra = columna[0].column_letter
                    hoja.column_dimensions[letra].width = min(65,max(14,max(len(str(c.value or "")) for c in columna[:min(len(columna),300)])+3))
        st.download_button("📥 Descargar planes de acción pendientes (Excel)", data=buffer.getvalue(), file_name=f"RootMine_Planes_Pendientes_{date.today().isoformat()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="descarga_planes_pendientes")
        st.caption(f"{len(filas)} acciones abiertas en el archivo · incluye pendientes, por vencer y atrasadas de todos los ADF.")
    else:
        st.success("No hay planes de acción pendientes para exportar.")

    st.info("💡 Para una OT SAP, sube una captura donde se vea el encabezado/texto breve, Status de usuario y Fecha fin extrema. Si el Status contiene **CTEC + NOTI**, RootMine lo usa como señal fuerte de ejecución, pero también valida que la OT sea coherente con el plan. Para trabajos físicos puedes subir fotos **Antes** y **Después**.")

    filtro_recibido = st.session_state.pop("filtro_planes_desde_indicadores", None)
    opciones_estado = ["Todos", "Atrasados", "Por vencer", "Pendientes de respaldo", "Requiere corrección", "Ejecutados"] + (["Cancelados", "Eliminados (archivo)"] if es_admin else [])
    estado_inicial = filtro_recibido if filtro_recibido in opciones_estado else "Todos"
    f1, f2 = st.columns([1, 1])
    area_f = f1.selectbox("Área", ["Todas"] + sorted({a.area for a, _ in con_planes if a.area}))
    estado_f = f2.selectbox("Filtro de gestión", opciones_estado, index=opciones_estado.index(estado_inicial))
    if estado_f != "Todos":
        st.info(f"🔎 Mostrando directamente: **{estado_f}**. Este filtro puede venir desde Indicadores.")

    encontrados = 0
    for adf, plan in con_planes:
        if area_f != "Todas" and adf.area != area_f:
            continue
        plan_filtrado = []
        for idx, ac in enumerate(plan):
            ad = ac if isinstance(ac, dict) else {"accion": str(ac)}
            estado = estado_calculado(ad)
            inactivo = estado in {"Cancelado", "Eliminado (archivado)"}
            coincide = (
                (estado_f == "Cancelados" and es_admin and estado == "Cancelado")
                or (estado_f == "Eliminados (archivo)" and es_admin and estado == "Eliminado (archivado)")
                or (not inactivo and (
                estado_f == "Todos"
                or (estado_f == "Atrasados" and estado == "Atrasado")
                or (estado_f == "Por vencer" and estado == "Por vencer")
                or (estado_f == "Ejecutados" and estado == "Ejecutado")
                or (estado_f == "Requiere corrección" and estado == "Requiere corrección")
                or (estado_f == "Pendientes de respaldo" and ad.get("estado_ejecucion") != "Ejecutado verificado")
                ))
            )
            if coincide:
                plan_filtrado.append((idx, ad))
        if not plan_filtrado:
            continue
        encontrados += len(plan_filtrado)
        with st.container(border=True):
            st.subheader(f"ADF #{adf.id} · {adf.equipo}")
            st.caption(f"{adf.centro or '—'} · {adf.area} · Estado ADF: {adf.estado}")
            for i, accion in plan_filtrado:
                if not isinstance(plan[i], dict):
                    plan[i] = accion
                titulo = accion.get("accion") or f"Acción {i+1}"
                estado = estado_calculado(accion)
                rev = accion.get("revision_ia") or {}
                confianza_texto = ""
                if isinstance(rev, dict) and rev.get("confianza") is not None:
                    confianza_texto = f" · Respaldo {rev['confianza']}%"
                with st.expander(f"{i+1}. {titulo} · {estado}{confianza_texto}", expanded=False):
                    if es_admin:
                        with st.expander("🛡️ Administración del plan (solo administrador)"):
                            if accion.get("estado_administrativo") == "Cancelado" or accion.get("eliminado_administrador"):
                                st.warning(f"Estado: {estado_calculado(accion)}")
                                for evento in accion.get("auditoria_administrativa", []):
                                    st.caption(f"{evento.get('fecha','')} · {evento.get('accion','')} · {evento.get('motivo','')}")
                            else:
                                operacion = st.radio(
                                    "Acción administrativa",
                                    ["Cancelar con justificación", "Eliminar (archivar y ocultar)"],
                                    horizontal=True, key=f"adm_tipo_{adf.id}_{i}",
                                )
                                motivos = (["Imposibilidad técnica", "Restricción operacional",
                                            "Falta de factibilidad económica", "Acción reemplazada",
                                            "Otro"] if operacion.startswith("Cancelar") else
                                           ["Plan duplicado", "Creado por error", "Otro"])
                                motivo = st.selectbox("Motivo obligatorio", motivos, key=f"adm_motivo_{adf.id}_{i}")
                                justificacion = st.text_area(
                                    "Justificación obligatoria", key=f"adm_just_{adf.id}_{i}",
                                    placeholder="Indica por qué no se realizará o por qué corresponde archivarlo.",
                                )
                                confirmacion = st.checkbox(
                                    "Confirmo que soy administrador y que esta acción quedará registrada",
                                    key=f"adm_confirm_{adf.id}_{i}",
                                )
                                if st.button("Confirmar acción administrativa", type="secondary",
                                             disabled=not (confirmacion and justificacion.strip()),
                                             key=f"adm_apply_{adf.id}_{i}"):
                                    # Volver a comprobar el rol en el momento de persistir.
                                    actual = st.session_state.get("usuario_actual") or {}
                                    if actual.get("es_admin") is not True:
                                        st.error("Operación restringida al administrador.")
                                    else:
                                        marca = datetime.now().astimezone().isoformat()
                                        es_cancelacion = operacion.startswith("Cancelar")
                                        accion["estado_administrativo"] = "Cancelado" if es_cancelacion else "Eliminado"
                                        accion["eliminado_administrador"] = not es_cancelacion
                                        accion.setdefault("auditoria_administrativa", []).append({
                                            "fecha": marca, "accion": "Cancelación" if es_cancelacion else "Eliminación lógica",
                                            "motivo": motivo, "justificacion": justificacion.strip(),
                                            "usuario": str(actual.get("correo") or actual.get("email") or actual.get("nombre") or "Administrador"),
                                        })
                                        actualizar_plan_prevencion(adf.id, plan)
                                        st.success("Plan actualizado con registro de auditoría.")
                                        st.rerun()
                    if accion.get("estado_administrativo") == "Cancelado" or accion.get("eliminado_administrador"):
                        st.info("Este plan se conserva para trazabilidad. No se puede editar su ejecución.")
                        continue
                    st.write(f"**Objetivo:** {accion.get('objetivo','—')}")
                    st.write(f"**Relación con la causa:** {accion.get('relacion_con_causa','—')}")
                    c1, c2, c3 = st.columns(3)
                    responsable = c1.text_input("Responsable *", value=accion.get("responsable_sugerido", ""), key=f"pa_resp_{adf.id}_{i}", help="Campo obligatorio.")
                    fecha_comp = c2.date_input("Fecha de compromiso *", value=_fecha(accion.get("fecha_compromiso")) or date.today(), format="DD/MM/YYYY", key=f"pa_fecha_{adf.id}_{i}", help="Campo obligatorio. Selecciona la fecha en el calendario.")
                    c2.caption(f"📅 {fecha_comp.strftime('%d/%m/%Y')}")
                    c3.metric("Estado actual", estado_calculado(accion))
                    if accion.get("estado_ejecucion") == "Ejecutado verificado":
                        c3.success("Ejecución verificada por respaldo")
                    elif accion.get("estado_respaldo") == "Requiere corrección":
                        c3.warning("Respaldo rechazado: necesita corrección y nueva revisión")
                        st.warning("**Pendiente de corrección:** " + str(accion.get("solicitud_correccion") or "Complementar evidencia de ejecución."))
                    else:
                        c3.caption("El estado Ejecutado se obtiene tras revisar evidencia con IA.")

                    st.markdown("#### Evidencia / respaldo de ejecución")
                    st.caption("No necesitas transcribir manualmente NOTI, status o fechas: GearBot los leerá desde la captura cuando sean visibles.")
                    sap_files = st.file_uploader(
                        "📄 Captura(s) de Orden de Trabajo SAP",
                        type=["png", "jpg", "jpeg"], accept_multiple_files=True,
                        key=f"pa_sap_{adf.id}_{i}",
                        help="Idealmente incluye encabezado/texto breve, Status de usuario y Fecha fin extrema.",
                    )
                    p1, p2 = st.columns(2)
                    foto_antes = p1.file_uploader("📷 Foto ANTES", type=["png", "jpg", "jpeg"], key=f"pa_antes_{adf.id}_{i}")
                    foto_despues = p2.file_uploader("📷 Foto DESPUÉS", type=["png", "jpg", "jpeg"], key=f"pa_despues_{adf.id}_{i}")
                    otros = st.file_uploader("📎 Otros respaldos visuales", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True, key=f"pa_otros_{adf.id}_{i}")

                    requisitos = _requisitos_especiales(accion)
                    archivos_especiales = []
                    if requisitos:
                        st.markdown("##### 📋 Respaldos obligatorios para este tipo de plan")
                        st.info(
                            "RootMine detectó que esta acción corresponde a capacitación/charla, POEV y/o LUP. "
                            "La ejecución no podrá ser verificada por IA mientras falte un respaldo obligatorio."
                        )
                        for tipo_req, descripcion_req in requisitos:
                            permite_foto = tipo_req == "Foto capacitación / charla"
                            archivo_req = st.file_uploader(
                                f"{tipo_req} *",
                                type=["png", "jpg", "jpeg"] if permite_foto else ["png", "jpg", "jpeg", "pdf"],
                                key=f"pa_req_{adf.id}_{i}_{tipo_req}",
                                help=descripcion_req,
                            )
                            st.caption(descripcion_req)
                            archivos_especiales.append((tipo_req, archivo_req))

                    observacion = st.text_area(
                        "Contexto adicional (opcional)",
                        value=accion.get("evidencia_de_implementacion", ""),
                        placeholder="Ej.: OT ejecutada durante ventana de mantención; se reemplazó guía de manguera del lado descarga.",
                        key=f"pa_evtxt_{adf.id}_{i}",
                    )

                    respaldos = _respaldos_guardados(accion)
                    nuevos = list(respaldos)
                    _agregar_archivos(nuevos, sap_files, "Orden de Trabajo SAP")
                    _agregar_archivos(nuevos, foto_antes, "Foto ANTES")
                    _agregar_archivos(nuevos, foto_despues, "Foto DESPUÉS")
                    _agregar_archivos(nuevos, otros, "Otro respaldo")
                    for tipo_req, archivo_req in archivos_especiales:
                        _agregar_archivos(nuevos, archivo_req, tipo_req)

                    faltantes_especiales = _faltantes_requisitos(accion, nuevos)
                    if faltantes_especiales:
                        st.warning("Faltan respaldos obligatorios: " + " | ".join(faltantes_especiales))

                    if respaldos:
                        st.markdown("**Respaldos guardados**")
                        cols = st.columns(min(3, len(respaldos)))
                        for j, r in enumerate(respaldos):
                            data = _decode_respaldo(r)
                            if data:
                                mime = str(r.get("mime") or "")
                                if mime.startswith("image/"):
                                    cols[j % len(cols)].image(data, caption=f"{r.get('tipo','')} · {r.get('nombre','')}", use_container_width=True)
                                else:
                                    cols[j % len(cols)].write(f"📄 **{r.get('tipo','Respaldo')}**")
                                    cols[j % len(cols)].caption(r.get("nombre", "Documento"))
                                    cols[j % len(cols)].download_button(
                                        "Ver / descargar",
                                        data=data,
                                        file_name=r.get("nombre", "respaldo.pdf"),
                                        mime=mime or "application/octet-stream",
                                        key=f"pa_saved_{adf.id}_{i}_{j}",
                                    )

                    if st.button("🤖 Analizar respaldos y verificar ejecución", key=f"pa_ia_{adf.id}_{i}", type="primary", use_container_width=True):
                        if not nuevos:
                            st.error("Adjunta al menos un respaldo antes de analizar.")
                        elif faltantes_especiales:
                            st.error(
                                "No es posible verificar todavía esta acción. Faltan respaldos obligatorios: "
                                + " | ".join(faltantes_especiales)
                            )
                        else:
                            accion.update({
                                "responsable_sugerido": responsable.strip(),
                                "fecha_compromiso": fecha_comp.isoformat(),
                                "evidencia_de_implementacion": observacion.strip(),
                                "respaldos": nuevos,
                            })
                            contexto = f"""ADF #{adf.id}
Centro: {adf.centro or ''}
Equipo: {adf.equipo}
Equipo: {adf.equipo or 'Sin descripción'} · N° identificador: {getattr(adf,'numero_equipo','') or '—'}
Área: {adf.area}
Plan de acción: {titulo}
Objetivo: {accion.get('objetivo','')}
Relación con la causa: {accion.get('relacion_con_causa','')}
Fecha compromiso: {accion.get('fecha_compromiso') or 'No definida'}
Contexto adicional del ejecutor: {observacion or 'Sin contexto adicional'}

Evalúa SOLO el entregable comprometido en el plan de acción. Si la acción es CREAR o PROGRAMAR un plan de mantenimiento, valida su creación/programación, NO exijas que se haya ejecutado la primera OT futura. La ejecución posterior se registra separadamente. No supongas que una fecha futura demuestra ejecución.
Analiza directamente todos los respaldos adjuntos.
Para capturas SAP verifica encabezado/texto breve, Status de usuario (CTEC + NOTI como señal fuerte), Fecha fin extrema y coherencia de la OT con el plan.
Para fotos compara ANTES/DESPUÉS cuando existan.
Si el plan corresponde a capacitación/charla, valida que exista evidencia visual de la actividad y un registro firmado; en el registro, el tema/título visible en la parte superior debe ser coherente con el contenido del plan.
Si corresponde a POEV o LUP, valida que el documento presentado corresponda realmente al POEV/LUP comprometido y que el registro firmado de difusión/capacitación sea coherente con ese tema."""
                            try:
                                with st.spinner("GearBot está leyendo la OT y/o comparando la evidencia fotográfica..."):
                                    rev = revisar_evidencia_plan(contexto, imagenes=_partes_ia(nuevos))
                                rev_dict = rev.model_dump()
                                aprobado, condicionado, observacion_aprobacion = _evaluar_respaldo(rev_dict)
                                rev_dict["aprobado"] = aprobado
                                rev_dict["aprobado_con_observacion"] = condicionado
                                rev_dict["observacion_aprobacion"] = observacion_aprobacion
                                anterior = accion.get("revision_ia")
                                if isinstance(anterior, dict):
                                    historial = accion.get("historial_revision_ia")
                                    if not isinstance(historial, list):
                                        historial = []
                                    historial.append(anterior)
                                    accion["historial_revision_ia"] = historial[-20:]
                                accion["revision_ia"] = rev_dict
                                if aprobado:
                                    accion["estado_respaldo"] = ("Aprobado con observación" if condicionado else "Aprobado")
                                    accion.pop("solicitud_correccion", None)
                                    accion["estado_ejecucion"] = "Ejecutado verificado"
                                    accion["fecha_ejecucion"] = rev.fecha_ejecucion_estimada or date.today().isoformat()
                                else:
                                    accion["estado_ejecucion"] = "Pendiente"
                                    accion["estado_respaldo"] = "Requiere corrección"
                                    accion.pop("fecha_ejecucion", None)
                                    detalle = str(rev_dict.get("observacion_aprobacion") or "").strip()
                                    faltantes = rev_dict.get("faltantes") or rev_dict.get("observaciones") or []
                                    if isinstance(faltantes, str):
                                        faltantes = [faltantes]
                                    if isinstance(faltantes, list) and faltantes:
                                        detalle += " | " + "; ".join(str(x) for x in faltantes if x)
                                    accion["solicitud_correccion"] = detalle or "Adjuntar evidencia adicional que permita verificar la ejecución."
                                # Compatibilidad: poblar campos históricos solo desde lo detectado por IA.
                                accion["noti_sap"] = rev.noti_detectada
                                accion["status_usuario_sap"] = rev.status_usuario_detectado
                                accion["mov_mercancias"] = rev.mov_mercancias_detectado
                                accion["fecha_fin_extrema_sap"] = rev.fecha_fin_extrema_detectada
                                accion["orden_trabajo_detectada"] = rev.orden_trabajo_detectada
                                accion["encabezado_orden_detectado"] = rev.encabezado_orden or rev.descripcion_orden
                                actualizar_plan_prevencion(adf.id, plan)
                                _mostrar_revision(rev_dict)
                                if aprobado:
                                    st.success("Respaldo aprobado. Plan verificado y disponible para seguimiento de efectividad.")
                                else:
                                    st.error("Respaldo no aprobado. El plan permanece pendiente y se muestra en Requiere corrección.")
                                    st.warning(accion["solicitud_correccion"])
                            except Exception as exc:
                                amigable = mensaje_amigable_ia(exc)
                                if amigable:
                                    st.warning(amigable)
                                    st.caption("El respaldo queda disponible y podrás pedir la revisión de GearBot más tarde.")
                                else:
                                    st.error(f"No fue posible revisar la evidencia: {exc}")
                    elif accion.get("revision_ia"):
                        st.markdown("#### Última revisión de GearBot")
                        _mostrar_revision(accion["revision_ia"])

                    if st.button("💾 Guardar responsable, fecha y respaldos", key=f"pa_save_{adf.id}_{i}", use_container_width=True):
                        accion.update({
                            "responsable_sugerido": responsable.strip(),
                            "fecha_compromiso": fecha_comp.isoformat(),
                            "evidencia_de_implementacion": observacion.strip(),
                            "respaldos": nuevos,
                        })
                        actualizar_plan_prevencion(adf.id, plan)
                        if accion.get("estado_respaldo") == "Requiere corrección":
                            st.warning("Evidencia complementaria guardada sin aprobar el plan. Pulsa Analizar respaldos para solicitar una nueva evaluación.")
                        else:
                            st.success("Seguimiento guardado.")
                        st.rerun()
                    _confirmacion_mantenimiento(accion, adf.id, i, plan)
