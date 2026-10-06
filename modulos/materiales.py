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
                                PENDIENTE_MRP, LISTO_MRP, LISTO_SS, responsables_stock, es_reemplazo_jefe, sincronizar_flujo_stock)
from modulos.nuevo_adf import AREAS
from database.usuarios import _norm
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


def _limpiar_formulario_enviado():
    tipo = st.session_state.pop("mat_formulario_enviado", None)
    if tipo not in ("Stock de seguridad", "MRP"):
        return
    prefijo = "mat_ss_" if tipo == "Stock de seguridad" else "mat_mrp_"
    # Se ejecuta al inicio del rerun, antes de crear cualquier widget del formulario.
    for clave in list(st.session_state):
        if str(clave).startswith(prefijo):
            st.session_state.pop(clave, None)
    st.session_state["mat_area_vacia_"+tipo] = True


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
        anterior_area = d.get("area", "" if st.session_state.get("mat_area_vacia_"+tipo) else u.get("area", ""))
        opciones_area = list(AREAS)
        indice = next((i for i,x in enumerate(opciones_area) if _norm(x)==_norm(anterior_area)), None)
        area = st.selectbox("Área *", opciones_area, index=indice,
                            placeholder="Selecciona el área", key=pref+"area") or ""
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
        st.write("**Responsables asignados automáticamente**")
        usuarios = cargar_usuarios()
        resp = responsables_stock(usuarios, centro, area)
        nombres = {x["correo"]: x["nombre"] for x in usuarios}
        if resp["jefe"]:
            st.info(f"Jefe de {area}: {nombres.get(resp['jefe'], resp['jefe'])}")
        else:
            st.warning("Selecciona un área con jefe asignado en el maestro ADF. Sin esa asignación puedes guardar un borrador.")
        st.caption(f"Análisis: {nombres.get(resp['analista'], resp['analista'])} · Subgerente: {nombres.get(resp['subgerente'], resp['subgerente'])}")
        st.caption("Rodrigo Fernández puede reemplazar al jefe de su centro por ausencia. La aprobación del subgerente es obligatoria y queda pendiente hasta que pueda revisarla.")
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
            if enviar:
                st.session_state["mat_formulario_enviado"] = tipo
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _resumen_valorizacion(a):
    imp = impacto(a)
    moneda = a.get("moneda", "")
    def dinero(valor):
        return f"{valor:,.2f} {moneda}"
    def porcentaje(valor):
        return f"{valor:.2f}%" if valor is not None else "Sin base de bodega"
    st.markdown("**Qué representa el stock de seguridad**")
    x,y,z = st.columns(3)
    x.metric("Valor total del SS propuesto", dinero(imp["valor_ss_total"]))
    y.metric("Stock total actual de bodega", dinero(float(a.get("valor_bodega",0))))
    z.metric("SS total / bodega actual", porcentaje(imp["porcentaje_ss_total_bodega_actual"]))
    st.caption("Participación = cantidad total de SS propuesta × precio unitario ÷ valor del inventario actual de toda la bodega. No se suma otra vez el SS si ese material ya está en el inventario.")
    if imp["porcentaje_ss_total_bodega_actual"] is not None and imp["porcentaje_ss_total_bodega_actual"] > 100:
        st.warning("El SS propuesto valorizado supera el inventario total actual declarado de la bodega. Revisa la cantidad, el precio y que el valor de bodega incluya todos sus materiales en la misma moneda.")
    x,y,z = st.columns(3)
    x.metric("Aumento SS valorizado", dinero(imp["incremento_ss"]))
    y.metric("Reposición adicional estimada", dinero(imp["reposicion"]))
    z.metric("SS total / bodega con reposición", porcentaje(imp["porcentaje_ss_total_bodega_proyectada"]))
    st.caption(f"Valor actual de este material en bodega: {dinero(imp['valor_stock_material_actual'])}. Bodega con reposición adicional estimada: {dinero(imp['bodega_proyectada'])}. Esta proyección suma solo la compra adicional calculada; no agrega como ingreso físico las OC pendientes. La compra estimada sí descuenta stock y OC y considera reservas.")
    st.markdown("**Cobertura de reserva y permanencia del material**")
    x,y = st.columns(2)
    cobertura = imp["cobertura_ss_meses"]
    x.metric("Cobertura del SS ante emergencias", f"{cobertura:.1f} meses" if cobertura is not None else "Sin base de emergencias")
    cobertura_actual = imp["cobertura_stock_meses"]
    y.metric("Cobertura del stock actual del material", f"{cobertura_actual:.1f} meses" if cobertura_actual is not None else "Sin consumo promedio")
    if cobertura is not None:
        st.caption(f"El SS propuesto equivale a {imp['cobertura_ss_dias']:.0f} días del consumo histórico de emergencia por falla, usando meses de 30 días. Es cobertura orientativa, no una fecha garantizada de utilización.")
    else:
        st.info("Sin un consumo positivo registrado de emergencias por falla no se estima cobertura del SS. No se sustituye por consumo planificado; justifica la reserva por criticidad cuando no hay historial.")
    if a.get("stock_promedio_observado"):
        meses = imp["permanencia_promedio_meses"]
        st.metric("Permanencia promedio orientativa del material", f"{meses:.1f} meses" if meses is not None else "No estimable")
        st.caption("Stock promedio observado ÷ consumo promedio mensual del mismo período. Estima la permanencia media del inventario del material; no determina cuánto permanece una unidad específica de stock de seguridad.")
    st.markdown("**Uso de SS registrado por emergencias de fallas**")
    if a.get("uso_ss_registrado"):
        x,y,z = st.columns(3)
        x.metric("Cantidad retirada por fallas", f"{imp['uso_ss_cantidad']:,.2f} {a.get('unidad','unidades')}")
        y.metric("Valor utilizado por emergencias", dinero(imp["uso_ss_valorizado"]))
        participacion = imp["uso_ss_porcentaje_consumo_periodo"]
        z.metric("Emergencias SS / consumo total", f"{participacion:.2f}%" if participacion is not None else "Sin consumo base")
        st.caption(f"Período: {a.get('periodo_consumo_meses', 'sin informar')} meses. La valorización usa el precio unitario de esta evaluación, no los precios históricos de las salidas.")
        emergencia_mensual = imp["consumo_emergencia_ss_mensual"]
        if emergencia_mensual is not None:
            st.caption(f"Consumo promedio de emergencia desde SS: {emergencia_mensual:.2f} {a.get('unidad','unidades')}/mes. Cobertura de reserva = SS propuesto ÷ este promedio; se excluye consumo planificado.")
        equivalentes = imp["uso_ss_reservas_equivalentes"]
        if equivalentes is not None:
            st.caption(f"Se utilizó el equivalente a {equivalentes:.2f} veces el SS histórico de referencia declarado. Puede superar una reserva completa si hubo reposiciones durante el período.")
        if participacion is not None and participacion > 100:
            st.warning("El uso declarado de la reserva supera el consumo total estimado del mismo período. Revisa cantidades, unidades y período del consumo promedio.")
        elif float(a.get("consumo_mensual",0)) == 0 and imp["uso_ss_cantidad"] > 0:
            st.warning("Se declaró uso de la reserva con consumo promedio cero. Revisa que ambos antecedentes correspondan al mismo período.")
        st.caption("Respaldo del uso: " + (a.get("uso_ss_respaldo") or "Sin referencia informada"))
    else:
        st.caption("Uso de SS por falla: sin registro informado. No se considera cero ni se deduce del consumo total o planificado.")
    return imp


