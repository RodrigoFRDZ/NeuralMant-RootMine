import streamlit as st

from database.llaves_acceso import eliminar_llave, tiene_llave
from database.repositorio_adf import listar_adf, eliminar_adf_completo, listar_borradores_globales, reasignar_borrador_adf
from database.usuarios import (
    actualizar_usuario,
    cargar_centros,
    cargar_todos_usuarios,
    crear_usuario,
    eliminar_usuario,
    nombre_centro,
    ROLES_TECNICOS,
)

ROLES = ["tecnico", "senior", "programador_mantenimiento", "ingeniero_confiabilidad", "ingeniero_procesos", "supervisor", "jefe", "subgerente"]
ROL_ADMIN = "ingeniero"

ETIQUETA_ROL = {
    "tecnico": "Técnico", "senior": "Senior",
    "programador_mantenimiento": "Programador de Mantenimiento",
    "ingeniero_confiabilidad": "Ingeniero de Confiabilidad",
    "ingeniero_procesos": "Ingeniero de Procesos",
    "supervisor": "Supervisor", "jefe": "Jefe",
    "ingeniero": "Ingeniero de Mantenimiento", "subgerente": "Subgerente",
}
AREAS_BASE = ["FAENA", "PROCESOS", "CONGELADO", "ELABORADOS", "SERVICIOS", "GENERACIÓN", "SADEMA", "ADM-DESP", "PLANIFICACIÓN", "INGENIERÍA"]


def _es_admin(usuario: dict) -> bool:
    return bool(usuario.get("es_admin", False))




def _centros_opciones():
    centros = cargar_centros()
    return [f"{codigo} - {info.get('nombre','')}" for codigo, info in centros.items() if info.get("activo", True)]


def _codigo_centro(etiqueta: str) -> str:
    return (etiqueta or "").split(" - ", 1)[0].strip()


def _resp_desde_texto(texto: str) -> list[str]:
    return [x.strip() for x in (texto or "").replace(";", ",").split(",") if x.strip()]


