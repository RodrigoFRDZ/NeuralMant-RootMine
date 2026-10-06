"""Gestión de materiales: stock de seguridad, MRP, criticidad y seguimiento."""
import json
import math
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import uuid4
from functools import partial
import hashlib
import streamlit as st
from database.usuarios import cargar_usuarios, cargar_centros
from database.materiales import (PERFILES, ESTADOS, candidatos, criticidad, impacto,
                                guardar, listar, decidir, puede_actuar, mrp_pendiente, exportar_mrp, recuperar_lote_mrp,
                                PENDIENTE_MRP, LISTO_MRP, LISTO_SS)
from ia.cliente import _generar, mensaje_amigable_ia
from pydantic import BaseModel, Field


class JustificacionMaterial(BaseModel):
    justificacion: str
    antecedentes_faltantes: list[str] = Field(default_factory=list)


class OrientacionCriticidad(BaseModel):
    smac: Literal[1, 2, 3] | None = None
    co: Literal[1, 2, 3] | None = None
    te: Literal[1, 2, 3] | None = None
    ma: Literal[1, 2, 3] | None = None
    m_rotativo: bool | None = None
    estrategico: bool | None = None
    fundamento: str
    antecedentes_faltantes: list[str] = Field(default_factory=list)


def _guia(prefijo, datos=None):
    d = datos or {}
    st.caption("Responde según el uso real del repuesto. Puedes pedir orientación a GearBot y revisar sus propuestas antes de aplicarlas.")
    contexto = st.text_area("Contexto del material", value=d.get("contexto", ""),
        placeholder="Qué material es y en qué equipo se usa; qué pasa si falla o no está disponible; riesgos, plazo de compra y sustitutos. Indica si es motor/bomba reparable de stock rotativo.",
        height=120, key=prefijo+"contexto")
    huella = hashlib.sha256(contexto.encode()).hexdigest()
    if st.button("Ayudarme a evaluar la criticidad con IA", key=prefijo+"ia_criticidad"):
        if not contexto.strip():
            st.warning("Describe el material y sus condiciones para que GearBot pueda orientarte.")
        else:
            try:
                with st.spinner("GearBot está revisando el contexto del material…"):
                    res = _generar(
                        "Ayuda al técnico, supervisor o programador a evaluar criticidad. Usa solo hechos del contexto; nunca supongas que falta de información significa ausencia de riesgo. "
                        "Devuelve null para criterios desconocidos y pregunta por ellos. Criterios: smac 1 riesgo seguridad/medio ambiente/calidad, 2 incumple política interna, 3 sin riesgo; "
                        "co 1 afecta directamente operación, 2 impacto menor, 3 no afecta; te 1 más de 90 días, 2 de 21 a 90 días, 3 menos de 21 días; "
                        "ma 1 sin sustituto/solo fabricante, 2 sustituto validado fabricante, 3 sustituto validado empresa. m_rotativo solo si es motor o bomba reparable con stock rotativo. "
                        "estrategico solo con evidencia de baja rotación y graves consecuencias. No apruebes ni inventes clasificaciones. Fundamenta cada propuesta y pide los antecedentes faltantes.",
                        contexto, OrientacionCriticidad)
                st.session_state[prefijo+"orientacion"] = {"huella": huella, "datos": res.model_dump()}
            except Exception as exc:
                st.warning(mensaje_amigable_ia(exc) or "No fue posible consultar GearBot. Puedes completar la guía manualmente.")
    propuesta = st.session_state.get(prefijo+"orientacion", {})
    if propuesta.get("huella") == huella:
        ia = propuesta["datos"]
        st.info(ia["fundamento"])
        nombres = {"smac": "Seguridad, medio ambiente y calidad", "co": "Continuidad operacional", "te": "Tiempo de entrega", "ma": "Sustitución"}
        st.dataframe([{"Criterio": nombres[k], "Respuesta propuesta": str(ia[k]) if ia[k] is not None else "Falta información"} for k in nombres], hide_index=True, use_container_width=True)
        for pregunta in ia["antecedentes_faltantes"]:
            st.write("• " + pregunta)
        if st.button("Usar respuestas propuestas y revisar", key=prefijo+"usar_criticidad"):
            for k in ("smac", "co", "te", "ma"):
                if ia[k] is not None: st.session_state[prefijo+k] = ia[k]
            for campo, sufijo in (("m_rotativo", "m"), ("estrategico", "z")):
                if ia[campo] is not None: st.session_state[prefijo+sufijo] = ia[campo]
    m = st.checkbox("Es motor o bomba reparable con stock rotativo", value=bool(d.get("m_rotativo")), key=prefijo+"m")
    if m:
        st.info("Categoría M: control de reparación y retorno. No se incorpora al MRP.")
        return "M", {"m_rotativo": True, "contexto": contexto}
    opciones = {
        "smac": ["Riesgo para seguridad, medio ambiente o calidad", "Incumple política interna", "Sin riesgo"],
        "co": ["Afecta directamente la operación", "Afecta menormente el proceso", "No afecta el proceso"],
        "te": ["Más de 90 días", "Entre 21 y 90 días", "Menos de 21 días"],
        "ma": ["Sin sustituto; solo fabricante", "Sustituto validado por fabricante", "Sustituto validado por la empresa"],
    }
    etiquetas = {"smac": "Seguridad, medio ambiente y calidad", "co": "Continuidad operacional",
                 "te": "Tiempo de entrega", "ma": "Sustitución del repuesto"}
    respuestas = {"m_rotativo": False}
    cols = st.columns(2)
    for i, (k, opciones_k) in enumerate(opciones.items()):
        with cols[i % 2]:
            anterior = d.get(k)
            respuestas[k] = st.selectbox(etiquetas[k], [1, 2, 3],
                index=anterior-1 if anterior in (1,2,3) else None,
                placeholder="Selecciona una respuesta", format_func=lambda v, opts=opciones_k: opts[v-1], key=prefijo+k)
    respuestas["estrategico"] = st.checkbox("Repuesto estratégico de baja rotación con graves consecuencias si falta", value=bool(d.get("estrategico")), key=prefijo+"z")
    c = criticidad(**respuestas) if all(respuestas[k] is not None for k in opciones) else None
    if c:
        st.success(f"Criticidad sugerida: {c}")
    else:
        st.info("Completa los cuatro criterios para obtener una sugerencia de criticidad.")
    st.caption("Guía basada en SV-DC-MAN-019 · revisión 27-05-2025. Revisa técnicamente las respuestas antes de asignar la criticidad.")
    return c, {**respuestas, "contexto": contexto}


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
    st.subheader("1. Identifica el material")
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
    st.subheader("2. Configuración solicitada")
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
    clase = st.selectbox("Criticidad propuesta *", clases, index=clases.index(seleccion) if seleccion in clases else None, placeholder="Selecciona una criticidad", key=pref+"crit")
    razon_crit = st.text_input("Fundamento de la criticidad", value=d.get("razon_criticidad", ""), key=pref+"razon")
    if respuestas["m_rotativo"]:
        if tipo == "MRP": st.error("Material M: no se permite enviar ni guardar una incorporación al MRP.")
        else: clase = "M"
    justificacion = respaldo = ""
    resp = {}
    if tipo == "Stock de seguridad":
        st.subheader("3. Justifica la cobertura necesaria")
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
    enviar = b.button("Guardar material para MRP" if tipo == "MRP" else "Enviar al jefe de área", key=pref+"enviar", type="primary", use_container_width=True)
    if draft or enviar:
        try:
            if tipo == "MRP" and perfil == "Stock de seguridad" and cantidad <= 0 and enviar:
                raise ValueError("Indica una cantidad para el perfil de stock de seguridad.")
            n = guardar(u["correo"], tipo, datos, resp, enviar=enviar, solicitud_id=elegido or None, version=r["version"] if r else None)
            st.session_state["mat_flash"] = f"Solicitud #{n}: " + ("pendiente de exportación MRP." if enviar and tipo == "MRP" else "enviada al jefe de área." if enviar else "borrador guardado.")
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
        st.dataframe([{"Dato": etiqueta, "Valor": str(d.get(k, "") or "Sin informar")} for k, etiqueta in (
            ("equipos", "Equipos"), ("almacen", "Almacén"), ("criticidad", "Criticidad"),
            ("razon_criticidad", "Fundamento criticidad"), ("cantidad", "Stock solicitado"),
            ("perfil", "Perfil MRP"), ("mercado", "Mercado"), ("lead_time", "Plazo de entrega (días)"))], hide_index=True, use_container_width=True)
        if r["tipo"] == "Stock de seguridad":
            st.write("**Respaldo:**", d.get("respaldo") or "Sin referencias")
            st.write(f"Jefe: {r['jefe_email']} · Analizador: {r['analista_email']} · Subgerente: {r['subgerente_email']}")
        if d.get("analisis"):
            st.write("**Evaluación:**", d["analisis"].get("fundamento", ""))
            st.dataframe([{"Dato": k.replace("_", " ").capitalize(), "Valor": str(v)} for k,v in d["analisis"].items() if k != "impacto"], hide_index=True, use_container_width=True)
        if d.get("exportacion"):
            st.success("Listo: incluido en el Excel MRP descargado por administración.")
            st.caption(f"Lote: {d['exportacion']['lote']} · Fecha UTC: {d['exportacion']['fecha']}")
        if d.get("carga"):
            st.write("**Confirmación de stock:**", d["carga"].get("referencia", ""))
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
    principal = "Validar análisis" if a is not None else "Marcar stock listo" if c is not None else "Aprobar"
    cols = st.columns(3)
    seleccion = None
    for col, accion in zip(cols, [principal, "Devolver", "Rechazar"]):
        if col.button(accion, key=pref+accion, use_container_width=True, type="primary" if accion==principal else "secondary"):
            seleccion = accion
    if seleccion:
        try:
            if seleccion == "Marcar stock listo" and not confirmado:
                raise ValueError("Debes confirmar que la carga coincide con la configuración aprobada.")
            decidir(u["correo"], r["id"], r["version"], seleccion, comentario, analisis=a, carga=c)
            st.session_state["mat_flash"] = f"Solicitud #{r['id']}: {seleccion}."
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _tabla_solicitudes(registros):
    return [{"Folio": r["id"], "Tipo": r["tipo"], "Material": r["material"],
             "Descripción": r["datos"].get("descripcion", ""), "Estado": r["estado"],
             "Centro": r["centro"], "Área": r["area"], "Solicitante": r["solicitante_nombre"]} for r in registros]