def _evaluacion(r, clave=""):

    d = r["datos"]; anterior = d.get("analisis", {})
    a = {"unidad": d.get("unidad", "unidades")}
    pref = f"eval_{clave}_{r['id']}_{r['version']}_"
    clases = ["A", "B", "C", "Z"] if r["tipo"] == "MRP" else ["A", "B", "C", "Z", "M"]
    clase = anterior.get("criticidad", d["criticidad"])
    a["criticidad"] = st.selectbox("Criticidad validada", clases, index=clases.index(clase) if clase in clases else 0, key=pref+"crit")
    if r["tipo"] == "MRP":
        # El perfil solicitado se conserva en la aprobación. Cambios se devuelven al solicitante.
        st.info(f"Perfil solicitado: {d['perfil']} · {d['mercado']} · Lead time: {d['lead_time']} días")
    if r["tipo"] == "Stock de seguridad" or d.get("perfil") == "Stock de seguridad":
        campos = [("ss_actual", "Stock de seguridad actual"), ("ss_propuesto", "Stock de seguridad propuesto"),
            ("stock", "Stock actual del material en bodega"), ("reservas", "Reservas pendientes"), ("oc", "OC pendientes de entrega"),
            ("precio", "Precio unitario"), ("valor_bodega", "Valor del stock total actual de la bodega"),
            ("consumo_mensual", "Consumo promedio mensual total del material"),
            ("lead_time_dias", "Lead time en días")]
        st.markdown("**Stock en bodega y valorización**")
        st.caption(f"Cantidades y consumo en {d['unidad']}. El valor total de la bodega debe incluir todos sus materiales; no solo este repuesto.")
        ayudas = {
            "stock": "Cantidad física de este material en la fecha de los datos. No es el stock de seguridad ni el total de unidades de otros materiales.",
            "valor_bodega": "Valor del inventario físico total de la bodega en la misma fecha y moneda; es la base de comparación del SS valorizado.",
            "consumo_mensual": "Salidas promedio totales del material por mes: planificadas y emergencias. Solo se usa para la cobertura de bodega y la permanencia del material; la cobertura del SS usa únicamente emergencias por falla.",
            "precio": "Precio unitario de este material, en la moneda seleccionada.",
        }
        cols = st.columns(2)
        for i,(k,etiqueta) in enumerate(campos):
            with cols[i%2]:
                inicial = anterior.get(k, d.get("cantidad", 0) if k=="ss_propuesto" else d.get("lead_time", 0) if k=="lead_time_dias" else 0)
                a[k] = st.number_input(etiqueta, min_value=0.0, value=float(inicial), key=pref+k, help=ayudas.get(k))
        a["moneda"] = st.selectbox("Moneda de todos los valores", ["USD", "CLP"], index=int(anterior.get("moneda")=="CLP"), key=pref+"moneda")
        a["fecha_datos"] = st.date_input("Fecha de los datos de bodega", value=date.fromisoformat(anterior["fecha_datos"]) if anterior.get("fecha_datos") else date.today(), key=pref+"fecha").isoformat()
        a["periodo_consumo_meses"] = st.number_input("Período usado para el consumo promedio (meses)",
            min_value=1, value=max(1,int(anterior.get("periodo_consumo_meses",12))), step=1, key=pref+"periodo_consumo")
        a["stock_promedio_observado"] = st.checkbox("Tengo el stock promedio observado del material en ese mismo período",
            value=bool(anterior.get("stock_promedio_observado")), key=pref+"tengo_promedio")
        if a["stock_promedio_observado"]:
            a["stock_promedio"] = st.number_input(f"Stock promedio observado del material ({d['unidad']})", min_value=0.0,
                value=float(anterior.get("stock_promedio",0)), key=pref+"stock_promedio",
                help="Promedio de las existencias observadas durante el mismo período que el consumo. No reemplazarlo por la cantidad solicitada de SS.")
        st.markdown("**Consumo de emergencia por falla desde el SS**")
        a["uso_ss_registrado"] = st.checkbox("Tengo registro de salidas del SS por emergencias de fallas",
            value=bool(anterior.get("uso_ss_registrado")), key=pref+"uso_ss_registrado")
        if a["uso_ss_registrado"]:
            st.caption("Registra solo salidas desde la reserva para resolver fallas no planificadas, en el mismo período del consumo promedio. Los trabajos planificados se excluyen del uso de SS.")
            x,y = st.columns(2)
            a["uso_ss_cantidad"] = x.number_input(f"Cantidad retirada del SS por fallas ({d['unidad']})", min_value=0.0,
                value=float(anterior.get("uso_ss_cantidad",0)), key=pref+"uso_ss_cantidad")
            a["ss_historico_referencia"] = y.number_input(f"SS histórico de referencia del período ({d['unidad']})", min_value=0.0,
                value=float(anterior.get("ss_historico_referencia",anterior.get("ss_actual",0))), key=pref+"ss_historico_referencia",
                help="Cantidad de reserva que estuvo vigente en el período analizado. Si cambió, informa una base representativa y explica su criterio en el respaldo.")
            a["uso_ss_respaldo"] = st.text_input("Aviso / OT correctiva y respaldo de las salidas por falla", value=anterior.get("uso_ss_respaldo", ""),
                placeholder="Aviso de falla, OT correctiva, movimientos SAP y reporte de salidas de emergencia", key=pref+"uso_ss_respaldo")
            a["uso_ss_solo_emergencias"] = st.checkbox("Confirmo que son emergencias por falla; excluí todos los trabajos planificados",
                value=bool(anterior.get("uso_ss_solo_emergencias")), key=pref+"solo_emergencias")
        a["ss_estadistico_datos_emergencia"] = st.checkbox("Tengo una serie mensual de emergencias por falla para estimar el SS estadístico",
            value=bool(anterior.get("ss_estadistico_datos_emergencia")), key=pref+"datos_estadisticos_emergencia")
        if a["ss_estadistico_datos_emergencia"]:
            a["desviacion"] = st.number_input(f"Desviación mensual de consumo de emergencia por falla ({d['unidad']})",
                min_value=0.0, value=float(anterior.get("desviacion",0)), key=pref+"desviacion")
            nivel = st.selectbox("Nivel de servicio para cálculo estadístico", [90, 95, 99], key=pref+"servicio")
            a["nivel_servicio"] = nivel
            sugerencia = math.ceil({90:1.28,95:1.64,99:2.33}[nivel]*a["desviacion"]*math.sqrt(a["lead_time_dias"]/30))
            a["ss_estadistico"] = sugerencia
            st.caption(f"SS estadístico de emergencias orientativo: {sugerencia} {d['unidad']}. Demanda mensual y lead time convertido a meses de 30 días. Validar unidad y redondeo antes de aprobar.")
            st.caption("Para repuestos estratégicos de baja rotación, el consumo histórico por sí solo no define la cobertura necesaria. Justifica la cantidad técnicamente.")
        st.caption("Los consumos planificados no justifican el SS. Para repuestos de baja rotación sin historial de fallas, sustenta la reserva por criticidad y consecuencias de no disponer del material.")
        _resumen_valorizacion(a)
    a["fundamento"] = st.text_area("Fundamento del análisis *", value=anterior.get("fundamento", ""), key=pref+"fund")
    return a