def mostrar_administracion() -> None:
    usuario_actual = st.session_state.get("usuario_actual") or {}
    if not _es_admin(usuario_actual):
        st.error("No tienes permisos de administrador de cuentas.")
        return

    st.markdown("# 👥 Administración de cuentas")
    st.caption("Crea, edita, elimina y restablece llaves de acceso. Esta sección está disponible solo para el administrador RootMine.")

    usuarios = cargar_todos_usuarios()
    activos = sum(1 for u in usuarios if u.get("activo", True))
    validadores = sum(1 for u in usuarios if (u.get("rol") or "").lower() in {"supervisor", "jefe", "ingeniero", "subgerente"} and u.get("activo", True))
    c1, c2, c3 = st.columns(3)
    c1.metric("Cuentas registradas", len(usuarios))
    c2.metric("Activas", activos)
    c3.metric("Validadores activos", validadores)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ Crear cuenta", "✏️ Editar / eliminar", "🔐 Restablecer llaves", "🗑️ Administrar ADF", "🔄 Reasignar borradores"])

    with tab1:
        st.subheader("Nueva cuenta")
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre completo", key="adm_nuevo_nombre")
        correo = col2.text_input("Correo Agrosuper", placeholder="nombre@agrosuper.com", key="adm_nuevo_correo")

        col3, col4 = st.columns(2)
        centro_etiqueta = col3.selectbox("Centro / Planta", _centros_opciones(), key="adm_nuevo_centro")
        area = col4.selectbox("Área", AREAS_BASE, key="adm_nuevo_area")

        col5, col6 = st.columns(2)
        rol = col5.selectbox("Rol RootMine", ROLES, format_func=lambda x: ETIQUETA_ROL.get(x, x.replace("_", " ").title()), key="adm_nuevo_rol")
        es_admin_nuevo = st.checkbox("Administrador RootMine", value=False, key="adm_nuevo_es_admin",
                                     help="Permiso independiente del cargo. Solo un administrador puede otorgarlo.")
        cargo = col6.text_input("Cargo / Job code", key="adm_nuevo_cargo")

        responsabilidades = st.text_input(
            "Responsable de (solo validadores)",
            placeholder="Ej.: FAENA, PROCESOS  |  Usa TODAS para responsabilidad transversal",
            key="adm_nuevo_resp",
        )
        st.caption("Para perfiles técnicos (Técnico, Senior, Programador, Ing. Confiabilidad e Ing. Procesos) deja 'Responsable de' vacío.")

        if st.button("➕ Crear cuenta", type="primary", use_container_width=True):
            codigo = _codigo_centro(centro_etiqueta)
            try:
                crear_usuario({
                    "rut": "",
                    "nombre": nombre,
                    "correo": correo,
                    "area": area,
                    "job_code": cargo,
                    "rol": rol,
                    "es_admin": es_admin_nuevo,
                    "centro": codigo,
                    "planta": nombre_centro(codigo),
                    "activo": True,
                    "responsable_de": _resp_desde_texto(responsabilidades),
                })
                st.success("Cuenta creada correctamente.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with tab2:
        st.subheader("Editar o eliminar cuenta")
        usuarios_ordenados = sorted(usuarios, key=lambda u: ((u.get("nombre") or ""), (u.get("correo") or "")))
        opciones = {
            f"{u.get('nombre','Sin nombre')} · {ETIQUETA_ROL.get(u.get('rol',''), u.get('rol','').replace('_',' ').title())} · {u.get('correo','')}" : u
            for u in usuarios_ordenados
        }
        if not opciones:
            st.info("No hay cuentas registradas.")
        else:
            etiqueta = st.selectbox("Selecciona una cuenta", list(opciones.keys()), key="adm_editar_sel")
            seleccionado = opciones[etiqueta]
            correo_original = seleccionado.get("correo", "")

            e1, e2 = st.columns(2)
            nombre_e = e1.text_input("Nombre completo", value=seleccionado.get("nombre", ""), key=f"adm_nombre_{correo_original}")
            correo_e = e2.text_input("Correo", value=correo_original, key=f"adm_correo_{correo_original}")

            centros = _centros_opciones()
            centro_actual = str(seleccionado.get("centro", ""))
            idx_centro = next((i for i, x in enumerate(centros) if x.startswith(centro_actual + " -")), 0)
            e3, e4 = st.columns(2)
            centro_e = e3.selectbox("Centro / Planta", centros, index=idx_centro, key=f"adm_centro_{correo_original}")
            area_actual = seleccionado.get("area", "") or ""
            areas = AREAS_BASE if area_actual in AREAS_BASE else AREAS_BASE + [area_actual]
            area_e = e4.selectbox("Área", areas, index=areas.index(area_actual) if area_actual in areas else 0, key=f"adm_area_{correo_original}")

            e5, e6 = st.columns(2)
            rol_actual = (seleccionado.get("rol") or "tecnico").lower()
            roles_edicion = list(ROLES)
            if ROL_ADMIN not in roles_edicion:
                roles_edicion.append(ROL_ADMIN)
            rol_e = e5.selectbox("Rol", roles_edicion, index=roles_edicion.index(rol_actual) if rol_actual in roles_edicion else 0, format_func=lambda x: ETIQUETA_ROL.get(x, x.replace("_", " ").title()), key=f"adm_rol_{correo_original}")
            es_admin_e = st.checkbox(
                "Administrador RootMine",
                value=bool(seleccionado.get("es_admin", False)),
                key=f"adm_es_admin_{correo_original}",
                help="Este permiso no depende del rol o cargo del usuario.",
            )
            cargo_e = e6.text_input("Cargo / Job code", value=seleccionado.get("job_code", ""), key=f"adm_cargo_{correo_original}")

            resp_actual = seleccionado.get("responsable_de") or []
            if isinstance(resp_actual, str):
                resp_actual = _resp_desde_texto(resp_actual)
            resp_e = st.text_input("Responsable de", value=", ".join(resp_actual), key=f"adm_resp_{correo_original}")
            activo_e = st.toggle("Cuenta activa", value=bool(seleccionado.get("activo", True)), key=f"adm_activo_{correo_original}")

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 Guardar cambios", type="primary", use_container_width=True, key=f"adm_guardar_{correo_original}"):
                    nuevo_codigo = _codigo_centro(centro_e)
                    try:
                        actualizar_usuario(correo_original, {
                            "nombre": nombre_e,
                            "correo": correo_e,
                            "centro": nuevo_codigo,
                            "planta": nombre_centro(nuevo_codigo),
                            "area": area_e,
                            "rol": rol_e,
                            "es_admin": es_admin_e,
                            "job_code": cargo_e,
                            "responsable_de": _resp_desde_texto(resp_e),
                            "activo": activo_e,
                        })
                        if correo_original.lower() != correo_e.strip().lower() and tiene_llave(correo_original):
                            eliminar_llave(correo_original)
                            st.info("Como cambió el correo, la llave anterior fue eliminada. El usuario deberá crear una nueva.")
                        st.success("Cuenta actualizada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            with b2:
                es_propia = correo_original.lower() == (usuario_actual.get("correo") or "").lower()
                es_ultimo_admin = bool(seleccionado.get("es_admin", False)) and sum(
                    1 for u in usuarios if u.get("activo", True) and u.get("es_admin", False)
                ) <= 1
                confirmar = st.checkbox("Confirmar eliminación", key=f"adm_confirmar_del_{correo_original}", disabled=es_propia)
                if es_propia:
                    st.caption("Tu propia cuenta administradora no puede eliminarse desde RootMine.")
                elif es_ultimo_admin:
                    st.caption("No puedes eliminar la última cuenta administradora activa de RootMine.")
                if st.button("🗑️ Eliminar cuenta", use_container_width=True, disabled=es_propia or not confirmar, key=f"adm_del_{correo_original}"):
                    if tiene_llave(correo_original):
                        eliminar_llave(correo_original)
                    if eliminar_usuario(correo_original):
                        st.success("Cuenta eliminada correctamente.")
                        st.rerun()
                    else:
                        st.error("No fue posible eliminar la cuenta.")

    with tab3:
        st.subheader("Restablecer llave de acceso")
        st.info("Las llaves nunca se muestran. Al restablecer una, se elimina la actual y el validador deberá crear una nueva en su próximo ingreso.")
        validadores_lista = [
            u for u in usuarios
            if (u.get("rol") or "").lower() in {"supervisor", "jefe", "ingeniero", "subgerente"} and u.get("activo", True)
        ]
        validadores_lista.sort(key=lambda u: ((u.get("nombre") or ""), (u.get("correo") or "")))
        if not validadores_lista:
            st.info("No hay validadores activos.")
        else:
            opciones_v = {
                f"{u.get('nombre')} · {ETIQUETA_ROL.get(u.get('rol',''), u.get('rol','').replace('_',' ').title())} · {u.get('correo')}" : u
                for u in validadores_lista
            }
            et_v = st.selectbox("Selecciona un validador", list(opciones_v.keys()), key="adm_reset_sel")
            val = opciones_v[et_v]
            correo_v = val.get("correo", "")
            r1, r2, r3 = st.columns(3)
            r1.metric("Rol", ETIQUETA_ROL.get(val.get("rol", ""), val.get("rol", "").replace("_", " ").title()))
            r2.metric("Centro", val.get("centro", "—"))
            r3.metric("Llave", "Configurada" if tiene_llave(correo_v) else "Sin crear")
            if tiene_llave(correo_v):
                confirmar_r = st.checkbox("Confirmo que deseo restablecer esta llave", key=f"adm_reset_confirm_{correo_v}")
                if st.button("🔐 Restablecer llave", type="primary", use_container_width=True, disabled=not confirmar_r):
                    if eliminar_llave(correo_v):
                        st.success("Llave restablecida. El usuario deberá crear una nueva al iniciar sesión.")
                        st.rerun()
            else:
                st.success("Este usuario no tiene una llave creada actualmente.")


    with tab4:
        st.subheader("Administración de ADF")
        st.warning(
            "Esta sección elimina registros de forma permanente de la base de datos. "
            "Úsala principalmente para limpiar ADF de prueba."
        )

        adfs = listar_adf()
        if not adfs:
            st.info("No hay ADF registrados en la base.")
        else:
            busqueda_adf = st.text_input(
                "Buscar ADF",
                placeholder="N° ADF, equipo, N° equipo, área, centro o creador",
                key="adm_buscar_adf",
            ).strip().lower()

            filtrados = []
            for adf in adfs:
                texto = " ".join([
                    str(adf.id),
                    adf.equipo or "",
                    getattr(adf, "numero_equipo", "") or "",
                    adf.area or "",
                    getattr(adf, "centro", "") or "",
                    getattr(adf, "planta", "") or "",
                    adf.creado_por or "",
                    adf.creado_por_email or "",
                    adf.estado or "",
                ]).lower()
                if not busqueda_adf or busqueda_adf in texto:
                    filtrados.append(adf)

            if not filtrados:
                st.info("No se encontraron ADF con ese filtro.")
            else:
                opciones_adf = {
                    (
                        f"ADF #{adf.id} · {adf.equipo or 'Sin equipo'} · "
                        f"{getattr(adf, 'centro', '') or 's/centro'} · "
                        f"{adf.area or 's/área'} · {adf.estado or 'Borrador'}"
                    ): adf
                    for adf in filtrados
                }
                etiqueta_adf = st.selectbox(
                    "Selecciona el ADF que deseas revisar",
                    list(opciones_adf.keys()),
                    key="adm_adf_sel",
                )
                adf_sel = opciones_adf[etiqueta_adf]

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("ADF", f"#{adf_sel.id}")
                c2.metric("Centro", getattr(adf_sel, "centro", "") or "—")
                c3.metric("Área", adf_sel.area or "—")
                c4.metric("Estado", adf_sel.estado or "Borrador")

                st.markdown(f"**Equipo:** {adf_sel.equipo or 'No registrado'}")
                st.markdown(f"**N° equipo:** {getattr(adf_sel, 'numero_equipo', '') or 'No registrado'}")
                st.markdown(f"**Creado por:** {adf_sel.creado_por or 'No registrado'}")
                st.caption(
                    "Al eliminarlo también se borran su trazabilidad de validación, "
                    "notificaciones, planes y respaldos guardados dentro del ADF."
                )

                confirmar_id = st.text_input(
                    f"Para confirmar, escribe el número del ADF: {adf_sel.id}",
                    key=f"adm_confirmar_adf_{adf_sel.id}",
                ).strip()

                if st.button(
                    "🗑️ Eliminar ADF permanentemente",
                    type="primary",
                    use_container_width=True,
                    disabled=confirmar_id != str(adf_sel.id),
                    key=f"adm_eliminar_adf_{adf_sel.id}",
                ):
                    resultado = eliminar_adf_completo(adf_sel.id)
                    if resultado.get("ok"):
                        st.success(f"ADF #{adf_sel.id} eliminado correctamente de la base.")
                        st.rerun()
                    else:
                        st.error(resultado.get("mensaje", "No fue posible eliminar el ADF."))

    with tab5:
        st.subheader("Reasignar borradores")
        st.info(
            "Los borradores solo pueden ser continuados por su responsable actual. "
            "Como administrador puedes transferirlos a otro usuario habilitado. "
            "La reasignación queda registrada en la trazabilidad del ADF."
        )

        borradores = listar_borradores_globales()
        if not borradores:
            st.success("No hay borradores pendientes de reasignación.")
        else:
            opciones_borrador = {
                (
                    f"ADF #{adf.id} · {adf.equipo or 'Sin equipo'} · "
                    f"{adf.area or 's/área'} · Responsable: {adf.creado_por or 'No registrado'}"
                ): adf
                for adf in borradores
            }
            etiqueta_b = st.selectbox(
                "Selecciona el borrador",
                list(opciones_borrador.keys()),
                key="adm_reasignar_borrador_sel",
            )
            borrador = opciones_borrador[etiqueta_b]

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("ADF", f"#{borrador.id}")
            r2.metric("Etapa", borrador.borrador_paso or 1)
            r3.metric("Centro", borrador.centro or "—")
            r4.metric("Área", borrador.area or "—")

            st.markdown(f"**Equipo:** {borrador.equipo or 'No registrado'}")
            st.markdown(
                f"**Responsable actual:** {borrador.creado_por or 'No registrado'} "
                f"· {borrador.creado_por_email or 's/correo'}"
            )
            st.caption(
                f"Última actualización: "
                f"{borrador.fecha_actualizacion:%d/%m/%Y %H:%M}"
                if borrador.fecha_actualizacion else "Sin fecha registrada"
            )

            # Perfiles que pueden generar/continuar ADF, más el propio Ingeniero/Admin.
            candidatos = [
                u for u in usuarios
                if u.get("activo", True)
                and (
                    (u.get("rol") or "").lower() in ROLES_TECNICOS
                    or (u.get("rol") or "").lower() == "ingeniero"
                )
                and (u.get("correo") or "").strip().lower()
                    != (borrador.creado_por_email or "").strip().lower()
            ]
            candidatos.sort(key=lambda u: ((u.get("nombre") or ""), (u.get("correo") or "")))

            if not candidatos:
                st.warning("No existen otros usuarios activos habilitados para recibir este borrador.")
            else:
                opciones_destino = {
                    (
                        f"{u.get('nombre','Sin nombre')} · "
                        f"{ETIQUETA_ROL.get(u.get('rol',''), u.get('rol','').replace('_',' ').title())} · "
                        f"{u.get('correo','')}"
                    ): u
                    for u in candidatos
                }
                etiqueta_destino = st.selectbox(
                    "Nuevo responsable",
                    list(opciones_destino.keys()),
                    key=f"adm_reasignar_destino_{borrador.id}",
                )
                destino = opciones_destino[etiqueta_destino]

                motivo = st.text_area(
                    "Motivo / comentario de reasignación",
                    placeholder="Ej.: técnico de turno no disponible; el ADF continuará con el siguiente responsable.",
                    key=f"adm_reasignar_motivo_{borrador.id}",
                )

                confirmar = st.checkbox(
                    f"Confirmo reasignar el ADF #{borrador.id} a {destino.get('nombre','')}",
                    key=f"adm_reasignar_confirm_{borrador.id}",
                )

                if st.button(
                    "🔄 Reasignar borrador",
                    type="primary",
                    use_container_width=True,
                    disabled=not confirmar,
                    key=f"adm_reasignar_btn_{borrador.id}",
                ):
                    try:
                        actualizado = reasignar_borrador_adf(
                            borrador.id,
                            usuario_actual,
                            destino,
                            motivo,
                        )
                        if actualizado:
                            st.success(
                                f"ADF #{actualizado.id} reasignado correctamente a {destino.get('nombre')}."
                            )
                            st.caption(
                                "El nuevo responsable lo verá en 'ADF en progreso' y podrá continuar "
                                "desde la última etapa guardada."
                            )
                            st.rerun()
                        else:
                            st.error("No fue posible encontrar el borrador.")
                    except Exception as exc:
                        st.error(str(exc))

