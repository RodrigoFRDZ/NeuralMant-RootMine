"""Gestión de materiales: stock de seguridad, MRP, criticidad y seguimiento."""
import json
import math
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import streamlit as st
from database.usuarios import cargar_usuarios, cargar_centros
from database.materiales import (PERFILES, ESTADOS, candidatos, criticidad, impacto,
                                guardar, listar, decidir, puede_actuar)
from ia.cliente import _generar, mensaje_amigable_ia
from pydantic import BaseModel, Field


class JustificacionMaterial(BaseModel):
    justificacion: str
    antecedentes_faltantes: list[str] = Field(default_factory=list)


def _guia(prefijo, datos=None):
    d = datos or {}
    st.caption("Guía basada en SV-DC-MAN-019 · revisión 27-05-2025. La clasificación requiere validación técnica.")
    m = st.checkbox("Es motor o bomba reparable con stock rotativo", value=bool(d.get("m_rotativo")), key=prefijo+"m")
    if m:
        st.info("Categoría M: control de reparación y retorno. No se incorpora al MRP.")
        return "M", {"m_rotativo": True}
    opciones = {
        "smac": ["Riesgo para seguridad, medio ambiente o calidad", "Incumple política interna de Agrosuper", "Sin riesgo"],
        "co": ["Afecta directamente la operación", "Afecta menormente el proceso", "No afecta el proceso"],
        "te": ["Más de 90 días", "Entre 21 y 90 días", "Menos de 21 días"],
        "ma": ["Sin sustituto; solo fabricante", "Sustituto validado por fabricante", "Sustituto validado por Agrosuper"],
    }
    etiquetas = {"smac": "Seguridad, medio ambiente y calidad", "co": "Continuidad operacional",
                 "te": "Tiempo de entrega", "ma": "Sustitución del repuesto"}
    respuestas = {"m_rotativo": False}
    cols = st.columns(2)
    for i, (k, opciones_k) in enumerate(opciones.items()):
        with cols[i % 2]:
            respuestas[k] = st.selectbox(etiquetas[k], [1, 2, 3],
                index=int(d.get(k, 3))-1, format_func=lambda v, opts=opciones_k: opts[v-1], key=prefijo+k)
    respuestas["estrategico"] = st.checkbox("Repuesto estratégico de baja rotación con graves consecuencias si falta", value=bool(d.get("estrategico")), key=prefijo+"z")
    c = criticidad(**respuestas)
    st.success(f"Clasificación sugerida por el árbol: {c}")
    return c, respuestas


def _responsable(usuarios, etapa, centro, area, previo, key):
    opciones = candidatos(usuarios, etapa, centro, area)
    correos = [""] + [u["correo"] for u in opciones]
    nombres = {u["correo"]: f"{u['nombre']} · {u['correo']}" for u in opciones}
    recomendado = previo if previo in correos else (correos[1] if len(correos) == 2 else "")
    if etapa == "analista" and "rfernandezc@agrosuper.com" in correos and not previo:
        recomendado = "rfernandezc@agrosuper.com"
    return st.selectbox({"jefe": "Jefe de área", "analista": "Analizador de materiales", "subgerente": "Subgerente de Mantenimiento"}[etapa],
        correos, index=correos.index(recomendado), format_func=lambda c: nombres.get(c, "Seleccionar responsable"), key=key)