def _detalle(r, u, clave="general"):
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
            if r["tipo"] == "Stock de seguridad":
                _resumen_valorizacion(d["analisis"])
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
        file_name=f"Solicitud_materiales_{r['id']}.json", mime="application/json", key=f"desc_{clave}_{r['id']}")
    if r["tipo"] == "Stock de seguridad" and r["estado"] == "Pendiente subgerente":
        st.info("Esperando la aprobación del subgerente. Esta etapa no admite reemplazo.")
    if not puede_actuar(r,u): return
    st.write("**Acciones de la etapa actual**")
    a = _evaluacion(r, clave) if r["estado"] == "Pendiente análisis" else None
    pref = f"accion_{clave}_{r['id']}_{r['version']}_"
    c = None
    if r["estado"] == "Pendiente carga SAP":
        st.info("Confirma que la configuración cargada corresponde exactamente a la aprobada. Si necesitas modificarla, devuelve la solicitud para una nueva evaluación.")
        fecha = st.date_input("Fecha real de carga en SAP", value=datetime.now(ZoneInfo("America/Santiago")).date(), key=pref+"fecha")
        hora = st.time_input("Hora de carga en SAP (Chile)", value=datetime.now(ZoneInfo("America/Santiago")).time().replace(microsecond=0), key=pref+"hora")
        ref = st.text_input("Referencia o enlace de evidencia SAP *", key=pref+"ref")
        confirmado = st.checkbox("La configuración cargada coincide con la aprobada", key=pref+"conf")
        c = {"fecha": datetime.combine(fecha, hora, tzinfo=ZoneInfo("America/Santiago")).astimezone(ZoneInfo("UTC")).replace(tzinfo=None).isoformat(), "referencia": ref}
    reemplazo = es_reemplazo_jefe(r,u)
    confirmo_ausencia = True
    if reemplazo:
        st.warning("Vas a validar en reemplazo del jefe. La decisión quedará registrada con tu nombre y el motivo de ausencia.")
        confirmo_ausencia = st.checkbox("Confirmo que el jefe está ausente y actúo como reemplazo", key=pref+"ausencia")
    comentario = st.text_area("Motivo de ausencia del jefe y comentario *" if reemplazo else "Comentario o motivo de rechazo/devolución", key=pref+"comentario")
    principal = "Validar análisis" if a is not None else "Marcar stock listo" if c is not None else "Aprobar"
    cols = st.columns(3)
    seleccion = None
    for col, accion in zip(cols, [principal, "Devolver", "Rechazar"]):
        if col.button(accion, key=pref+accion, use_container_width=True, type="primary" if accion==principal else "secondary"):
            seleccion = accion
    if seleccion:
        try:
            if reemplazo and not confirmo_ausencia:
                raise ValueError("Confirma la ausencia del jefe antes de actuar como reemplazo.")
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


