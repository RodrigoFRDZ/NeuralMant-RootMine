import json

import streamlit as st

from database.conocimiento import buscar_casos_similares, formatear_contexto_casos
from database.repositorio_adf import guardar_adf
from ia.cliente import (
    generar_cadenas_y_planes,
    generar_diagnostico,
    generar_informe_final,
    generar_ishikawa,
)
from modulos.diagrama_ishikawa import mostrar_ishikawa
from reportes.pdf_adf import generar_pdf_adf


AREAS = [
    "Faena", "Procesos", "Congelado", "Elaborados", "ADM / Despacho",
    "Servicios", "SADEMA", "Otra",
]

CATEGORIAS = {
    "Máquina": "maquina",
    "Método": "metodo",
    "Mano de obra": "mano_obra",
    "Material": "material",
    "Medición": "medicion",
    "Medio ambiente": "medio_ambiente",
}

TOTAL_ETAPAS = 9


def inicializar() -> None:
    if "nuevo_adf" not in st.session_state:
        st.session_state.nuevo_adf = {
            "paso": 1,
            "area": "",
            "equipo": "",
            "aviso_sap": "",
            "relato_original": "",
            "casos_similares": [],
            "diagnostico": None,
            "efecto": "",
            "principio_funcionamiento": "",
            "ishikawa_ia": None,
            "ishikawa_validado": {},
            "causas_priorizadas": [],
            "profundizacion": None,
            "cadenas_causales": [],
            "plan_prevencion": [],
            "informe_final": None,
            "imagen_falla": None,
            "pdf_bytes": None,
            "solicitudes_ia": 0,
            "id_guardado": None,
        }


def avanzar(paso: int) -> None:
    st.session_state.nuevo_adf["paso"] = paso
    st.rerun()