def _formulario(tipo, u, registros):
    pref = "mat_ss_" if tipo == "Stock de seguridad" else "mat_mrp_"
    borradores = [r for r in registros if r["tipo"] == tipo and r["solicitante_email"] == u["correo"] and r["estado"] in ("Borrador", "Devuelta")]
    ids = [0] + [r["id"] for r in borradores]
    elegido = st.selectbox("Continuar solicitud o crear nueva", ids, format_func=lambda n: "Nueva solicitud" if not n else f"#{n} · {next(r for r in borradores if r['id']==n)['material']}", key=pref+"draft")
    r = next((r for r in borradores if r["id"] == elegido), None)
    d = r["datos"] if r else {}
    pref += str(elegido)+"_"
    if r and r["estado"] == "Devuelta":
        st.warning("Solicitud devuelta. Corrige los antecedentes y vuelve a enviarla al jefe de área.")
        st.write(r["historial"][-1]["comentario"])
    c1, c2, c3 = st.columns(3)
    with c1:
        material = st.text_input("Código material *", value=d.get("material", ""), key=pref+"codigo").strip()
        unidad = st.text_input("Unidad de medida *", value=d.get("unidad", ""), placeholder="UN, KG, M…", key=pref+"um").strip().upper()
    with c2:
        descripcion = st.text_input("Descripción material *", value=d.get("descripcion", ""), key=pref+"desc").strip()
        centro_op = list(cargar_centros()) or [u.get("centro", "1802")]
        if not u.get("es_admin"):
            centro_op = [u.get("centro", "")]
        centro_def = d.get("centro", u.get("centro", ""))
        centro = st.selectbox("Centro *", centro_op, index=centro_op.index(centro_def) if centro_def in centro_op else 0, key=pref+"centro")
    with c3:
        area = st.text_input("Área *", value=d.get("area", u.get("area", "")), key=pref+"area").strip()
        almacen = st.text_input("Almacén", value=d.get("almacen", ""), key=pref+"almacen").strip()
    equipo = st.text_input("Equipos donde se utiliza", value=d.get("equipos", ""), key=pref+"equipos")
    perfil = mercado = ""
    lead_time = 0
    if tipo == "MRP":
        a,b,c = st.columns(3)
        with a:
            perfil = st.selectbox("Perfil MRP *", PERFILES, index=PERFILES.index(d.get("perfil")) if d.get("perfil") in PERFILES else 0, key=pref+"perfil")
        with b:
            mercado = st.selectbox("Mercado *", ["Nacional", "Importado"], index=int(d.get("mercado")=="Importado"), key=pref+"mercado")
        with c:
            lead_time = st.number_input("Lead time en días *", min_value=1, value=max(1, int(d.get("lead_time", 1))), step=1, key=pref+"lt")
    cantidad = st.number_input("Stock de seguridad solicitado", min_value=0.0, value=float(d.get("cantidad", 0)), key=pref+"cant") if tipo == "Stock de seguridad" or perfil == "Stock de seguridad" else 0.0
    with st.expander("Ayuda para asignar criticidad", expanded=False):
        sugerida, respuestas = _guia(pref+"guia_", d.get("guia", {}))
    clases = ["A", "B", "C", "Z"] if tipo == "MRP" else ["A", "B", "C", "Z", "M"]
    seleccion = d.get("criticidad", sugerida)
    clase = st.selectbox("Criticidad propuesta *", clases, index=clases.index(seleccion) if seleccion in clases else 0, key=pref+"crit")
    razon_crit = st.text_input("Fundamento de la criticidad", value=d.get("razon_criticidad", ""), key=pref+"razon")
    if respuestas["m_rotativo"]:
        if tipo == "MRP": st.error("Material M: no se permite enviar ni guardar una incorporación al MRP.")
        else: clase = "M"
    just_key = pref+"justificacion"
    st.session_state.setdefault(just_key, d.get("justificacion", ""))
    if st.button("Complementar justificación con IA", key=pref+"ia"):
        original = st.session_state[just_key]
        if not original.strip():
            st.warning("Escribe primero por qué necesitas el material.")
        else:
            try:
                with st.spinner("GearBot está revisando los antecedentes…"):
                    res = _generar("Redacta una justificación técnica para una solicitud de materiales. Usa únicamente los hechos entregados. No inventes fallas, costos, cantidades ni plazos. Identifica antecedentes faltantes como preguntas. No apruebes la solicitud.",
                        json.dumps({"material": material, "descripcion": descripcion, "equipos": equipo, "tipo": tipo, "criticidad": clase, "relato": original}, ensure_ascii=False), JustificacionMaterial)
                st.session_state[pref+"propuesta_ia"] = res.model_dump()
            except Exception as exc:
                st.warning(mensaje_amigable_ia(exc) or "No fue posible consultar GearBot. Puedes continuar manualmente.")
    propuesta = st.session_state.get(pref+"propuesta_ia")
    if propuesta:
        st.write("**Propuesta de GearBot**")
        st.write(propuesta["justificacion"])
        for falta in propuesta["antecedentes_faltantes"]:
            st.write("• "+falta)
        if st.button("Usar propuesta y revisar", key=pref+"usar_ia"):
            st.session_state[just_key] = propuesta["justificacion"]
    justificacion = st.text_area("Justificación de la necesidad *", height=150, key=just_key)
    respaldo = st.text_area("Referencias de respaldo", value=d.get("respaldo", ""), placeholder="ADF, OT, aviso SAP o enlace a evidencia", key=pref+"respaldo")
    st.write("**Responsables del flujo**")
    usuarios = cargar_usuarios()
    resp = {}
    for etapa in ("jefe", "analista", "subgerente"):
        resp[etapa] = _responsable(usuarios, etapa, centro, area, r.get(etapa+"_email", "") if r else "", pref+etapa)
    datos = dict(material=material, descripcion=descripcion, unidad=unidad, centro=centro, area=area,
        almacen=almacen, equipos=equipo, perfil=perfil, mercado=mercado, lead_time=int(lead_time),
        cantidad=cantidad, criticidad=clase, razon_criticidad=razon_crit, guia=respuestas,
        m_rotativo=respuestas["m_rotativo"], justificacion=justificacion, respaldo=respaldo)
    a,b = st.columns(2)
    draft = a.button("Guardar borrador", key=pref+"guardar", use_container_width=True)
    enviar = b.button("Enviar al jefe de área", key=pref+"enviar", type="primary", use_container_width=True)
    if draft or enviar:
        try:
            if tipo == "MRP" and perfil == "Stock de seguridad" and cantidad <= 0 and enviar:
                raise ValueError("Indica una cantidad para el perfil de stock de seguridad.")
            n = guardar(u["correo"], tipo, datos, resp, enviar=enviar, solicitud_id=elegido or None, version=r["version"] if r else None)
            st.session_state["mat_flash"] = f"Solicitud #{n} {'enviada' if enviar else 'guardada como borrador'}."
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _evaluacion(r):
    d = r["datos"]; anterior = d.get("analisis", {})
    a = {}
    pref = f"eval_{r['id']}_{r['version']}_"
    clases = ["A", "B", "C", "Z"] if r["tipo"] == "MRP" else ["A", "B", "C", "Z", "M"]
    clase = anterior.get("criticidad", d["criticidad"])
    a["criticidad"] = st.selectbox("Criticidad validada", clases, index=clases.index(clase) if clase in clases else 0, key=pref+"crit")
    if r["tipo"] == "MRP":
        # El perfil solicitado se conserva en la aprobación. Cambios se devuelven al solicitante.
        st.info(f"Perfil solicitado: {d['perfil']} · {d['mercado']} · Lead time: {d['lead_time']} días")
    if r["tipo"] == "Stock de seguridad" or d.get("perfil") == "Stock de seguridad":
        campos = [("ss_actual", "Stock de seguridad actual"), ("ss_propuesto", "Stock de seguridad propuesto"),
            ("stock", "Stock físico disponible"), ("reservas", "Reservas pendientes"), ("oc", "OC pendientes de entrega"),
            ("precio", "Precio unitario"), ("valor_bodega", "Valor total actual de la bodega"),
            ("consumo_mensual", "Consumo promedio mensual"), ("desviacion", "Desviación de demanda por mes"),
            ("lead_time_dias", "Lead time en días")]
        cols = st.columns(2)
        for i,(k,etiqueta) in enumerate(campos):
            with cols[i%2]:
                inicial = anterior.get(k, d.get("cantidad", 0) if k=="ss_propuesto" else d.get("lead_time", 0) if k=="lead_time_dias" else 0)
                a[k] = st.number_input(etiqueta, min_value=0.0, value=float(inicial), key=pref+k)
        a["moneda"] = st.selectbox("Moneda de todos los valores", ["USD", "CLP"], index=int(anterior.get("moneda")=="CLP"), key=pref+"moneda")
        a["fecha_datos"] = st.date_input("Fecha de los datos de bodega", value=date.fromisoformat(anterior["fecha_datos"]) if anterior.get("fecha_datos") else date.today(), key=pref+"fecha").isoformat()
        nivel = st.selectbox("Nivel de servicio para cálculo estadístico", [90, 95, 99], key=pref+"servicio")
        a["nivel_servicio"] = nivel
        sugerencia = math.ceil({90:1.28,95:1.64,99:2.33}[nivel]*a["desviacion"]*math.sqrt(a["lead_time_dias"]/30))
        a["ss_estadistico"] = sugerencia
        st.caption(f"SS estadístico orientativo: {sugerencia} {d['unidad']}. Demanda mensual y lead time convertido a meses de 30 días. Validar unidad y redondeo antes de aprobar.")
        st.caption("Para repuestos estratégicos de baja rotación, el consumo histórico por sí solo no define la cobertura necesaria. Justifica la cantidad técnicamente.")
        imp = impacto(a)
        x,y,z = st.columns(3)
        x.metric("Aumento SS valorizado", f"{imp['incremento_ss']:,.2f} {a['moneda']}")
        y.metric("Reposición adicional estimada", f"{imp['reposicion']:,.2f} {a['moneda']}")
        z.metric("Aumento SS / bodega", f"{imp['porcentaje']:.2f}%" if imp['porcentaje'] is not None else "Sin base")
        st.caption(f"Bodega proyectada con reposición: {imp['bodega_proyectada']:,.2f} {a['moneda']}. Se consideran stock, reservas y OC pendientes; la carga del parámetro en SAP no representa una entrada física.")
    a["fundamento"] = st.text_area("Fundamento del análisis *", value=anterior.get("fundamento", ""), key=pref+"fund")
    return a