def _seguimiento_general(u, registros):
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


def _bandeja_aprobaciones(u, registros):
    pendientes = [r for r in registros if puede_actuar(r,u)]
    objetivo = st.session_state.pop("mat_solicitud_enlace", None)
    st.subheader("Solicitudes que puedes revisar")
    st.caption("La bandeja incluye tu etapa actual y, para Rodrigo, las solicitudes donde puede reemplazar al jefe. La subgerencia conserva su aprobación obligatoria.")
    if objetivo is not None:
        destino = next((r for r in registros if r["id"] == objetivo), None)
        if destino is None:
            st.warning("La solicitud del enlace no está disponible para tu cuenta.")
        elif not puede_actuar(destino,u):
            st.info(f"Solicitud #{objetivo}: {destino['estado']}. No requiere una acción tuya en esta etapa.")
            _detalle(destino, u, clave="enlace")
        else:
            st.session_state["mat_aprobacion_abrir"] = objetivo
    if not pendientes:
        st.success("No tienes solicitudes de materiales pendientes de revisión.")
        return
    st.dataframe(_tabla_solicitudes(pendientes), hide_index=True, use_container_width=True)
    opciones = [r["id"] for r in pendientes]
    if st.session_state.get("mat_aprobacion_abrir") not in opciones:
        st.session_state.pop("mat_aprobacion_abrir", None)
    n = st.selectbox("Solicitud para aprobar", opciones,
        format_func=lambda n: next(f"#{n} · {r['material']} · {r['datos'].get('descripcion','')} · {r['estado']}" for r in pendientes if r["id"]==n),
        key="mat_aprobacion_abrir")
    with st.container(border=True):
        _detalle(next(r for r in pendientes if r["id"]==n),u,clave="bandeja")