def encabezado(titulo: str, subtitulo: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <h1>{titulo}</h1>
            <p>{subtitulo}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_error_ia(error: Exception) -> None:
    st.error(f"No fue posible completar la operación de IA: {error}")
    st.caption(
        "Revisa la clave, el modelo, la cuota disponible y la conexión a internet."
    )


def indicador_consumo() -> None:
    solicitudes = st.session_state.nuevo_adf.get("solicitudes_ia", 0)
    st.caption(f"Solicitudes IA utilizadas en este ADF: {solicitudes} de 4 previstas.")


def paso_relato() -> None:
    encabezado(
        "Contexto inicial de la falla",
        "Primera llamada: comprensión del evento, fenómeno y principio de funcionamiento.",
    )
    datos = st.session_state.nuevo_adf
    opciones = ["Seleccione un área"] + AREAS

    with st.form("form_relato", clear_on_submit=False):
        area = st.selectbox(
            "Área", opciones,
            index=opciones.index(datos["area"]) if datos["area"] else 0,
        )
        equipo = st.text_input("Equipo", value=datos["equipo"], placeholder="Ejemplo: Novamax")
        aviso = st.text_input("Aviso SAP", value=datos["aviso_sap"], placeholder="Opcional")
        relato = st.text_area(
            "Relato original", value=datos["relato_original"], height=260,
            placeholder="Describe alarma, condición encontrada, intervención y resultado.",
        )
        enviar = st.form_submit_button(
            "Analizar contexto con IA →", type="primary", use_container_width=True,
        )

    if not enviar:
        return
    if area == "Seleccione un área":
        st.error("Selecciona el área.")
        return
    if len(equipo.strip()) < 3:
        st.error("Ingresa el equipo.")
        return
    if len(relato.strip()) < 20:
        st.error("Describe el evento con un poco más de detalle.")
        return
    if aviso.strip() and not aviso.strip().isdigit():
        st.error("El aviso SAP debe contener solo números.")
        return

    datos.update({
        "area": area,
        "equipo": equipo.strip(),
        "aviso_sap": aviso.strip(),
        "relato_original": relato.strip(),
    })
    try:
        with st.spinner("GearBot está analizando el contexto técnico..."):
            casos = buscar_casos_similares(equipo=equipo.strip(), relato=relato.strip())
            diagnostico = generar_diagnostico(
                area=area,
                equipo=equipo.strip(),
                aviso_sap=aviso.strip(),
                relato=relato.strip(),
                casos_similares=formatear_contexto_casos(casos),
            )
        datos["casos_similares"] = [caso.__dict__ for caso in casos]
        datos["diagnostico"] = diagnostico.model_dump()
        datos["efecto"] = diagnostico.fenomeno_propuesto
        datos["principio_funcionamiento"] = diagnostico.principio_funcionamiento
        datos["solicitudes_ia"] = 1
        avanzar(2)
    except Exception as error:
        mostrar_error_ia(error)


def paso_diagnostico() -> None:
    encabezado(
        "Validación del fenómeno",
        "Corrige la interpretación y el principio de funcionamiento antes del Ishikawa.",
    )
    datos = st.session_state.nuevo_adf
    diagnostico = datos["diagnostico"]
    indicador_consumo()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Hechos confirmados")
        for item in diagnostico["hechos_confirmados"]:
            st.write(f"• {item}")
        st.subheader("Condición encontrada")
        st.info(diagnostico["condicion_encontrada"] or "No identificada")
        st.subheader("Acción de recuperación")
        st.write(diagnostico["accion_recuperacion"] or "No informada")
    with col2:
        st.subheader("Síntomas")
        for item in diagnostico["sintomas"]:
            st.write(f"• {item}")
        st.subheader("Información faltante")
        for item in diagnostico["informacion_faltante"]:
            st.warning(item)

    with st.form("form_validar_diagnostico"):
        st.info(f"**Justificación IA:** {diagnostico['justificacion_fenomeno']}")
        efecto = st.text_area("Fenómeno o efecto técnico", value=datos["efecto"], height=110)
        principio = st.text_area(
            "Principio de funcionamiento",
            value=datos["principio_funcionamiento"],
            height=190,
            help="Debe explicar cómo funciona el conjunto antes de explicar cómo falló.",
        )
        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Editar relato", use_container_width=True)
        continuar = c2.form_submit_button(
            "Generar Ishikawa con IA →", type="primary", use_container_width=True,
        )

    if volver:
        avanzar(1)
    if continuar:
        if len(efecto.strip()) < 10:
            st.error("El fenómeno necesita mayor precisión.")
            return
        if len(principio.strip()) < 30:
            st.error("Explica con mayor detalle el principio de funcionamiento.")
            return
        datos["efecto"] = efecto.strip()
        datos["principio_funcionamiento"] = principio.strip()
        try:
            with st.spinner("GearBot está construyendo el Ishikawa 6M..."):
                ishikawa = generar_ishikawa(
                    area=datos["area"],
                    equipo=datos["equipo"],
                    relato=datos["relato_original"],
                    fenomeno=datos["efecto"],
                    principio_funcionamiento=datos["principio_funcionamiento"],
                    hechos=diagnostico["hechos_confirmados"],
                )
            datos["ishikawa_ia"] = ishikawa.model_dump()
            datos["solicitudes_ia"] = 2
            avanzar(3)
        except Exception as error:
            mostrar_error_ia(error)


def paso_ishikawa() -> None:
    encabezado(
        "Ishikawa 6M ordenado",
        "Revisa la matriz uniforme y selecciona solo las causas aplicables.",
    )
    datos = st.session_state.nuevo_adf
    ishikawa = datos["ishikawa_ia"]
    indicador_consumo()
    mostrar_ishikawa(datos["efecto"], ishikawa)

    st.info(ishikawa.get("resumen_tecnico", ""))
    for advertencia in ishikawa.get("advertencias", []):
        st.warning(advertencia)

    with st.form("form_ishikawa"):
        resultado: dict[str, list[dict]] = {}
        for categoria, clave in CATEGORIAS.items():
            with st.expander(categoria, expanded=True):
                seleccionadas = []
                for indice, causa in enumerate(ishikawa.get(clave, [])):
                    incluir = st.checkbox(
                        f"{causa['causa']} · Prioridad {causa['prioridad_revision']}",
                        value=causa["prioridad_revision"] == "Alta",
                        key=f"inc_{clave}_{indice}",
                    )
                    mecanismo = st.text_area(
                        f"Mecanismo - {causa['causa']}",
                        value=causa["mecanismo"],
                        key=f"mec_{clave}_{indice}",
                        height=75,
                    )
                    if causa.get("preguntas_validacion"):
                        st.caption("Validar: " + " | ".join(causa["preguntas_validacion"]))
                    if incluir:
                        seleccionadas.append({**causa, "mecanismo": mecanismo.strip()})

                extras = st.text_area(
                    f"Causas observadas adicionales en {categoria}",
                    placeholder="Una causa concreta por línea",
                    key=f"extras_{clave}", height=70,
                )
                for linea in extras.splitlines():
                    if linea.strip():
                        seleccionadas.append({
                            "causa": linea.strip(),
                            "mecanismo": "Causa agregada por el equipo investigador.",
                            "prioridad_revision": "Alta",
                            "preguntas_validacion": [],
                        })
                resultado[categoria] = seleccionadas

        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver", use_container_width=True)
        continuar = c2.form_submit_button(
            "Seleccionar causas para 5 Porqués →", type="primary", use_container_width=True,
        )

    if volver:
        avanzar(2)
    if continuar:
        if sum(len(items) for items in resultado.values()) < 1:
            st.error("Selecciona o agrega al menos una causa.")
            return
        datos["ishikawa_validado"] = resultado
        avanzar(4)


def paso_priorizacion() -> None:
    encabezado(
        "Causas probables a profundizar",
        "La tercera llamada generará todos los 5 Porqués y planes preventivos en conjunto.",
    )
    datos = st.session_state.nuevo_adf
    indicador_consumo()
    opciones = [
        f"{categoria} | {causa['causa']}"
        for categoria, causas in datos["ishikawa_validado"].items()
        for causa in causas
    ]
    with st.form("form_priorizar"):
        priorizadas = st.multiselect(
            "Causas a profundizar", options=opciones,
            default=opciones[: min(2, len(opciones))],
            help="Para cuidar cuota y claridad, se recomienda seleccionar entre 1 y 3.",
        )
        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver al Ishikawa", use_container_width=True)
        generar = c2.form_submit_button(
            "Generar 5 Porqués y planes con IA →", type="primary", use_container_width=True,
        )
    if volver:
        avanzar(3)
    if generar:
        if not priorizadas:
            st.error("Selecciona al menos una causa probable.")
            return
        datos["causas_priorizadas"] = priorizadas
        contexto = (
            f"Relato: {datos['relato_original']}\n"
            f"Fenómeno: {datos['efecto']}\n"
            f"Hechos: {json.dumps(datos['diagnostico']['hechos_confirmados'], ensure_ascii=False)}"
        )
        try:
            with st.spinner("GearBot está desarrollando las cadenas causales y planes preventivos..."):
                resultado = generar_cadenas_y_planes(
                    efecto=datos["efecto"],
                    principio_funcionamiento=datos["principio_funcionamiento"],
                    causas_seleccionadas=priorizadas,
                    contexto_validado=contexto,
                )
            datos["profundizacion"] = resultado.model_dump()
            datos["solicitudes_ia"] = 3
            avanzar(5)
        except Exception as error:
            mostrar_error_ia(error)


def paso_causal() -> None:
    encabezado(
        "5 Porqués editable con ayuda de IA",
        "La IA define entre 3 y 5 niveles según la complejidad. Puedes agregar o quitar niveles antes de continuar.",
    )
    datos = st.session_state.nuevo_adf
    indicador_consumo()
    profundizacion = datos["profundizacion"]

    with st.form("form_cadenas"):
        cadenas_editadas = []
        for indice_cadena, cadena in enumerate(profundizacion.get("cadenas", [])):
            st.subheader(f"Causa {indice_cadena + 1}: {cadena['causa']}")
            st.warning(cadena.get("advertencia", "Debe validarse en terreno."))
            niveles_originales = list(cadena.get("niveles", []))
            clave_cantidad = f"cantidad_niveles_{indice_cadena}"
            st.session_state.setdefault(clave_cantidad, max(3, min(5, len(niveles_originales))))
            cantidad_niveles = st.number_input(
                "Cantidad de niveles causales",
                min_value=3,
                max_value=5,
                step=1,
                key=clave_cantidad,
                help="La IA propone la profundidad inicial. Puedes ajustarla entre 3 y 5 niveles.",
            )
            while len(niveles_originales) < cantidad_niveles:
                numero = len(niveles_originales) + 1
                respuesta_anterior = niveles_originales[-1].get("respuesta_sugerida", "la condición anterior") if niveles_originales else "la causa seleccionada"
                niveles_originales.append({
                    "nivel": numero,
                    "pregunta": f"¿Por qué ocurrió que {respuesta_anterior.rstrip('.').lower()}?",
                    "respuesta_sugerida": "Completar con una causa técnica o de gestión validable.",
                    "justificacion_tecnica": "Nivel agregado manualmente; requiere análisis y validación del equipo investigador.",
                    "evidencia_requerida": "Definir evidencia necesaria para confirmar este nivel.",
                })
            niveles_editados = []
            for indice_nivel, nivel in enumerate(niveles_originales[:cantidad_niveles]):
                with st.container(border=True):
                    st.markdown(f"**Nivel {nivel['nivel']}**")
                    pregunta = st.text_area(
                        "Pregunta causal",
                        value=nivel["pregunta"],
                        key=f"preg_{indice_cadena}_{indice_nivel}", height=65,
                    )
                    respuesta = st.text_area(
                        "Respuesta técnica editable",
                        value=nivel["respuesta_sugerida"],
                        key=f"resp_{indice_cadena}_{indice_nivel}", height=85,
                        help="Redáctala como afirmación técnica. Evita comenzar con 'porque'.",
                    )
                    justificacion = st.text_area(
                        "Ayuda / justificación técnica de la IA",
                        value=nivel["justificacion_tecnica"],
                        key=f"just_{indice_cadena}_{indice_nivel}", height=90,
                    )
                    evidencia = st.text_area(
                        "Evidencia necesaria para validarlo",
                        value=nivel["evidencia_requerida"],
                        key=f"evid_{indice_cadena}_{indice_nivel}", height=70,
                    )
                    niveles_editados.append({
                        "nivel": nivel["nivel"],
                        "pregunta": pregunta.strip(),
                        "respuesta": respuesta.strip(),
                        "justificacion": justificacion.strip(),
                        "evidencia": evidencia.strip(),
                    })
            causa_raiz = st.text_area(
                "Causa raíz preliminar",
                value=cadena.get("causa_raiz_preliminar", ""),
                key=f"raiz_{indice_cadena}", height=85,
            )
            cadenas_editadas.append({
                "causa": cadena["causa"],
                "niveles": niveles_editados,
                "causa_raiz_preliminar": causa_raiz.strip(),
            })

        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver a causas", use_container_width=True)
        continuar = c2.form_submit_button(
            "Revisar planes preventivos →", type="primary", use_container_width=True,
        )

    if volver:
        avanzar(4)
    if continuar:
        for cadena in cadenas_editadas:
            if len(cadena["niveles"]) < 3:
                st.error("Cada cadena debe contener al menos 3 niveles causales.")
                return
            if any(len(nivel["respuesta"]) < 8 for nivel in cadena["niveles"]):
                st.error("Todas las respuestas causales deben quedar suficientemente desarrolladas.")
                return
        datos["cadenas_causales"] = cadenas_editadas
        avanzar(6)


def paso_planes() -> None:
    encabezado(
        "Planes de prevención",
        "Ajusta acciones, responsables, plazos y evidencias antes del informe.",
    )
    datos = st.session_state.nuevo_adf
    indicador_consumo()
    acciones = datos["profundizacion"].get("plan_prevencion", [])

    with st.form("form_planes"):
        acciones_editadas = []
        for indice, accion in enumerate(acciones):
            with st.expander(f"Acción {indice + 1}", expanded=True):
                texto = st.text_area("Acción", value=accion["accion"], key=f"accion_{indice}")
                objetivo = st.text_area("Objetivo", value=accion["objetivo"], key=f"obj_{indice}")
                relacion = st.text_area(
                    "Relación con la causa", value=accion["relacion_con_causa"],
                    key=f"rel_{indice}",
                )
                responsable = st.text_input(
                    "Responsable", value=accion.get("responsable_sugerido", "Por definir"),
                    key=f"resp_plan_{indice}",
                )
                plazo = st.text_input(
                    "Plazo", value=accion.get("plazo_sugerido", "Por definir"),
                    key=f"plazo_{indice}",
                )
                evidencia = st.text_area(
                    "Evidencia de implementación",
                    value=accion["evidencia_de_implementacion"], key=f"evid_plan_{indice}",
                )
                acciones_editadas.append({
                    "accion": texto.strip(),
                    "objetivo": objetivo.strip(),
                    "relacion_con_causa": relacion.strip(),
                    "responsable_sugerido": responsable.strip(),
                    "plazo_sugerido": plazo.strip(),
                    "evidencia_de_implementacion": evidencia.strip(),
                })

        st.subheader("Imagen de la falla")
        archivo = st.file_uploader(
            "Adjunta una fotografía para incorporarla al PDF",
            type=["png", "jpg", "jpeg"],
            help="Si no adjuntas una imagen, el informe dejará un espacio reservado.",
        )
        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver a 5 Porqués", use_container_width=True)
        generar = c2.form_submit_button(
            "Generar redacción final con IA →", type="primary", use_container_width=True,
        )

    if volver:
        avanzar(5)
    if generar:
        validas = [a for a in acciones_editadas if a["accion"] and a["relacion_con_causa"]]
        if not validas:
            st.error("Debe existir al menos una acción preventiva válida.")
            return
        datos["plan_prevencion"] = validas
        if archivo is not None:
            datos["imagen_falla"] = archivo.getvalue()

        contexto = json.dumps({
            "area": datos["area"],
            "equipo": datos["equipo"],
            "aviso_sap": datos["aviso_sap"],
            "relato_original": datos["relato_original"],
            "hechos_confirmados": datos["diagnostico"]["hechos_confirmados"],
            "efecto": datos["efecto"],
            "principio_funcionamiento": datos["principio_funcionamiento"],
            "ishikawa_validado": datos["ishikawa_validado"],
            "cadenas_causales": datos["cadenas_causales"],
            "plan_prevencion": datos["plan_prevencion"],
        }, ensure_ascii=False, indent=2)
        try:
            with st.spinner("GearBot está redactando el informe final..."):
                informe = generar_informe_final(contexto)
            datos["informe_final"] = informe.model_dump()
            datos["solicitudes_ia"] = 4
            avanzar(7)
        except Exception as error:
            mostrar_error_ia(error)


def paso_informe() -> None:
    encabezado(
        "Resumen preliminar del informe",
        "Cuarta llamada completada. Revisa y edita la propuesta antes de guardar y generar el PDF.",
    )
    datos = st.session_state.nuevo_adf
    informe = datos["informe_final"]
    indicador_consumo()

    with st.form("form_informe"):
        titulo = st.text_input("Título", value=informe["titulo"])
        resumen = st.text_area("Resumen ejecutivo", value=informe["resumen_ejecutivo"], height=150)
        descripcion = st.text_area("Descripción del evento", value=informe["descripcion_evento"], height=160)
        principio = st.text_area("Principio de funcionamiento", value=informe["principio_funcionamiento"], height=180)
        fenomeno = st.text_area("Fenómeno investigado", value=informe["fenomeno_investigado"], height=100)
        sintesis = st.text_area("Síntesis Ishikawa", value=informe["sintesis_ishikawa"], height=140)
        conclusion = st.text_area("Conclusión técnica", value=informe["conclusion_tecnica"], height=210)
        leccion = st.text_area("Lección aprendida", value=informe["leccion_aprendida"], height=110)
        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver a planes", use_container_width=True)
        guardar = c2.form_submit_button(
            "Guardar ADF y preparar PDF →", type="primary", use_container_width=True,
        )

    if volver:
        avanzar(6)
    if guardar:
        if len(conclusion.strip()) < 30:
            st.error("La conclusión necesita mayor desarrollo.")
            return
        informe_editado = {
            **informe,
            "titulo": titulo.strip(),
            "resumen_ejecutivo": resumen.strip(),
            "descripcion_evento": descripcion.strip(),
            "principio_funcionamiento": principio.strip(),
            "fenomeno_investigado": fenomeno.strip(),
            "sintesis_ishikawa": sintesis.strip(),
            "conclusion_tecnica": conclusion.strip(),
            "leccion_aprendida": leccion.strip(),
        }
        datos["informe_final"] = informe_editado
        adf_id = guardar_adf({
            "creado_por": st.session_state.usuario,
            "estado": "Borrador",
            "etapa": "Informe PDF",
            "area": datos["area"],
            "equipo": datos["equipo"],
            "aviso_sap": datos["aviso_sap"],
            "relato_original": datos["relato_original"],
            "analisis_ia": json.dumps(datos["diagnostico"], ensure_ascii=False),
            "efecto": datos["efecto"],
            "investigacion_web": datos["principio_funcionamiento"],
            "fuentes_web": json.dumps([], ensure_ascii=False),
            "ishikawa": json.dumps(datos["ishikawa_validado"], ensure_ascii=False),
            "causas_priorizadas": json.dumps(datos["causas_priorizadas"], ensure_ascii=False),
            "cadenas_causales": json.dumps(datos["cadenas_causales"], ensure_ascii=False),
            "conclusion": conclusion.strip(),
            "plan_prevencion": json.dumps(datos["plan_prevencion"], ensure_ascii=False),
            "leccion_aprendida": leccion.strip(),
        })
        datos["id_guardado"] = adf_id
        pdf_datos = {
            **informe_editado,
            "creado_por": st.session_state.usuario,
            "area": datos["area"],
            "equipo": datos["equipo"],
            "aviso_sap": datos["aviso_sap"],
            "relato_original": datos["relato_original"],
            "efecto": datos["efecto"],
            "ishikawa_validado": datos["ishikawa_validado"],
            "cadenas_causales": datos["cadenas_causales"],
            "plan_prevencion": datos["plan_prevencion"],
        }
        datos["pdf_bytes"] = generar_pdf_adf(pdf_datos, datos.get("imagen_falla"))
        avanzar(8)


def paso_pdf() -> None:
    encabezado(
        "Informe PDF preparado",
        "El documento incluye imagen o espacio reservado, principio de funcionamiento, Ishikawa, 5 Porqués y planes.",
    )
    datos = st.session_state.nuevo_adf
    st.success(f"ADF #{datos['id_guardado']} guardado correctamente.")
    nombre = f"ADF_{datos['equipo'].replace(' ', '_')}_{datos['id_guardado']}.pdf"
    st.download_button(
        "Descargar informe PDF",
        data=datos["pdf_bytes"],
        file_name=nombre,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    if st.button("Ver resumen final →", use_container_width=True):
        avanzar(9)


def paso_final() -> None:
    datos = st.session_state.nuevo_adf
    encabezado(
        "RootMine v3.0 completado",
        "El análisis quedó guardado y disponible para la memoria técnica.",
    )
    st.write(f"**Equipo:** {datos['equipo']}")
    st.write(f"**Fenómeno:** {datos['efecto']}")
    st.write(f"**Solicitudes IA:** {datos['solicitudes_ia']}")
    st.info(
        "Las causas y la causa raíz deben considerarse preliminares hasta que la evidencia de terreno sea revisada y aprobada."
    )
    if st.button("Crear otro ADF", type="primary", use_container_width=True):
        st.session_state.pop("nuevo_adf", None)
        st.rerun()


def mostrar_nuevo_adf() -> None:
    inicializar()
    paso = st.session_state.nuevo_adf["paso"]
    st.markdown(
        f'<div class="step-chip">RootMine v3.0 · Etapa {paso} de {TOTAL_ETAPAS}</div>',
        unsafe_allow_html=True,
    )
    st.progress(paso / TOTAL_ETAPAS)
    funciones = {
        1: paso_relato,
        2: paso_diagnostico,
        3: paso_ishikawa,
        4: paso_priorizacion,
        5: paso_causal,
        6: paso_planes,
        7: paso_informe,
        8: paso_pdf,
        9: paso_final,
    }
    funciones[paso]()