def _detalle(r, u):
    d = r["datos"]
    st.write(f"**#{r['id']} · {r['tipo']} · {r['estado']}**")
    st.write(f"Material {r['material']} · {d.get('descripcion', '')} · {d.get('unidad', '')}")
    st.caption(f"{r['solicitante_nombre']} · Centro {r['centro']} · {r['area']}")
    st.write(d.get("justificacion", ""))
    with st.expander("Antecedentes y evaluación aprobada"):
        st.json(d)
        st.write(f"Jefe: {r['jefe_email']} · Analizador: {r['analista_email']} · Subgerente: {r['subgerente_email']}")
    if r["fecha_envio"]:
        fin = r["fecha_carga"] or datetime.utcnow()
        horas = (fin-r["fecha_envio"]).total_seconds()/3600
        st.metric("Tiempo desde envío hasta SAP" if r["fecha_carga"] else "Tiempo transcurrido desde envío", f"{horas:.1f} horas · {horas/24:.1f} días")
    with st.expander("Historial del flujo"):
        st.caption("Fechas de historial en UTC. La confirmación de carga usa hora de Chile.")
        for h in r["historial"]:
            st.write(f"{h['fecha'][:19]} · {h['usuario']} · {h['accion']} · {h['estado']}")
            if h.get("comentario"): st.write(h["comentario"])
        if r["fecha_envio"] and r["historial"]:
            st.write("**Tiempo entre acciones**")
            hist = r["historial"]
            st.dataframe([{"Desde": h['accion'], "Hasta": nxt['accion'],
                "Horas": round((datetime.fromisoformat(nxt['fecha'])-datetime.fromisoformat(h['fecha'])).total_seconds()/3600, 1)}
                for h,nxt in zip(hist, hist[1:])], hide_index=True, use_container_width=True)
    st.download_button("Descargar expediente JSON", json.dumps(r, default=str, ensure_ascii=False, indent=2),
        file_name=f"Solicitud_materiales_{r['id']}.json", mime="application/json", key=f"desc_{r['id']}")
    if not puede_actuar(r,u): return
    st.write("**Acciones de la etapa actual**")
    a = _evaluacion(r) if r["estado"] == "Pendiente análisis" else None
    pref = f"accion_{r['id']}_{r['version']}_"
    c = None
    if r["estado"] == "Pendiente carga SAP":
        st.info("Confirma que la configuración cargada corresponde exactamente a la aprobada. Si necesitas modificarla, devuelve la solicitud para una nueva evaluación.")
        fecha = st.date_input("Fecha real de carga en SAP", value=datetime.now(ZoneInfo("America/Santiago")).date(), key=pref+"fecha")
        hora = st.time_input("Hora de carga en SAP (Chile)", value=datetime.now(ZoneInfo("America/Santiago")).time().replace(microsecond=0), key=pref+"hora")
        ref = st.text_input("Referencia o enlace de evidencia SAP *", key=pref+"ref")
        confirmado = st.checkbox("La configuración cargada coincide con la aprobada", key=pref+"conf")
        c = {"fecha": datetime.combine(fecha, hora, tzinfo=ZoneInfo("America/Santiago")).astimezone(ZoneInfo("UTC")).replace(tzinfo=None).isoformat(), "referencia": ref}
    comentario = st.text_area("Comentario o motivo de rechazo/devolución", key=pref+"comentario")
    principal = "Validar análisis" if a is not None else "Cargado en SAP" if c is not None else "Aprobar"
    cols = st.columns(3)
    seleccion = None
    for col, accion in zip(cols, [principal, "Devolver", "Rechazar"]):
        if col.button(accion, key=pref+accion, use_container_width=True, type="primary" if accion==principal else "secondary"):
            seleccion = accion
    if seleccion:
        try:
            if seleccion == "Cargado en SAP" and not confirmado:
                raise ValueError("Debes confirmar que la carga coincide con la configuración aprobada.")
            decidir(u["correo"], r["id"], r["version"], seleccion, comentario, analisis=a, carga=c)
            st.session_state["mat_flash"] = f"Solicitud #{r['id']}: {seleccion}."
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _seguimiento(u, registros):
    total = len(registros)
    pendientes = [r for r in registros if puede_actuar(r,u)]
    cerradas = [r for r in registros if r["fecha_carga"] and r["fecha_envio"]]
    cols = st.columns(4)
    cols[0].metric("Solicitudes visibles",total)
    cols[1].metric("Pendientes de mi revisión",len(pendientes))
    cols[2].metric("Cargadas en SAP",len(cerradas))
    promedio = sum((r['fecha_carga']-r['fecha_envio']).total_seconds()/86400 for r in cerradas)/len(cerradas) if cerradas else None
    cols[3].metric("Promedio envío a SAP",f"{promedio:.1f} días" if promedio is not None else "Sin cierres")
    estado = st.selectbox("Filtrar estado", ["Todos", "Pendientes de mi revisión"]+list(ESTADOS), key="mat_filtro_estado")
    tipo = st.selectbox("Filtrar tipo", ["Todos", "Stock de seguridad", "MRP"], key="mat_filtro_tipo")
    busqueda = st.text_input("Buscar código o descripción", key="mat_buscar").strip().lower()
    filtrados = [r for r in registros if (estado=="Todos" or r['estado']==estado or (estado=="Pendientes de mi revisión" and puede_actuar(r,u)))
        and (tipo=="Todos" or r['tipo']==tipo) and (not busqueda or busqueda in (r['material']+' '+r['datos'].get('descripcion','')).lower())]
    if not filtrados:
        st.info("No hay solicitudes para los filtros seleccionados."); return
    st.dataframe([{"Folio":r['id'], "Tipo":r['tipo'], "Material":r['material'], "Descripción":r['datos'].get('descripcion',''),
        "Estado":r['estado'], "Centro":r['centro'], "Área":r['area'], "Solicitante":r['solicitante_nombre']} for r in filtrados], hide_index=True, use_container_width=True)
    n = st.selectbox("Abrir solicitud", [r['id'] for r in filtrados], key="mat_abrir")
    _detalle(next(r for r in filtrados if r['id']==n),u)


