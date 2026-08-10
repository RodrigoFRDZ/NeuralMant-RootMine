import base64
import json
from datetime import date, datetime, timedelta

import streamlit as st

from database.repositorio_adf import listar_adf, actualizar_plan_prevencion
from ia.cliente import revisar_evidencia_plan


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


def _agregar_archivos(destino: list[dict], archivos, tipo: str):
    if not archivos:
        return
    if not isinstance(archivos, list):
        archivos = [archivos]
    existentes = {(r.get("tipo"), r.get("nombre"), len(r.get("b64", ""))) for r in destino}
    for archivo in archivos:
        data = archivo.getvalue()
        item = {
            "tipo": tipo,
            "nombre": archivo.name,
            "mime": archivo.type or "image/png",
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


def _mostrar_revision(rev: dict):
    ver = rev.get("veredicto", "—")
    conf = rev.get("confianza", "—")
    if ver == "Ejecución respaldada":
        st.success(f"✅ {ver} · Confianza {conf}%")
    elif ver == "Evidencia inconsistente":
        st.error(f"❌ {ver} · Confianza {conf}%")
    else:
        st.warning(f"⚠️ {ver} · Confianza {conf}%")
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


def mostrar_planes_accion() -> None:
    st.markdown('<div class="hero"><div class="eyebrow">ROOTMINE · SEGUIMIENTO</div><h1>Planes de acción</h1><p>Respalda la ejecución con OT SAP y/o evidencia fotográfica. GearBot interpreta directamente los respaldos.</p></div>', unsafe_allow_html=True)
    registros = listar_adf()
    con_planes = [(adf, _json(adf.plan_prevencion, [])) for adf in registros if _json(adf.plan_prevencion, [])]
    if not con_planes:
        st.info("Aún no existen planes de acción registrados.")
        return

    st.info("💡 Para una OT SAP, sube una captura donde se vea el encabezado/texto breve, Status de usuario y Fecha fin extrema. Si el Status contiene **CTEC + NOTI**, RootMine lo usa como señal fuerte de ejecución, pero también valida que la OT sea coherente con el plan. Para trabajos físicos puedes subir fotos **Antes** y **Después**.")

    filtro_recibido = st.session_state.pop("filtro_planes_desde_indicadores", None)
    opciones_estado = ["Todos", "Atrasados", "Por vencer", "Pendientes de respaldo", "Ejecutados"]
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
            coincide = (
                estado_f == "Todos"
                or (estado_f == "Atrasados" and estado == "Atrasado")
                or (estado_f == "Por vencer" and estado == "Por vencer")
                or (estado_f == "Ejecutados" and estado == "Ejecutado")
                or (estado_f == "Pendientes de respaldo" and ad.get("estado_ejecucion") != "Ejecutado verificado")
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
                with st.expander(f"{i+1}. {titulo} · {estado}", expanded=False):
                    st.write(f"**Objetivo:** {accion.get('objetivo','—')}")
                    st.write(f"**Relación con la causa:** {accion.get('relacion_con_causa','—')}")
                    c1, c2, c3 = st.columns(3)
                    responsable = c1.text_input("Responsable", value=accion.get("responsable_sugerido", ""), key=f"pa_resp_{adf.id}_{i}")
                    tiene_fecha = c2.checkbox("Fecha compromiso definida", value=bool(_fecha(accion.get("fecha_compromiso"))), key=f"pa_tfecha_{adf.id}_{i}")
                    fecha_comp = c2.date_input("Fecha compromiso", value=_fecha(accion.get("fecha_compromiso")) or date.today(), disabled=not tiene_fecha, key=f"pa_fecha_{adf.id}_{i}")
                    c3.metric("Estado actual", estado_calculado(accion))
                    if accion.get("estado_ejecucion") == "Ejecutado verificado":
                        c3.success("Ejecución verificada por respaldo")
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
                    otros = st.file_uploader("📎 Otros respaldos visuales", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key=f"pa_otros_{adf.id}_{i}")
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

                    if respaldos:
                        st.markdown("**Respaldos guardados**")
                        cols = st.columns(min(3, len(respaldos)))
                        for j, r in enumerate(respaldos):
                            data = _decode_respaldo(r)
                            if data:
                                cols[j % len(cols)].image(data, caption=f"{r.get('tipo','')} · {r.get('nombre','')}", use_container_width=True)

                    if st.button("🤖 Analizar respaldos y verificar ejecución", key=f"pa_ia_{adf.id}_{i}", type="primary", use_container_width=True):
                        if not nuevos:
                            st.error("Adjunta al menos una captura de SAP o una evidencia fotográfica antes de analizar.")
                        else:
                            accion.update({
                                "responsable_sugerido": responsable.strip(),
                                "fecha_compromiso": fecha_comp.isoformat() if tiene_fecha else "",
                                "evidencia_de_implementacion": observacion.strip(),
                                "respaldos": nuevos,
                            })
                            contexto = f"""ADF #{adf.id}
Centro: {adf.centro or ''}
Equipo: {adf.equipo}
N° equipo: {getattr(adf,'numero_equipo','') or ''}
Área: {adf.area}
Plan de acción: {titulo}
Objetivo: {accion.get('objetivo','')}
Relación con la causa: {accion.get('relacion_con_causa','')}
Fecha compromiso: {accion.get('fecha_compromiso') or 'No definida'}
Contexto adicional del ejecutor: {observacion or 'Sin contexto adicional'}

Analiza directamente todos los respaldos adjuntos. Para capturas SAP verifica encabezado/texto breve, Status de usuario (CTEC + NOTI como señal fuerte), Fecha fin extrema y coherencia de la OT con el plan. Para fotos compara ANTES/DESPUÉS cuando existan."""
                            try:
                                with st.spinner("GearBot está leyendo la OT y/o comparando la evidencia fotográfica..."):
                                    rev = revisar_evidencia_plan(contexto, imagenes=_partes_ia(nuevos))
                                rev_dict = rev.model_dump()
                                accion["revision_ia"] = rev_dict
                                if rev.ejecucion_confirmada and rev.veredicto == "Ejecución respaldada":
                                    accion["estado_ejecucion"] = "Ejecutado verificado"
                                    accion["fecha_ejecucion"] = rev.fecha_ejecucion_estimada or date.today().isoformat()
                                else:
                                    accion["estado_ejecucion"] = "Pendiente"
                                # Compatibilidad: poblar campos históricos solo desde lo detectado por IA.
                                accion["noti_sap"] = rev.noti_detectada
                                accion["status_usuario_sap"] = rev.status_usuario_detectado
                                accion["mov_mercancias"] = rev.mov_mercancias_detectado
                                accion["fecha_fin_extrema_sap"] = rev.fecha_fin_extrema_detectada
                                accion["orden_trabajo_detectada"] = rev.orden_trabajo_detectada
                                accion["encabezado_orden_detectado"] = rev.encabezado_orden or rev.descripcion_orden
                                actualizar_plan_prevencion(adf.id, plan)
                                _mostrar_revision(rev_dict)
                                st.success("Revisión guardada en el historial del plan.")
                            except Exception as exc:
                                st.error(f"No fue posible revisar la evidencia: {exc}")
                    elif accion.get("revision_ia"):
                        st.markdown("#### Última revisión de GearBot")
                        _mostrar_revision(accion["revision_ia"])

                    if st.button("💾 Guardar responsable, fecha y respaldos", key=f"pa_save_{adf.id}_{i}", use_container_width=True):
                        accion.update({
                            "responsable_sugerido": responsable.strip(),
                            "fecha_compromiso": fecha_comp.isoformat() if tiene_fecha else "",
                            "evidencia_de_implementacion": observacion.strip(),
                            "respaldos": nuevos,
                        })
                        actualizar_plan_prevencion(adf.id, plan)
                        st.success("Seguimiento guardado.")
                        st.rerun()
