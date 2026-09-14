import json
from datetime import date, datetime

import streamlit as st

from database.conocimiento import buscar_casos_similares, formatear_contexto_casos
from database.repositorio_adf import (
    guardar_adf, actualizar_adf, guardar_pdf_adf, obtener_adf, registrar_envio_validacion,
    guardar_borrador_adf, cargar_borrador_adf, actualizar_contenido_borrador,
    buscar_borrador_coincidente, resolver_devolucion_jefatura,
)
from ia.cliente import (mensaje_amigable_ia,
    generar_cadenas_y_planes,
    generar_diagnostico,
    generar_informe_final,
    generar_ishikawa,
)
from modulos.diagrama_ishikawa import mostrar_ishikawa
from reportes.pdf_adf import generar_pdf_adf
from database.usuarios import resolver_supervisor, resolver_jefe


AREAS = [
    "Faena", "Procesos", "Congelado", "Elaborados", "ADM / Despacho",
    "Servicios", "Generación", "SADEMA", "Otra",
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


def descripcion_equipo_para_redaccion(texto: str) -> str:
    """Normaliza solo la narrativa: conserva el valor original en la base."""
    limpio = " ".join((texto or "").strip().split())
    letras = [c for c in limpio if c.isalpha()]
    if letras and all(c.isupper() for c in letras):
        return limpio.lower()
    return limpio




def inicializar() -> None:
    if "nuevo_adf" not in st.session_state:
        usuario = st.session_state.get("usuario_actual") or {}
        st.session_state.nuevo_adf = {
            "paso": 1,
            "centro": str(usuario.get("centro", "")).strip(),
            "planta": str(usuario.get("planta", "")).strip(),
            "area": "",
            "numero_equipo": "",
            "equipo": "",
            "aviso_sap": "",
            "tiempo_perdido_h": 0.0,
            "relato_original": "",
            "casos_similares": [],
            "antecedentes_reincidencia": [],
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
            "_revision_etapas": {},
            "_informe_desactualizado": False,
            "imagen_falla": None,
            "imagen_equipo": None,
            "imagen_componente": None,
            "pdf_bytes": None,
            "solicitudes_ia": 0,
            "id_guardado": None,
            "id_edicion": None,
            "estado_validacion": "Borrador",
        }


def _json_campo(texto, defecto):
    try:
        valor = json.loads(texto or "")
        return valor if valor is not None else defecto
    except (TypeError, ValueError, json.JSONDecodeError):
        return defecto


def _datos_edicion_desde_adf(adf, usuario: dict) -> dict:
    """Reconstruye el análisis existente para editar el MISMO ADF sin perder contenido."""
    snapshot = _json_campo(getattr(adf, "borrador_json", ""), {})
    if not isinstance(snapshot, dict):
        snapshot = {}

    diagnostico = snapshot.get("diagnostico") or _json_campo(adf.analisis_ia, {})
    ishikawa_validado = snapshot.get("ishikawa_validado") or _json_campo(adf.ishikawa, {})
    ishikawa_ia = snapshot.get("ishikawa_ia")
    if not ishikawa_ia and isinstance(ishikawa_validado, dict):
        # Respaldo para ADF antiguos cuyo borrador no conservó la propuesta original de IA.
        ishikawa_ia = {"resumen_tecnico": "Ishikawa recuperado desde el ADF guardado.", "advertencias": []}
        for categoria, clave in CATEGORIAS.items():
            ishikawa_ia[clave] = list(ishikawa_validado.get(categoria, []) or [])

    causas = snapshot.get("causas_priorizadas") or _json_campo(adf.causas_priorizadas, [])
    cadenas = snapshot.get("cadenas_causales") or _json_campo(adf.cadenas_causales, [])
    planes = snapshot.get("plan_prevencion") or _json_campo(adf.plan_prevencion, [])

    informe = snapshot.get("informe_final")
    if not isinstance(informe, dict) or not informe:
        informe = {
            "titulo": f"ADF · {adf.equipo or 'Equipo'}",
            "resumen_ejecutivo": adf.conclusion or adf.efecto or "",
            "descripcion_evento": adf.relato_original or "",
            "principio_funcionamiento": adf.investigacion_web or "",
            "fenomeno_investigado": adf.efecto or "",
            "sintesis_ishikawa": "Análisis Ishikawa recuperado desde el registro existente.",
            "conclusion_tecnica": adf.conclusion or "",
            "leccion_aprendida": adf.leccion_aprendida or "",
        }

    base = {
        "paso": 1,
        "centro": adf.centro or str(usuario.get("centro", "")).strip(),
        "planta": adf.planta or str(usuario.get("planta", "")).strip(),
        "area": adf.area or "",
        "numero_equipo": adf.numero_equipo or "",
        "equipo": adf.equipo or "",
        "aviso_sap": adf.aviso_sap or "",
        "tiempo_perdido_h": float(getattr(adf, "tiempo_perdido_h", 0) or 0),
        "relato_original": adf.relato_original or "",
        "casos_similares": snapshot.get("casos_similares", []),
        "antecedentes_reincidencia": snapshot.get("antecedentes_reincidencia", []),
        "diagnostico": diagnostico,
        "efecto": adf.efecto or snapshot.get("efecto", ""),
        "principio_funcionamiento": adf.investigacion_web or snapshot.get("principio_funcionamiento", ""),
        "ishikawa_ia": ishikawa_ia,
        "ishikawa_validado": ishikawa_validado,
        "causas_priorizadas": causas,
        "profundizacion": snapshot.get("profundizacion"),
        "cadenas_causales": cadenas,
        "plan_prevencion": planes,
        "informe_final": informe,
        "_revision_etapas": snapshot.get("_revision_etapas", {}),
        "_informe_desactualizado": bool(snapshot.get("_informe_desactualizado", False)),
        # Las imágenes históricas no siempre están disponibles como bytes en el snapshot.
        # Se conservan las nuevas que el usuario adjunte durante la corrección.
        "imagen_falla": None,
        "imagen_equipo": None,
        "imagen_componente": None,
        "pdf_bytes": getattr(adf, "pdf_archivo", None),
        "solicitudes_ia": int(snapshot.get("solicitudes_ia", 0) or 0),
        "id_guardado": adf.id,
        "id_edicion": adf.id,
        "estado_validacion": adf.estado,
        "comentario_rechazo": adf.comentario_validacion or "",
        "_creado_por_original": adf.creado_por or "",
        "_creado_por_email_original": adf.creado_por_email or "",
        "_max_paso_alcanzado": 8,
    }
    return base


def cargar_adf_para_correccion(adf_id: int) -> bool:
    """Carga un ADF rechazado por Supervisor para que su creador lo corrija y reenvíe."""
    adf = obtener_adf(adf_id)
    usuario = st.session_state.get("usuario_actual") or {}
    if not adf:
        return False
    correo = (usuario.get("correo") or "").lower().strip()
    if (adf.creado_por_email or "").lower().strip() != correo:
        return False
    if adf.estado not in {"Requiere corrección", "Rechazado"}:
        return False

    datos = _datos_edicion_desde_adf(adf, usuario)
    datos["paso"] = 1
    st.session_state.nuevo_adf = datos
    st.session_state.pagina = "📝 RootMine · Nuevo ADF"
    return True


def cargar_adf_devuelto_jefatura_para_correccion(adf_id: int) -> bool:
    """Abre un ADF devuelto por Jefatura para corrección directa del Supervisor.

    Conserva ID, creador, validaciones previas y observación de Jefatura. El ADF no
    vuelve a pasar por una segunda aprobación de Supervisor: tras corregir se reenvía
    directamente a Jefatura.
    """
    adf = obtener_adf(adf_id)
    usuario = st.session_state.get("usuario_actual") or {}
    if not adf or adf.estado != "Devuelto por Jefatura":
        return False

    correo = (usuario.get("correo") or "").lower().strip()
    centro_usuario = str(usuario.get("centro", "") or "").strip()
    es_supervisor_asignado = correo == (adf.supervisor_email or "").lower().strip()
    es_admin_mismo_centro = bool(usuario.get("es_admin", False)) and centro_usuario == str(adf.centro or "").strip()
    if not (es_supervisor_asignado or es_admin_mismo_centro):
        return False

    datos = _datos_edicion_desde_adf(adf, usuario)
    # Abrimos en PDF / envío para que el Supervisor pueda saltar a cualquier etapa anterior.
    datos["paso"] = 8
    datos["_correccion_jefatura"] = True
    datos["_editor_correccion_email"] = correo
    datos["_observacion_jefatura"] = adf.comentario_validacion or ""
    datos["estado_validacion"] = "Devuelto por Jefatura"
    st.session_state.nuevo_adf = datos
    st.session_state.pagina = "📝 RootMine · Nuevo ADF"
    return True


def cargar_borrador_para_continuar(adf_id: int) -> bool:
    usuario = st.session_state.get("usuario_actual") or {}
    recuperado = cargar_borrador_adf(adf_id, usuario.get("correo", ""))
    if not recuperado:
        return False
    base = {
        "paso": 1, "centro": str(usuario.get("centro", "")).strip(), "planta": str(usuario.get("planta", "")).strip(),
        "area": "", "numero_equipo": "", "equipo": "", "aviso_sap": "", "tiempo_perdido_h": 0.0,
        "relato_original": "", "casos_similares": [], "antecedentes_reincidencia": [], "diagnostico": None, "efecto": "",
        "principio_funcionamiento": "", "ishikawa_ia": None, "ishikawa_validado": {},
        "causas_priorizadas": [], "profundizacion": None, "cadenas_causales": [], "plan_prevencion": [],
        "informe_final": None,
            "_revision_etapas": {},
            "_informe_desactualizado": False, "imagen_falla": None, "imagen_equipo": None, "imagen_componente": None,
        "pdf_bytes": None, "solicitudes_ia": 0, "id_guardado": adf_id, "id_edicion": None,
        "estado_validacion": "Borrador",
    }
    base.update(recuperado)
    base["id_guardado"] = adf_id
    base["id_edicion"] = None

    # Un ADF que sigue siendo Borrador no debe quedar atrapado en el Resumen final.
    # Si fue guardado en paso 9 sin enviarse a validación, se retoma en PDF / envío
    # para continuar el MISMO ADF y conservar su ID.
    if (base.get("estado_validacion") or "Borrador") == "Borrador" and int(base.get("paso") or 1) >= 9:
        base["paso"] = 8
        base["_retomado_desde_resumen"] = True

    st.session_state.nuevo_adf = base
    st.session_state.pagina = "📝 RootMine · Nuevo ADF"
    return True


def _guardar_avance(paso_destino: int) -> bool:
    datos = st.session_state.get("nuevo_adf") or {}
    if not (datos.get("relato_original") or datos.get("equipo") or datos.get("id_guardado") or datos.get("id_edicion")):
        return True
    try:
        usuario = st.session_state.get("usuario_actual") or {}
        adf_id = guardar_borrador_adf(datos, usuario, paso_destino)
        datos["id_guardado"] = adf_id
        datos["paso"] = paso_destino
        return True
    except Exception as exc:
        st.error(f"No fue posible guardar el avance del ADF: {exc}")
        st.caption("RootMine no avanzará de etapa hasta confirmar que el borrador quedó guardado.")
        return False


def avanzar(paso: int) -> None:
    datos = st.session_state.nuevo_adf
    datos["_max_paso_alcanzado"] = max(int(datos.get("_max_paso_alcanzado", 1)), int(paso))
    if not _guardar_avance(paso):
        return
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
    amigable = mensaje_amigable_ia(error)
    if amigable:
        st.warning(amigable)
        st.caption("Tu ADF y el avance realizado siguen guardados; puedes continuar cuando GearBot vuelva a estar disponible.")
        return
    st.error(f"No fue posible completar la operación de IA: {error}")
    st.caption("Revisa la conexión a internet o intenta nuevamente en unos minutos.")


def indicador_consumo() -> None:
    solicitudes = st.session_state.nuevo_adf.get("solicitudes_ia", 0)
    st.caption(f"Solicitudes IA utilizadas en este ADF: {solicitudes}. Las actualizaciones inteligentes solo se ejecutan cuando detectan cambios guardados.")



ETAPAS_NAVEGABLES = {
    1: "1 · Contexto y evidencias",
    2: "2 · Diagnóstico",
    3: "3 · Ishikawa 6M",
    4: "4 · Priorización de causas",
    5: "5 · 5 Porqués",
    6: "6 · Planes de prevención",
    7: "7 · Informe técnico",
    8: "8 · PDF / envío",
}


def _serializable(valor) -> str:
    try:
        return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(valor)


def _cambio_real(anterior, nuevo) -> bool:
    return _serializable(anterior) != _serializable(nuevo)


def _marcar_cambio_desde(etapa: int) -> None:
    """Registra que una etapa fue editada y que todo lo posterior debe reconstruirse."""
    datos = st.session_state.nuevo_adf
    revision = datos.setdefault("_revision_etapas", {})
    revision[str(etapa)] = "Modificado por investigador"
    for posterior in range(etapa + 1, 8):
        revision[str(posterior)] = "Requiere actualización"
    if etapa <= 6:
        datos["_informe_desactualizado"] = True


def _contexto_vivo(datos: dict) -> str:
    """Fuente única para GearBot: siempre usa el estado actualmente validado/editado."""
    diagnostico = datos.get("diagnostico") or {}
    return json.dumps({
        "instruccion": (
            "Usa como fuente de verdad los datos validados/editados por el investigador. "
            "Si difieren de una propuesta anterior de IA, prevalece siempre la edición humana. "
            "No inventes información ausente. Si el investigador modificó una cadena causal, "
            "conserva el significado técnico de su edición y mejora solo coherencia, continuidad y redacción."
        ),
        "centro": datos.get("centro", ""),
        "planta": datos.get("planta", ""),
        "area": datos.get("area", ""),
        "numero_equipo": datos.get("numero_equipo", ""),
        "equipo": descripcion_equipo_para_redaccion(datos.get("equipo", "")),
        "aviso_sap": datos.get("aviso_sap", ""),
        "tiempo_perdido_h": datos.get("tiempo_perdido_h", 0.0),
        "relato_original": datos.get("relato_original", ""),
        "diagnostico_validado": diagnostico,
        "efecto_validado": datos.get("efecto", ""),
        "principio_funcionamiento_validado": datos.get("principio_funcionamiento", ""),
        "ishikawa_validado": datos.get("ishikawa_validado", {}),
        "causas_priorizadas": datos.get("causas_priorizadas", []),
        "cadenas_causales_validadas": datos.get("cadenas_causales", []),
        "planes_validados": datos.get("plan_prevencion", []),
    }, ensure_ascii=False, indent=2)


def _navegacion_retroceso_form(actual: int):
    """Selector DENTRO del formulario: al enviar también viajan todos los cambios de pantalla."""
    anteriores = [n for n in ETAPAS_NAVEGABLES if n < actual]
    if not anteriores:
        return None, False
    st.markdown("---")
    st.caption("🧭 Navegación segura · RootMine guardará primero lo que acabas de editar.")
    etiquetas = [ETAPAS_NAVEGABLES[n] for n in reversed(anteriores)]
    seleccion = st.selectbox(
        "¿A qué etapa anterior quieres volver?",
        etiquetas,
        key=f"destino_seguro_{actual}",
    )
    destino = next(n for n, etiqueta in ETAPAS_NAVEGABLES.items() if etiqueta == seleccion)
    viajar = st.form_submit_button(
        "💾 Guardar cambios e ir a la etapa seleccionada",
        use_container_width=True,
        key=f"viajar_guardando_{actual}",
    )
    return destino, viajar


def _barra_navegacion_etapas() -> None:
    """En etapas editables evita saltos que podrían descartar campos aún no enviados."""
    datos = st.session_state.nuevo_adf
    actual = int(datos.get("paso", 1))
    max_alcanzado = int(datos.get("_max_paso_alcanzado", actual))
    datos["_max_paso_alcanzado"] = max(max_alcanzado, actual)
    if 1 <= actual <= 7:
        st.caption("🧭 En las etapas editables RootMine evita saltos directos que puedan perder datos. Para retroceder usa **Navegación segura** al final de la etapa.")
        return
    disponibles = [n for n in ETAPAS_NAVEGABLES if n <= max(datos["_max_paso_alcanzado"], actual)]
    if len(disponibles) <= 1:
        return
    opciones = {ETAPAS_NAVEGABLES[n]: n for n in disponibles}
    actual_label = ETAPAS_NAVEGABLES.get(actual, ETAPAS_NAVEGABLES[disponibles[-1]])
    elegido = st.selectbox(
        "🧭 Ir directamente a una etapa",
        list(opciones),
        index=list(opciones).index(actual_label) if actual_label in opciones else 0,
        key=f"nav_etapa_{actual}",
    )
    destino = opciones[elegido]
    if destino != actual and st.button("Ir a la etapa seleccionada", use_container_width=True, key=f"ir_etapa_{actual}_{destino}"):
        if _guardar_avance(destino):
            datos["paso"] = destino
            st.rerun()


def _aviso_analisis_vivo() -> None:
    datos = st.session_state.nuevo_adf
    revision = datos.get("_revision_etapas", {})
    pendientes = [ETAPAS_NAVEGABLES.get(int(k), k) for k,v in revision.items() if v == "Requiere actualización" and str(k).isdigit()]
    if datos.get("_informe_desactualizado") or pendientes:
        st.info(
            "🧠 **Análisis vivo activo:** RootMine detectó cambios guardados. "
            "GearBot actualizará automáticamente cada etapa dependiente cuando vuelvas a entrar en ella, "
            "usando siempre tu última versión como fuente de verdad."
        )
    if pendientes:
        st.caption("Pendientes de refresh inteligente: " + " · ".join(pendientes))


def _limpiar_widgets(prefijos: tuple[str, ...]) -> None:
    for clave in list(st.session_state.keys()):
        if any(str(clave).startswith(prefijo) for prefijo in prefijos):
            st.session_state.pop(clave, None)


def _cadenas_modelo_a_validadas(profundizacion: dict) -> list[dict]:
    salida = []
    for cadena in (profundizacion or {}).get("cadenas", []):
        niveles = []
        for nivel in cadena.get("niveles", []):
            niveles.append({
                "nivel": nivel.get("nivel"),
                "pregunta": (nivel.get("pregunta") or "").strip(),
                "respuesta": (nivel.get("respuesta_sugerida") or "").strip(),
                "justificacion": (nivel.get("justificacion_tecnica") or "").strip(),
                "evidencia": (nivel.get("evidencia_requerida") or "").strip(),
            })
        salida.append({
            "causa": (cadena.get("causa") or "").strip(),
            "niveles": niveles,
            "causa_raiz_preliminar": (cadena.get("causa_raiz_preliminar") or "").strip(),
        })
    return salida


def _auto_refrescar_ishikawa(datos: dict) -> None:
    revision = datos.setdefault("_revision_etapas", {})
    if revision.get("3") != "Requiere actualización":
        return
    try:
        with st.spinner("🧠 GearBot está actualizando el Ishikawa con tus últimos cambios..."):
            ishikawa = generar_ishikawa(
                area=datos["area"],
                equipo=descripcion_equipo_para_redaccion(datos["equipo"]),
                relato=datos["relato_original"],
                fenomeno=datos["efecto"],
                principio_funcionamiento=datos["principio_funcionamiento"],
                hechos=(datos.get("diagnostico") or {}).get("hechos_confirmados", []),
            )
        datos["ishikawa_ia"] = ishikawa.model_dump()
        revision["3"] = "Actualizado por GearBot"
        datos["solicitudes_ia"] = int(datos.get("solicitudes_ia", 0)) + 1
        _limpiar_widgets(("inc_", "mec_", "extra_causa_", "cantidad_extra_"))
        st.success("✅ Ishikawa actualizado automáticamente a partir de la última información guardada.")
    except Exception as error:
        mostrar_error_ia(error)


def _auto_refrescar_cadenas(datos: dict) -> None:
    revision = datos.setdefault("_revision_etapas", {})
    if revision.get("5") != "Requiere actualización":
        return
    causas = list(datos.get("causas_priorizadas") or [])
    if not causas:
        return
    try:
        with st.spinner("🧠 GearBot está reconstruyendo los 5 Porqués con tus cambios..."):
            resultado = generar_cadenas_y_planes(
                efecto=datos["efecto"],
                principio_funcionamiento=datos["principio_funcionamiento"],
                causas_seleccionadas=causas,
                contexto_validado=(
                    "RECALCULO AUTOMÁTICO. Usa únicamente la última versión guardada por el investigador. "
                    "Alinea cada pregunta con la respuesta anterior y evita saltos lógicos.\n" + _contexto_vivo(datos)
                ),
            )
        datos["profundizacion"] = resultado.model_dump()
        datos["cadenas_causales"] = []
        datos["plan_prevencion"] = []
        revision["5"] = "Actualizado por GearBot"
        revision["6"] = "Requiere actualización"
        datos["solicitudes_ia"] = int(datos.get("solicitudes_ia", 0)) + 1
        _limpiar_widgets(("preg_", "resp_", "just_", "evid_", "raiz_", "cantidad_niveles_"))
        st.success("✅ Los 5 Porqués fueron recalculados automáticamente con el análisis actualizado.")
    except Exception as error:
        mostrar_error_ia(error)


def _auto_refrescar_desde_5porques(datos: dict) -> None:
    """Si el investigador editó la cadena, GearBot armoniza redacción y rehace los planes dependientes."""
    revision = datos.setdefault("_revision_etapas", {})
    if revision.get("6") != "Requiere actualización" or not datos.get("cadenas_causales"):
        return
    causas = list(datos.get("causas_priorizadas") or [])
    if not causas:
        return
    try:
        with st.spinner("🧠 GearBot está revisando la coherencia de los 5 Porqués y actualizando los planes..."):
            resultado = generar_cadenas_y_planes(
                efecto=datos["efecto"],
                principio_funcionamiento=datos["principio_funcionamiento"],
                causas_seleccionadas=causas,
                contexto_validado=(
                    "REFRESH DESPUÉS DE EDICIÓN HUMANA. Las cadenas causales incluidas en el contexto fueron editadas "
                    "por el investigador y son la fuente de verdad. Conserva sus hechos y significado técnico. "
                    "Mejora la continuidad pregunta-respuesta, la redacción y la causa raíz solo cuando sea necesario; "
                    "no inventes hechos. Luego genera planes coherentes con esa versión corregida.\n" + _contexto_vivo(datos)
                ),
            )
        datos["profundizacion"] = resultado.model_dump()
        refinadas = _cadenas_modelo_a_validadas(datos["profundizacion"])
        if refinadas:
            datos["cadenas_causales"] = refinadas
        datos["plan_prevencion"] = []
        revision["5"] = "Revisado por GearBot tras edición"
        revision["6"] = "Actualizado por GearBot"
        revision["7"] = "Requiere actualización"
        datos["_informe_desactualizado"] = True
        datos["solicitudes_ia"] = int(datos.get("solicitudes_ia", 0)) + 1
        _limpiar_widgets(("accion_", "obj_", "rel_", "resp_plan_", "fecha_plan_", "evid_plan_"))
        st.success("✅ GearBot conservó tus cambios como base, revisó la coherencia del 5 Porqués y actualizó los planes sugeridos.")
    except Exception as error:
        mostrar_error_ia(error)


def _auto_refrescar_informe(datos: dict) -> None:
    revision = datos.setdefault("_revision_etapas", {})
    if not (datos.get("_informe_desactualizado") or revision.get("7") == "Requiere actualización"):
        return
    try:
        with st.spinner("🧠 GearBot está actualizando automáticamente la redacción final..."):
            actualizado = generar_informe_final(_contexto_vivo(datos))
        datos["informe_final"] = actualizado.model_dump()
        datos["_informe_desactualizado"] = False
        revision["7"] = "Actualizado por GearBot"
        datos["solicitudes_ia"] = int(datos.get("solicitudes_ia", 0)) + 1
        st.success("✅ Informe actualizado automáticamente con la última versión del análisis.")
    except Exception as error:
        mostrar_error_ia(error)


def paso_relato() -> None:
    encabezado(
        "Contexto inicial de la falla",
        "Primera llamada: comprensión del evento, fenómeno y principio de funcionamiento.",
    )
    datos = st.session_state.nuevo_adf
    opciones = ["Seleccione un área"] + AREAS
    if datos.get("id_edicion"):
        st.warning(
            f"🛠️ Estás corrigiendo el ADF #{datos['id_edicion']} rechazado. "
            f"Observación del validador: {datos.get('comentario_rechazo') or 'Sin comentario registrado'}"
        )

    with st.form("form_relato", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            centro_etiqueta = f"{datos.get('centro','')} - {datos.get('planta','')}".strip(" -")
            st.text_input(
                "Centro / Planta *",
                value=centro_etiqueta,
                disabled=True,
                help="El centro se obtiene automáticamente desde el maestro de usuarios y no se selecciona manualmente.",
            )
            centro = datos.get("centro", "")
        with c2:
            area = st.selectbox(
                "Área *", opciones,
                index=opciones.index(datos["area"]) if datos["area"] else 0,
            )
        c3, c4 = st.columns(2)
        with c3:
            numero_equipo = st.text_input(
                "N° de Equipo *",
                value=datos["numero_equipo"],
                placeholder="Ejemplo: 100245 o EQ-100245",
                help="Código o número único con que el activo se identifica en la planta/SAP.",
            )
        with c4:
            equipo = st.text_input(
                "Descripción del equipo *",
                value=datos["equipo"],
                placeholder="Ejemplo: Evisceradora Novamax",
            )
        c5, c6 = st.columns(2)
        with c5:
            aviso = st.text_input("Aviso SAP", value=datos["aviso_sap"], placeholder="Opcional")
        with c6:
            tiempo_perdido_h = st.number_input(
                "Tiempo perdido analizado (h)", min_value=0.0, value=float(datos.get("tiempo_perdido_h", 0.0) or 0.0), step=0.1,
                help="Horas de detención o tiempo perdido atribuible al evento analizado."
            )
        relato = st.text_area(
            "Relato original", value=datos["relato_original"], height=260,
            placeholder="Describe alarma, condición encontrada, intervención y resultado.",
        )
        st.markdown("#### Evidencia inicial de la falla")
        archivo_falla = st.file_uploader(
            "Imagen de la falla (opcional)",
            type=["png", "jpg", "jpeg"],
            key="imagen_falla_inicio",
            help="Adjunta la evidencia principal del problema. Esta imagen aparecerá junto a la descripción del evento en el informe.",
        )
        if archivo_falla is not None:
            st.image(archivo_falla, caption="Vista previa · Evidencia de la falla", width=420)
        elif datos.get("imagen_falla"):
            st.image(datos["imagen_falla"], caption="Imagen de falla cargada", width=420)
        enviar = st.form_submit_button(
            "Analizar contexto con IA →", type="primary", use_container_width=True,
        )

    if not enviar:
        return
    if len(centro.strip()) < 2:
        st.error("Tu usuario no tiene un Centro configurado en el maestro. Contacta al administrador de RootMine.")
        return
    if area == "Seleccione un área":
        st.error("Selecciona el área.")
        return
    if len(numero_equipo.strip()) < 2:
        st.error("Ingresa el N° de Equipo.")
        return
    if len(equipo.strip()) < 3:
        st.error("Ingresa la descripción del equipo.")
        return
    if len(relato.strip()) < 20:
        st.error("Describe el evento con un poco más de detalle.")
        return
    if aviso.strip() and not aviso.strip().isdigit():
        st.error("El aviso SAP debe contener solo números.")
        return

    datos.update({
        "centro": centro.strip(),
        "planta": datos.get("planta", "").strip(),
        "area": area,
        "numero_equipo": numero_equipo.strip(),
        "equipo": equipo.strip(),
        "aviso_sap": aviso.strip(),
        "tiempo_perdido_h": float(tiempo_perdido_h),
        "relato_original": relato.strip(),
    })
    if archivo_falla is not None:
        datos["imagen_falla"] = archivo_falla.getvalue()

    usuario_actual = st.session_state.get("usuario_actual") or {}
    borrador_existente = buscar_borrador_coincidente(
        usuario_actual.get("correo", ""),
        numero_equipo=numero_equipo.strip(),
        equipo=equipo.strip(),
        excluir_id=datos.get("id_guardado"),
    )
    casos = buscar_casos_similares(
        centro=centro.strip(),
        numero_equipo=numero_equipo.strip(),
        equipo=equipo.strip(),
        relato=relato.strip(),
    )
    casos = [c for c in casos if int(c.id) != int(datos.get("id_guardado") or -1)]
    # Ya vienen filtrados por el mismo activo desde database.conocimiento.
    # Mostramos hasta 3 como referencia, sin bloquear el flujo.
    casos_relevantes = casos[:3]

    if borrador_existente:
        st.warning(
            f"📝 Ya existe el borrador ADF #{borrador_existente['id']} para "
            f"{borrador_existente['equipo']} (N° {borrador_existente['numero_equipo'] or 's/i'}). "
            f"Última etapa: {borrador_existente['etapa']}."
        )
        b_cont, b_nuevo = st.columns(2)
        if b_cont.button(
            "▶️ Continuar borrador existente",
            key=f"usar_borrador_{borrador_existente['id']}",
            use_container_width=True,
            type="primary",
        ):
            if cargar_borrador_para_continuar(int(borrador_existente["id"])):
                st.rerun()
            st.error("No fue posible recuperar el borrador.")
            return
        continuar_nuevo = b_nuevo.button(
            "➕ Crear un ADF nuevo de todas formas",
            key=f"nuevo_a_pesar_borrador_{borrador_existente['id']}",
            use_container_width=True,
        )
        if not continuar_nuevo:
            return

    antecedentes_seleccionados = []
    if casos_relevantes:
        st.info(
            "🔎 Este equipo tiene ADF anteriores registrados. RootMine los muestra solo como referencia; "
            "puedes continuar normalmente aunque la falla actual sea distinta."
        )

        # Una similitud alta dentro del MISMO activo se trata como posible reincidencia.
        posibles_reincidencias = [c for c in casos_relevantes if c.similitud >= 0.62]
        for caso in casos_relevantes:
            etiqueta = " · 🔁 Posible modo de falla repetitivo" if caso in posibles_reincidencias else ""
            st.write(
                f"**ADF #{caso.id} · {caso.equipo}** — "
                f"{caso.efecto or 'Fenómeno no registrado'}{etiqueta}"
            )
            if caso.conclusion:
                st.caption(f"Conclusión anterior: {caso.conclusion}")

        if posibles_reincidencias:
            st.warning(
                "RootMine detectó uno o más ADF del mismo equipo con un modo de falla suficientemente parecido. "
                "Puedes usar sus conclusiones como antecedente técnico para este NUEVO análisis. "
                "Los planes de acción anteriores no se copiarán."
            )
            opciones = {
                f"ADF #{c.id} · {c.efecto or 'Fenómeno no registrado'}": c
                for c in posibles_reincidencias
            }
            seleccion = st.multiselect(
                "Antecedentes que quieres entregar a GearBot",
                list(opciones.keys()),
                key="antecedentes_reincidencia_sel",
                help=(
                    "GearBot considerará causa/conclusión anterior como referencia, pero deberá volver a validar "
                    "la causa actual y proponer planes nuevos o mejorados."
                ),
            )
            antecedentes_seleccionados = [opciones[x] for x in seleccion]
            if antecedentes_seleccionados:
                st.success(
                    "🧠 GearBot usará las conclusiones seleccionadas como antecedente, "
                    "sin copiar automáticamente sus planes."
                )

        st.caption("Estos antecedentes corresponden al mismo activo y nunca bloquean la creación de un nuevo ADF.")

    try:
        with st.spinner("GearBot está analizando el contexto técnico..."):
            equipo_redaccion = descripcion_equipo_para_redaccion(equipo.strip())
            diagnostico = generar_diagnostico(
                area=f"{area} | Centro: {centro.strip()} - {datos.get('planta','')} | Identificador interno del activo: {numero_equipo.strip()} (no usar como nombre del equipo en la redacción)",
                equipo=equipo_redaccion,
                aviso_sap=aviso.strip(),
                relato=relato.strip(),
                casos_similares=(
                    "POSIBLE REINCIDENCIA DEL MISMO ACTIVO. Usa estas conclusiones únicamente como antecedente; "
                    "valida nuevamente la causa actual y NO copies los planes de acción anteriores. "
                    "Si la falla se repitió, considera explícitamente si los planes previos fueron insuficientes, "
                    "no se ejecutaron o requieren una acción diferente.\n" +
                    formatear_contexto_casos(antecedentes_seleccionados)
                    if antecedentes_seleccionados else ""
                ),
            )
        datos["casos_similares"] = [caso.__dict__ for caso in casos]
        datos["antecedentes_reincidencia"] = [caso.__dict__ for caso in antecedentes_seleccionados]
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

    st.markdown("### Contexto visual del principio de funcionamiento")
    st.caption("Puedes adjuntar una imagen general del equipo y otra del componente que presentó la falla. Se utilizarán solo para contextualizar técnicamente el análisis y el PDF.")
    img1, img2 = st.columns(2)
    with img1:
        archivo_equipo = st.file_uploader(
            "Imagen del equipo (opcional)",
            type=["png", "jpg", "jpeg"],
            key="imagen_equipo_contexto",
        )
        if archivo_equipo is not None:
            datos["imagen_equipo"] = archivo_equipo.getvalue()
        if datos.get("imagen_equipo"):
            st.image(datos["imagen_equipo"], caption="Equipo / conjunto general", use_container_width=True)
    with img2:
        archivo_componente = st.file_uploader(
            "Imagen del componente afectado (opcional)",
            type=["png", "jpg", "jpeg"],
            key="imagen_componente_contexto",
        )
        if archivo_componente is not None:
            datos["imagen_componente"] = archivo_componente.getvalue()
        if datos.get("imagen_componente"):
            st.image(datos["imagen_componente"], caption="Componente asociado a la falla", use_container_width=True)

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
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(2)

    if volver or viajar_seguro:
        nuevo_efecto = efecto.strip()
        nuevo_principio = principio.strip()
        if _cambio_real(datos.get("efecto", ""), nuevo_efecto) or _cambio_real(datos.get("principio_funcionamiento", ""), nuevo_principio):
            datos["efecto"] = nuevo_efecto
            datos["principio_funcionamiento"] = nuevo_principio
            _marcar_cambio_desde(2)
        avanzar(destino_seguro if viajar_seguro else 1)
        return
    if continuar:
        if len(efecto.strip()) < 10:
            st.error("El fenómeno necesita mayor precisión.")
            return
        if len(principio.strip()) < 30:
            st.error("Explica con mayor detalle el principio de funcionamiento.")
            return
        nuevo_efecto = efecto.strip()
        nuevo_principio = principio.strip()
        if _cambio_real(datos.get("efecto", ""), nuevo_efecto) or _cambio_real(datos.get("principio_funcionamiento", ""), nuevo_principio):
            datos["efecto"] = nuevo_efecto
            datos["principio_funcionamiento"] = nuevo_principio
            _marcar_cambio_desde(2)
        else:
            datos["efecto"] = nuevo_efecto
            datos["principio_funcionamiento"] = nuevo_principio
        try:
            with st.spinner("GearBot está construyendo el Ishikawa 6M..."):
                ishikawa = generar_ishikawa(
                    area=datos["area"],
                    equipo=descripcion_equipo_para_redaccion(datos["equipo"]),
                    relato=datos["relato_original"],
                    fenomeno=datos["efecto"],
                    principio_funcionamiento=datos["principio_funcionamiento"],
                    hechos=diagnostico["hechos_confirmados"],
                )
            datos["ishikawa_ia"] = ishikawa.model_dump()
            datos.setdefault("_revision_etapas", {})["3"] = "Actualizado por GearBot"
            datos["solicitudes_ia"] = max(2, int(datos.get("solicitudes_ia", 0)) + 1)
            avanzar(3)
        except Exception as error:
            mostrar_error_ia(error)


def paso_ishikawa() -> None:
    encabezado(
        "Ishikawa 6M ordenado",
        "Revisa la matriz uniforme y selecciona solo las causas aplicables.",
    )
    datos = st.session_state.nuevo_adf
    _auto_refrescar_ishikawa(datos)
    ishikawa = datos["ishikawa_ia"]
    indicador_consumo()
    ishikawa_guardado = datos.get("ishikawa_validado") or {}
    mostrar_ishikawa(datos["efecto"], ishikawa)

    st.info(ishikawa.get("resumen_tecnico", ""))
    for advertencia in ishikawa.get("advertencias", []):
        st.warning(advertencia)

    # Contraste reforzado para las 6M abiertas. Se limita al formulario de esta etapa.
    st.markdown(
        """
        <style>
        [data-testid="stForm"] [data-testid="stExpander"] details[open] > summary {
            background: linear-gradient(90deg, #f59e0b, #ffb545) !important;
            border-radius: 10px !important;
        }
        [data-testid="stForm"] [data-testid="stExpander"] details[open] > summary *,
        [data-testid="stForm"] [data-testid="stExpander"] details[open] > summary p,
        [data-testid="stForm"] [data-testid="stExpander"] details[open] > summary span {
            color: #182536 !important;
            -webkit-text-fill-color: #182536 !important;
            font-weight: 800 !important;
        }
        [data-testid="stForm"] [data-testid="stExpander"] details[open] > summary svg {
            color: #182536 !important;
            fill: #182536 !important;
        }
        [data-testid="stForm"] [data-testid="stExpander"] details[open] {
            border-color: #f59e0b !important;
            box-shadow: 0 0 0 1px rgba(245,158,11,.22) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.form("form_ishikawa"):
        resultado: dict[str, list[dict]] = {}
        for categoria, clave in CATEGORIAS.items():
            with st.expander(categoria, expanded=True):
                seleccionadas = []
                guardadas_categoria = ishikawa_guardado.get(categoria, []) if isinstance(ishikawa_guardado, dict) else []
                guardadas_por_causa = {str(x.get("causa", "")): x for x in guardadas_categoria if isinstance(x, dict)}
                causas_ia_nombres = {str(x.get("causa", "")) for x in ishikawa.get(clave, []) if isinstance(x, dict)}
                for indice, causa in enumerate(ishikawa.get(clave, [])):
                    guardada = guardadas_por_causa.get(str(causa.get("causa", "")))
                    incluir = st.checkbox(
                        f"{causa['causa']} · Prioridad {causa['prioridad_revision']}",
                        value=(True if guardada else causa["prioridad_revision"] == "Alta"),
                        key=f"inc_{clave}_{indice}",
                    )
                    mecanismo = st.text_area(
                        f"Mecanismo - {causa['causa']}",
                        value=(guardada.get("mecanismo", causa["mecanismo"]) if guardada else causa["mecanismo"]),
                        key=f"mec_{clave}_{indice}",
                        height=75,
                    )
                    if causa.get("preguntas_validacion"):
                        st.caption("Validar: " + " | ".join(causa["preguntas_validacion"]))
                    if incluir:
                        seleccionadas.append({**causa, "mecanismo": mecanismo.strip()})

                st.markdown("**Agregar causas observadas por el equipo investigador**")
                extras_guardadas = [
                    x for x in guardadas_categoria
                    if isinstance(x, dict) and str(x.get("causa", "")) not in causas_ia_nombres
                ]
                cantidad_key = f"cantidad_extra_{clave}"
                if cantidad_key not in st.session_state:
                    st.session_state[cantidad_key] = max(1, len(extras_guardadas))
                cantidad = max(1, int(st.session_state[cantidad_key]))

                for extra_idx in range(cantidad):
                    valor_extra = extras_guardadas[extra_idx].get("causa", "") if extra_idx < len(extras_guardadas) else ""
                    causa_extra = st.text_input(
                        f"Causa adicional {extra_idx + 1}",
                        value=valor_extra,
                        key=f"extra_causa_{clave}_{extra_idx}",
                        placeholder="Ej.: Holgura fuera de estándar en soporte de guía",
                    )
                    if causa_extra.strip():
                        seleccionadas.append({
                            "causa": causa_extra.strip(),
                            "mecanismo": "Causa agregada por el equipo investigador.",
                            "prioridad_revision": "Alta",
                            "preguntas_validacion": [],
                        })

                agregar = st.form_submit_button(
                    f"＋ Agregar otra causa en {categoria}",
                    key=f"agregar_extra_{clave}",
                    use_container_width=True,
                )
                quitar = False
                if cantidad > 1:
                    quitar = st.form_submit_button(
                        f"− Quitar última causa en {categoria}",
                        key=f"quitar_extra_{clave}",
                        use_container_width=True,
                    )
                if agregar:
                    st.session_state["_ishikawa_ajuste"] = ("agregar", clave)
                elif quitar:
                    st.session_state["_ishikawa_ajuste"] = ("quitar", clave)

                resultado[categoria] = seleccionadas

        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver", use_container_width=True)
        continuar = c2.form_submit_button(
            "Seleccionar causas para 5 Porqués →", type="primary", use_container_width=True,
        )
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(3)

    ajuste = st.session_state.pop("_ishikawa_ajuste", None)
    if ajuste:
        accion_ajuste, clave_ajuste = ajuste
        key_cantidad = f"cantidad_extra_{clave_ajuste}"
        actual = max(1, int(st.session_state.get(key_cantidad, 1)))
        if accion_ajuste == "agregar":
            st.session_state[key_cantidad] = actual + 1
        elif accion_ajuste == "quitar":
            ultima = actual - 1
            st.session_state[key_cantidad] = max(1, ultima)
            st.session_state.pop(f"extra_causa_{clave_ajuste}_{ultima}", None)
        st.rerun()

    if volver or viajar_seguro:
        if _cambio_real(datos.get("ishikawa_validado", {}), resultado):
            datos["ishikawa_validado"] = resultado
            _marcar_cambio_desde(3)
        avanzar(destino_seguro if viajar_seguro else 2)
        return
    if continuar:
        if sum(len(items) for items in resultado.values()) < 1:
            st.error("Selecciona o agrega al menos una causa.")
            return
        if _cambio_real(datos.get("ishikawa_validado", {}), resultado):
            datos["ishikawa_validado"] = resultado
            _marcar_cambio_desde(3)
        else:
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
            default=[x for x in (datos.get("causas_priorizadas") or []) if x in opciones] or opciones[: min(2, len(opciones))],
            help="Para cuidar cuota y claridad, se recomienda seleccionar entre 1 y 3.",
        )
        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver al Ishikawa", use_container_width=True)
        generar = c2.form_submit_button(
            "Generar 5 Porqués y planes con IA →", type="primary", use_container_width=True,
        )
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(4)
    if volver or viajar_seguro:
        if _cambio_real(datos.get("causas_priorizadas", []), priorizadas):
            datos["causas_priorizadas"] = list(priorizadas)
            _marcar_cambio_desde(4)
        avanzar(destino_seguro if viajar_seguro else 3)
        return
    if generar:
        if not priorizadas:
            st.error("Selecciona al menos una causa probable.")
            return
        if _cambio_real(datos.get("causas_priorizadas", []), priorizadas):
            datos["causas_priorizadas"] = list(priorizadas)
            _marcar_cambio_desde(4)
        else:
            datos["causas_priorizadas"] = list(priorizadas)
        contexto = (
            f"Equipo: {descripcion_equipo_para_redaccion(datos['equipo'])}\n"
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
            datos.setdefault("_revision_etapas", {})["5"] = "Actualizado por GearBot"
            datos.setdefault("_revision_etapas", {})["6"] = "Requiere actualización"
            datos["solicitudes_ia"] = max(3, int(datos.get("solicitudes_ia", 0)) + 1)
            avanzar(5)
        except Exception as error:
            mostrar_error_ia(error)


def paso_causal() -> None:
    encabezado(
        "5 Porqués editable con ayuda de IA",
        "La IA define entre 3 y 5 niveles según la complejidad. Puedes agregar o quitar niveles antes de continuar.",
    )
    datos = st.session_state.nuevo_adf
    _auto_refrescar_cadenas(datos)
    indicador_consumo()
    profundizacion = dict(datos["profundizacion"] or {})
    if datos.get("cadenas_causales"):
        cadenas_para_form = []
        base_por_causa = {str(c.get("causa", "")): c for c in profundizacion.get("cadenas", []) if isinstance(c, dict)}
        for cadena_validada in datos["cadenas_causales"]:
            base = base_por_causa.get(str(cadena_validada.get("causa", "")), {})
            niveles = []
            for nivel in cadena_validada.get("niveles", []):
                niveles.append({
                    "nivel": nivel.get("nivel"),
                    "pregunta": nivel.get("pregunta", ""),
                    "respuesta_sugerida": nivel.get("respuesta", ""),
                    "justificacion_tecnica": nivel.get("justificacion", ""),
                    "evidencia_requerida": nivel.get("evidencia", ""),
                })
            cadenas_para_form.append({
                **base,
                "causa": cadena_validada.get("causa", base.get("causa", "")),
                "niveles": niveles,
                "causa_raiz_preliminar": cadena_validada.get("causa_raiz_preliminar", ""),
                "advertencia": base.get("advertencia", "Debe validarse en terreno."),
            })
        profundizacion["cadenas"] = cadenas_para_form

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
                    with st.expander("🤖 Ayuda / justificación técnica de la IA", expanded=False):
                        justificacion = st.text_area(
                            "Justificación técnica",
                            value=nivel["justificacion_tecnica"],
                            key=f"just_{indice_cadena}_{indice_nivel}",
                            height=90,
                            label_visibility="collapsed",
                        )
                    with st.expander("🔎 Evidencia necesaria para validarlo", expanded=False):
                        evidencia = st.text_area(
                            "Evidencia requerida",
                            value=nivel["evidencia_requerida"],
                            key=f"evid_{indice_cadena}_{indice_nivel}",
                            height=80,
                            label_visibility="collapsed",
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
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(5)

    if volver or viajar_seguro:
        if _cambio_real(datos.get("cadenas_causales", []), cadenas_editadas):
            datos["cadenas_causales"] = cadenas_editadas
            _marcar_cambio_desde(5)
        avanzar(destino_seguro if viajar_seguro else 4)
        return
    if continuar:
        for cadena in cadenas_editadas:
            if len(cadena["niveles"]) < 3:
                st.error("Cada cadena debe contener al menos 3 niveles causales.")
                return
            if any(len(nivel["respuesta"]) < 8 for nivel in cadena["niveles"]):
                st.error("Todas las respuestas causales deben quedar suficientemente desarrolladas.")
                return
        if _cambio_real(datos.get("cadenas_causales", []), cadenas_editadas):
            datos["cadenas_causales"] = cadenas_editadas
            _marcar_cambio_desde(5)
        else:
            datos["cadenas_causales"] = cadenas_editadas
        avanzar(6)


def paso_planes() -> None:
    encabezado(
        "Planes de prevención",
        "Ajusta acciones, responsables, plazos y evidencias antes del informe.",
    )
    datos = st.session_state.nuevo_adf
    _auto_refrescar_desde_5porques(datos)
    indicador_consumo()
    acciones = datos.get("plan_prevencion") or datos["profundizacion"].get("plan_prevencion", [])

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
                responsable_actual = accion.get("responsable_sugerido", "")
                if str(responsable_actual).strip().lower() == "por definir": responsable_actual = ""
                responsable = st.text_input("Responsable *", value=responsable_actual, key=f"resp_plan_{indice}", placeholder="Nombre de la persona responsable", help="Campo obligatorio para cada plan de acción.")
                fecha_actual = accion.get("fecha_compromiso", "")
                try: fecha_default = datetime.fromisoformat(str(fecha_actual)).date() if fecha_actual else date.today()
                except (TypeError, ValueError): fecha_default = date.today()
                fecha_compromiso = st.date_input("Fecha de compromiso *", value=fecha_default, format="DD/MM/YYYY", key=f"fecha_plan_{indice}", help="Campo obligatorio. Selecciona la fecha en el calendario.")
                st.caption(f"📅 Compromiso: **{fecha_compromiso.strftime('%d/%m/%Y')}**")
                evidencia = st.text_area(
                    "Evidencia de implementación",
                    value=accion["evidencia_de_implementacion"], key=f"evid_plan_{indice}",
                )
                acciones_editadas.append({
                    "accion": texto.strip(),
                    "objetivo": objetivo.strip(),
                    "relacion_con_causa": relacion.strip(),
                    "responsable_sugerido": responsable.strip(),
                    "plazo_sugerido": fecha_compromiso.strftime("%d/%m/%Y"),
                    "evidencia_de_implementacion": evidencia.strip(),
                    "fecha_compromiso": fecha_compromiso.isoformat(),
                    "estado_ejecucion": accion.get("estado_ejecucion", "Pendiente"),
                    "fecha_ejecucion": accion.get("fecha_ejecucion", ""),
                    "noti_sap": accion.get("noti_sap", ""),
                    "status_usuario_sap": accion.get("status_usuario_sap", ""),
                    "mov_mercancias": accion.get("mov_mercancias", ""),
                    "gasto_asociado": accion.get("gasto_asociado", 0.0),
                    "moneda_gasto": accion.get("moneda_gasto", "CLP"),
                })

        c1, c2 = st.columns(2)
        volver = c1.form_submit_button("← Volver a 5 Porqués", use_container_width=True)
        generar = c2.form_submit_button(
            "Generar redacción final con IA →", type="primary", use_container_width=True,
        )
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(6)

    if volver or viajar_seguro:
        if _cambio_real(datos.get("plan_prevencion", []), acciones_editadas):
            datos["plan_prevencion"] = acciones_editadas
            _marcar_cambio_desde(6)
        avanzar(destino_seguro if viajar_seguro else 5)
        return
    if generar:
        validas = [a for a in acciones_editadas if a["accion"] and a["relacion_con_causa"]]
        if not validas:
            st.error("Debe existir al menos una acción preventiva válida.")
            return
        incompletas = []
        for n, accion in enumerate(validas, start=1):
            if not accion.get("responsable_sugerido", "").strip(): incompletas.append(f"Acción {n}: falta Responsable")
            if not accion.get("fecha_compromiso"): incompletas.append(f"Acción {n}: falta Fecha de compromiso")
        if incompletas:
            st.error("Antes de continuar completa los campos obligatorios de cada plan:\n\n- " + "\n- ".join(incompletas))
            return
        if _cambio_real(datos.get("plan_prevencion", []), validas):
            datos["plan_prevencion"] = validas
            _marcar_cambio_desde(6)
        else:
            datos["plan_prevencion"] = validas

        contexto = _contexto_vivo(datos)
        try:
            with st.spinner("GearBot está redactando el informe final..."):
                informe = generar_informe_final(contexto)
            datos["informe_final"] = informe.model_dump()
            datos["_informe_desactualizado"] = False
            datos.setdefault("_revision_etapas", {})["7"] = "Actualizado por GearBot"
            datos["solicitudes_ia"] = int(datos.get("solicitudes_ia", 0)) + 1
            avanzar(7)
        except Exception as error:
            mostrar_error_ia(error)


def paso_informe() -> None:
    encabezado(
        "Resumen preliminar del informe",
        "Cuarta llamada completada. Revisa y edita la propuesta antes de guardar y generar el PDF.",
    )
    datos = st.session_state.nuevo_adf
    _auto_refrescar_informe(datos)
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
        destino_seguro, viajar_seguro = _navegacion_retroceso_form(7)

    if volver or viajar_seguro:
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
        if _cambio_real(datos.get("informe_final", {}), informe_editado):
            datos["informe_final"] = informe_editado
            datos.setdefault("_revision_etapas", {})["7"] = "Modificado por investigador"
        avanzar(destino_seguro if viajar_seguro else 6)
        return
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
        payload_adf = {
            "creado_por": (datos.get("_creado_por_original") if datos.get("_correccion_jefatura") else st.session_state.usuario),
            "creado_por_email": (
                datos.get("_creado_por_email_original")
                if datos.get("_correccion_jefatura")
                else (st.session_state.get("usuario_actual") or {}).get("correo", "")
            ),
            "estado": "Borrador",
            "etapa": "Informe PDF",
            "centro": datos["centro"],
            "planta": datos.get("planta", ""),
            "area": datos["area"],
            "numero_equipo": datos["numero_equipo"],
            "equipo": datos["equipo"],
            "aviso_sap": datos["aviso_sap"],
            "tiempo_perdido_h": datos.get("tiempo_perdido_h", 0.0),
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
        }
        if datos.get("id_edicion"):
            adf_id = actualizar_adf(
                int(datos["id_edicion"]),
                payload_adf,
                conservar_devolucion_jefatura=bool(datos.get("_correccion_jefatura")),
            )
        elif datos.get("id_guardado"):
            adf_id = actualizar_contenido_borrador(int(datos["id_guardado"]), payload_adf)
        else:
            adf_id = guardar_adf(payload_adf)
        datos["id_guardado"] = adf_id
        pdf_datos = {
            **informe_editado,
            "creado_por": (datos.get("_creado_por_original") if datos.get("_correccion_jefatura") else st.session_state.usuario),
            "centro": datos["centro"],
            "planta": datos.get("planta", ""),
            "area": datos["area"],
            "numero_equipo": datos["numero_equipo"],
            "equipo": datos["equipo"],
            "aviso_sap": datos["aviso_sap"],
            "tiempo_perdido_h": datos.get("tiempo_perdido_h", 0.0),
            "relato_original": datos["relato_original"],
            "efecto": datos["efecto"],
            "ishikawa_validado": datos["ishikawa_validado"],
            "cadenas_causales": datos["cadenas_causales"],
            "plan_prevencion": datos["plan_prevencion"],
        }
        datos["pdf_bytes"] = generar_pdf_adf(
            pdf_datos,
            imagen_falla=datos.get("imagen_falla"),
            imagen_equipo=datos.get("imagen_equipo"),
            imagen_componente=datos.get("imagen_componente"),
        )
        guardar_pdf_adf(adf_id, datos["pdf_bytes"])
        avanzar(8)


def paso_pdf() -> None:
    datos = st.session_state.nuevo_adf
    es_correccion_jefatura = bool(datos.get("_correccion_jefatura"))
    encabezado(
        "ADF corregido · revisión de Jefatura" if es_correccion_jefatura else "Informe preparado para validación",
        (
            "Puedes revisar el PDF, volver a cualquier etapa para corregir y reenviar el mismo ADF directamente a Jefatura."
            if es_correccion_jefatura
            else "El ADF está guardado. Puedes enviarlo al flujo Supervisor → Jefe con notificaciones internas y trazabilidad de cada decisión."
        ),
    )
    adf = obtener_adf(datos["id_guardado"])
    st.success(f"ADF #{datos['id_guardado']} guardado correctamente.")
    nombre = f"ADF_{datos['equipo'].replace(' ', '_')}_{datos['id_guardado']}.pdf"
    pdf_actual = datos.get("pdf_bytes") or (getattr(adf, "pdf_archivo", None) if adf else None)
    if pdf_actual:
        st.download_button(
            "📄 Revisar / descargar PDF",
            data=pdf_actual,
            file_name=nombre,
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    else:
        st.info("El PDF se regenerará cuando guardes nuevamente el informe técnico.")

    supervisor = resolver_supervisor(datos["centro"], datos["area"])
    jefe = resolver_jefe(datos["centro"], datos["area"])
    with st.container(border=True):
        st.subheader("Flujo de aprobación")
        st.write(f"**Supervisor:** {supervisor['nombre']} · {supervisor['correo']}" if supervisor else "**Supervisor:** No encontrado para esta área")
        st.write(f"**Jefe:** {jefe['nombre']} · {jefe['correo']}" if jefe else "**Jefe:** No encontrado para esta área")

        if es_correccion_jefatura and adf and adf.estado == "Devuelto por Jefatura":
            st.warning("↩️ **ADF devuelto por Jefatura**")
            st.write(f"**Observación de Jefatura:** {datos.get('_observacion_jefatura') or adf.comentario_validacion or 'Sin comentario registrado'}")
            st.caption(
                "El ADF conserva su mismo ID y toda la trazabilidad. Al terminar la corrección se reenviará "
                "directamente a Jefatura; no requiere una nueva autoaprobación del Supervisor."
            )
            nota = st.text_area(
                "Comentario de la corrección (opcional)",
                key=f"nota_correccion_jef_{adf.id}",
                placeholder="Ej.: Se incorporó información explícita de la falla del cableado y se ajustó la conclusión técnica.",
            )
            c_editar, c_reenviar = st.columns(2)
            with c_editar:
                if st.button("✏️ Volver a editar", key=f"editar_dev_jef_{adf.id}", use_container_width=True):
                    avanzar(7)
            with c_reenviar:
                if st.button(
                    "✅ REENVIAR A JEFATURA",
                    key=f"reenviar_corregido_jef_{adf.id}",
                    type="primary",
                    use_container_width=True,
                ):
                    usuario = st.session_state.get("usuario_actual") or {}
                    comentario = nota.strip() or "ADF corregido por Supervisor según observación de Jefatura."
                    try:
                        resolver_devolucion_jefatura(adf.id, usuario, "reenviar_jefe", comentario)
                        datos["estado_validacion"] = "Pendiente Jefe"
                        datos["_correccion_jefatura"] = False
                        st.success("ADF corregido y reenviado a Jefatura. La trazabilidad quedó registrada.")
                        avanzar(9)
                    except Exception as error:
                        st.error(str(error))
            return

        st.caption("Al enviar, el ADF pasa a Pendiente Supervisor. Si se aprueba, avanza automáticamente a Pendiente Jefe.")

        if not supervisor:
            st.warning("⚠️ Esta área no tiene Supervisor configurado. El ADF podrá ser tomado por el Ingeniero como reemplazo.")
        if not jefe:
            st.warning("⚠️ Esta área no tiene Jefe configurado. El Ingeniero podrá actuar como reemplazo en la etapa final.")

        if adf and adf.estado == "Borrador":
            st.caption(
                "Mientras el ADF siga en Borrador puedes volver a editar cualquier etapa. "
                "La edición se bloquea recién cuando lo envías a validación."
            )
            volver_col, enviar_col = st.columns(2)
            with volver_col:
                if st.button(
                    "← Volver y editar",
                    key=f"volver_editar_pdf_{adf.id}",
                    use_container_width=True,
                ):
                    avanzar(7)
            with enviar_col:
                if st.button(
                    "📨 Enviar a validación",
                    key=f"enviar_validacion_{adf.id}",
                    type="primary",
                    use_container_width=True,
                ):
                    registrar_envio_validacion(adf.id, supervisor, jefe)
                    datos["estado_validacion"] = "Pendiente Supervisor"
                    if supervisor:
                        st.success("ADF enviado a validación. El Supervisor recibió una notificación dentro de RootMine.")
                    else:
                        st.success("ADF enviado a validación. Quedó disponible en la bandeja transversal del Ingeniero.")
                    st.rerun()
        elif adf:
            st.info(f"Estado actual: **{adf.estado}** · {adf.etapa}")

    if adf and adf.estado != "Borrador":
        if st.button("Ver resumen final →", use_container_width=True):
            avanzar(9)


def paso_final() -> None:
    datos = st.session_state.nuevo_adf
    encabezado(
        "RootMine v4.5.1 · análisis completado",
        "El análisis quedó guardado y disponible para la memoria técnica.",
    )
    st.write(f"**Centro (Planta):** {datos['centro']} - {datos.get('planta','')}")
    st.write(f"**Equipo:** {datos['equipo']}")
    st.caption(f"N° de equipo (identificador): {datos['numero_equipo']}")
    st.write(f"**Fenómeno:** {datos['efecto']}")
    st.write(f"**Solicitudes IA:** {datos['solicitudes_ia']}")
    adf = obtener_adf(datos.get('id_guardado')) if datos.get('id_guardado') else None
    if adf:
        st.write(f"**Estado de validación:** {adf.estado}")
        if adf.comentario_validacion:
            st.warning(f"Último comentario: {adf.comentario_validacion}")
    st.info(
        "Las causas y la causa raíz deben considerarse preliminares hasta que la evidencia de terreno sea revisada y aprobada."
    )
    if adf and adf.estado == "Borrador":
        st.warning(
            "Este ADF todavía está en borrador y no ha completado el envío a validación."
        )
        if st.button("← Volver a PDF / envío", type="primary", use_container_width=True):
            datos["paso"] = 8
            _guardar_avance(8)
            st.rerun()
    else:
        if st.button("Crear otro ADF", type="primary", use_container_width=True):
            st.session_state.pop("nuevo_adf", None)
            st.rerun()


def mostrar_nuevo_adf() -> None:
    inicializar()
    datos_actuales = st.session_state.nuevo_adf
    paso = datos_actuales["paso"]

    if datos_actuales.get("id_guardado") and datos_actuales.get("estado_validacion") == "Borrador":
        st.info(
            f"📝 Continuando el ADF #{datos_actuales['id_guardado']} desde la etapa guardada. "
            "Los cambios se guardarán en este mismo ADF; no se creará uno nuevo."
        )
        if datos_actuales.pop("_retomado_desde_resumen", False):
            st.caption(
                "El borrador estaba en Resumen final sin haber sido enviado. "
                "RootMine lo devolvió automáticamente a PDF / envío para que puedas completar el flujo."
            )
    st.markdown(
        f'<div class="step-chip">RootMine v4.5.1 · Etapa {paso} de {TOTAL_ETAPAS}</div>',
        unsafe_allow_html=True,
    )
    st.progress(paso / TOTAL_ETAPAS)
    _barra_navegacion_etapas()
    _aviso_analisis_vivo()
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