@st.fragment(run_every="4s")
def _exportaciones(u):
    registros = listar(u["correo"])
    firma = tuple((r["id"], r["version"], r["estado"]) for r in registros)
    previa = st.session_state.get("mat_exportaciones_estado")
    st.session_state["mat_exportaciones_estado"] = firma
    if previa is not None and previa != firma:
        st.rerun(scope="app")
    pendientes = [r for r in registros if mrp_pendiente(r)]
    st.subheader("Descarga de materiales para MRP")
    st.caption("Incluye todos los pendientes visibles para administración. Los filtros de búsqueda de abajo no recortan este lote.")
    st.info("Al descargar, los materiales del Excel quedan listos por exportación. La incorporación efectiva en SAP se realiza con esa planilla.")
    if pendientes:
        st.dataframe(_tabla_solicitudes(pendientes), hide_index=True, use_container_width=True)
        seleccion = tuple((r["id"], r["version"]) for r in pendientes)
        huella = hashlib.sha256(repr(seleccion).encode()).hexdigest()[:20]
        lote_key = "mat_lote_" + huella
        st.session_state.setdefault(lote_key, str(uuid4()))
        lote = st.session_state[lote_key]
        # Generación diferida: valida el lote y actualiza la BD antes de servir el archivo.
        st.download_button(f"Descargar {len(pendientes)} materiales pendientes · Excel",
            data=partial(exportar_mrp, u["correo"], seleccion, lote),
            file_name=f"MRP_pendientes_{lote}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="mat_exportar_"+huella, type="primary", use_container_width=True, on_click="ignore")
    else:
        st.success("No hay materiales pendientes de exportación MRP.")
    lotes = {}
    for r in registros:
        exp = r["datos"].get("exportacion")
        if exp:
            lotes.setdefault(exp["lote"], {"fecha": exp["fecha"], "cantidad": 0})["cantidad"] += 1
    if lotes:
        with st.expander("Lotes ya descargados · recuperar una planilla"):
            lote = st.selectbox("Lote", list(lotes),
                format_func=lambda n: f"{lotes[n]['fecha'][:19]} UTC · {lotes[n]['cantidad']} materiales · {n[:8]}", key="mat_recuperar_lote")
            st.download_button("Volver a descargar este lote", data=partial(recuperar_lote_mrp, u["correo"], lote),
                file_name=f"MRP_lote_{lote}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="mat_recuperar_excel", on_click="ignore", use_container_width=True)


def _seguimiento(u, registros):
    pendientes_mrp = [r for r in registros if mrp_pendiente(r)]
    listas_ss = [r for r in registros if r["tipo"] == "Stock de seguridad" and r["estado"] == "Pendiente carga SAP"]
    listas = [r for r in registros if r["estado"] in (LISTO_MRP, LISTO_SS, "Cargado en SAP")]
    cols = st.columns(4)
    cols[0].metric("Solicitudes", len(registros))
    cols[1].metric("MRP por descargar", len(pendientes_mrp))
    cols[2].metric("Stock por confirmar", len(listas_ss))
    cols[3].metric("Listas", len(listas))
    if u.get("es_admin"):
        _exportaciones(u)
        st.divider()
    st.subheader("Busca y revisa tus solicitudes")
    a,b,c = st.columns([2,2,3])
    tipo = a.selectbox("Tipo", ["Todos", "Stock de seguridad", "MRP"], key="mat_filtro_tipo")
    situacion = b.selectbox("Situación", ["Pendientes", "Listas", "Todas", "Mi revisión", "Borradores"], key="mat_situacion")
    busqueda = c.text_input("Buscar", placeholder="Folio, código, descripción, área o solicitante", key="mat_buscar").strip().lower()
    estado = st.selectbox("Etapa específica (opcional)", ["Todas"] + sorted({r["estado"] for r in registros}), key="mat_filtro_estado")
    filtrados = []
    for r in registros:
        lista = r["estado"] in (LISTO_MRP, LISTO_SS, "Cargado en SAP")
        if tipo != "Todos" and r["tipo"] != tipo: continue
        if situacion == "Pendientes" and r["estado"] in (LISTO_MRP, LISTO_SS, "Cargado en SAP", "Rechazada", "Borrador"): continue
        if situacion == "Listas" and not lista: continue
        if situacion == "Mi revisión" and not puede_actuar(r,u): continue
        if situacion == "Borradores" and r["estado"] != "Borrador": continue
        if estado != "Todas" and r["estado"] != estado: continue
        texto = " ".join(str(v) for v in (r["id"], r["material"], r["datos"].get("descripcion", ""), r["area"], r["centro"], r["solicitante_nombre"], r["solicitante_email"]))
        if busqueda and busqueda not in texto.lower(): continue
        filtrados.append(r)
    if not filtrados:
        st.info("No hay solicitudes para estos filtros.")
        return
    st.dataframe(_tabla_solicitudes(filtrados), hide_index=True, use_container_width=True)
    n = st.selectbox("Abrir solicitud", [r["id"] for r in filtrados],
        format_func=lambda n: next(f"#{n} · {r['material']} · {r['datos'].get('descripcion','')} · {r['estado']}" for r in filtrados if r["id"]==n), key="mat_abrir")
    with st.container(border=True):
        _detalle(next(r for r in filtrados if r["id"] == n), u)


def mostrar_materiales():
    u = st.session_state.get("usuario_actual") or {}
    if not u.get("correo"):
        st.error("Debes iniciar sesión.")
        return
    st.title("Gestión de Materiales")
    st.caption("Elige qué necesitas gestionar")
    if st.session_state.get("mat_flash"):
        st.success(st.session_state.pop("mat_flash"))
    if "mat_vista" not in st.session_state:
        st.session_state["mat_vista"] = "Stock de seguridad"
    ventanas = [("Stock de seguridad", "Solicita cobertura y conserva el flujo de aprobación.", "📦"),
                ("Incorporación al MRP", "Registra materiales para la descarga de administración.", "📋"),
                ("Guía de criticidad", "Evalúa el material con ayuda de GearBot.", "🤖"),
                ("Seguimiento y aprobaciones", "Busca solicitudes, revisa avances y confirma stock.", "🔎")]
    for col, (nombre, descripcion, icono) in zip(st.columns(4), ventanas):
        with col, st.container(border=True):
            st.markdown(f"**{icono} {nombre}**")
            st.caption(descripcion)
            if st.button("Abrir", key="mat_ventana_"+nombre, use_container_width=True,
                         type="primary" if st.session_state["mat_vista"] == nombre else "secondary"):
                st.session_state["mat_vista"] = nombre
                st.rerun()
    st.divider()
    vista = st.session_state["mat_vista"]
    st.header(vista)
    registros = listar(u["correo"])
    if vista == "Stock de seguridad":
        _formulario("Stock de seguridad", u, registros)
    elif vista == "Incorporación al MRP":
        st.info("Guarda cada material que deba incorporarse al MRP. Quedará pendiente de descarga por administración, sin responsables de aprobación.")
        _formulario("MRP", u, registros)
    elif vista == "Guía de criticidad":
        st.write("Describe el repuesto y revisa cómo afecta a tu operación. GearBot propone respuestas; tú revisas la clasificación.")
        _guia("guia_independiente_")
        st.write("**Z:** estratégico de baja rotación · **A:** crítico para continuidad · **B:** impacto intermedio · **C:** bajo impacto o sustitución disponible · **M:** motores y bombas reparables de stock rotativo.")
    else:
        _seguimiento(u, registros)