def mostrar_materiales():
    u = st.session_state.get("usuario_actual") or {}
    if not u.get("correo"): st.error("Debes iniciar sesión."); return
    st.title("Gestión de Materiales")
    st.caption("Stock de seguridad · Incorporación al MRP · Criticidad · Trazabilidad hasta SAP")
    if st.session_state.get("mat_flash"):
        st.success(st.session_state.pop("mat_flash"))
    registros = listar(u["correo"])
    ss,mrp,guia,seguimiento = st.tabs(["Stock de seguridad", "Incorporación al MRP", "Guía de criticidad", "Seguimiento y aprobaciones"])
    with ss: _formulario("Stock de seguridad",u,registros)
    with mrp:
        st.info("Perfiles: contrapedido, stock de seguridad y pronóstico. Las categorías M quedan excluidas del MRP.")
        _formulario("MRP",u,registros)
    with guia:
        _guia("guia_independiente_")
        st.write("Z: estratégico de baja rotación. A: crítico para continuidad. B: impacto intermedio. C: bajo impacto o sustitución disponible. M: motores y bombas reparables de stock rotativo.")
        st.caption("El texto del procedimiento incluye motores y bombas reparables en M; se recoge esa condición aunque el gráfico pregunte solo por motores.")
    with seguimiento: _seguimiento(u,registros)