def _seguimiento(u, registros):
    cantidad = sum(puede_actuar(r,u) for r in registros)
    bandeja, general = st.tabs([f"✅ Mis aprobaciones ({cantidad})", "🔎 Seguimiento de solicitudes"])
    with bandeja:
        _bandeja_aprobaciones(u, registros)
    with general:
        _seguimiento_general(u, registros)


def mostrar_materiales():
    _limpiar_formulario_enviado()
    u = st.session_state.get("usuario_actual") or {}
    if not u.get("correo"):
        st.error("Debes iniciar sesión.")
        return
    if u.get("es_admin"):
        try:
            sincronizar_flujo_stock(u["correo"])
        except ValueError as exc:
            st.warning(str(exc))
    st.title("Gestión de Materiales")
    st.caption("Elige qué necesitas gestionar")
    if st.session_state.get("mat_flash"):
        st.success(st.session_state.pop("mat_flash"))
    if "mat_vista" not in st.session_state:
        st.session_state["mat_vista"] = "Stock de seguridad"
    st.markdown("""<style>
    .mat-nav-title {min-height: 42px; display: flex; align-items: center;
        font-weight: 650; line-height: 1.35; margin-bottom: 8px;}
    .mat-nav-description {min-height: 64px; margin: 0; line-height: 1.5;
        font-size: .875rem; color: #a5adb7;}
    @media (max-width: 900px) {
        .mat-nav-title {min-height: 64px;}
        .mat-nav-description {min-height: 88px;}
    }
    </style>""", unsafe_allow_html=True)
    ventanas = [("Stock de seguridad", "Solicita cobertura y conserva el flujo de aprobación.", "📦"),
                ("Incorporación al MRP", "Registra materiales para la descarga de administración.", "📋"),
                ("Guía de criticidad", "Evalúa el material con ayuda de GearBot.", "🤖"),
                ("Seguimiento y aprobaciones", "Busca solicitudes, revisa avances y confirma stock.", "🔎")]
    for col, (nombre, descripcion, icono) in zip(st.columns(4), ventanas):
        with col, st.container(border=True):
            st.markdown(f'<div class="mat-nav-title">{icono}&nbsp; {nombre}</div>'
                        f'<p class="mat-nav-description">{descripcion}</p>', unsafe_allow_html=True)
            if st.button("Abrir", key="mat_ventana_"+nombre, use_container_width=True,
                         type="primary" if st.session_state["mat_vista"] == nombre else "secondary"):
                st.session_state["mat_vista"] = nombre
                st.session_state["pagina"] = "📦 Gestión de Materiales"
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
