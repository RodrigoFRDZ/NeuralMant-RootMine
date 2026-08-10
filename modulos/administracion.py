import streamlit as st

from database.llaves_acceso import eliminar_llave, tiene_llave
from database.usuarios import (
    actualizar_usuario,
    cargar_centros,
    cargar_todos_usuarios,
    crear_usuario,
    eliminar_usuario,
    nombre_centro,
)

ADMIN_CORREOS = {"rfernandezc@agrosuper.com"}
ROLES = ["tecnico", "senior", "supervisor", "jefe", "ingeniero", "subgerente"]
AREAS_BASE = ["FAENA", "PROCESOS", "CONGELADO", "ELABORADOS", "SERVICIOS", "GENERACIÓN", "SADEMA", "ADM-DESP", "PLANIFICACIÓN", "INGENIERÍA"]


def _es_admin(usuario: dict) -> bool:
    correo = (usuario.get("correo") or usuario.get("email") or "").strip().lower()
    nombre = (usuario.get("nombre") or "").strip().lower()
    return correo in ADMIN_CORREOS or ("rodrigo" in nombre and "fern" in nombre and (usuario.get("rol") or "").strip().lower() == "ingeniero")


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

    tab1, tab2, tab3 = st.tabs(["➕ Crear cuenta", "✏️ Editar / eliminar", "🔐 Restablecer llaves"])

    with tab1:
        st.subheader("Nueva cuenta")
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre completo", key="adm_nuevo_nombre")
        correo = col2.text_input("Correo Agrosuper", placeholder="nombre@agrosuper.com", key="adm_nuevo_correo")

        col3, col4 = st.columns(2)
        centro_etiqueta = col3.selectbox("Centro / Planta", _centros_opciones(), key="adm_nuevo_centro")
        area = col4.selectbox("Área", AREAS_BASE, key="adm_nuevo_area")

        col5, col6 = st.columns(2)
        rol = col5.selectbox("Rol RootMine", ROLES, format_func=lambda x: x.capitalize(), key="adm_nuevo_rol")
        cargo = col6.text_input("Cargo / Job code", key="adm_nuevo_cargo")

        responsabilidades = st.text_input(
            "Responsable de (solo validadores)",
            placeholder="Ej.: FAENA, PROCESOS  |  Usa TODAS para responsabilidad transversal",
            key="adm_nuevo_resp",
        )
        st.caption("Para técnicos y senior puedes dejar 'Responsable de' vacío.")

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
            f"{u.get('nombre','Sin nombre')} · {u.get('rol','').capitalize()} · {u.get('correo','')}" : u
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
            rol_e = e5.selectbox("Rol", ROLES, index=ROLES.index(rol_actual) if rol_actual in ROLES else 0, format_func=lambda x: x.capitalize(), key=f"adm_rol_{correo_original}")
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
                confirmar = st.checkbox("Confirmar eliminación", key=f"adm_confirmar_del_{correo_original}", disabled=es_propia)
                if es_propia:
                    st.caption("Tu propia cuenta administradora no puede eliminarse desde RootMine.")
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
                f"{u.get('nombre')} · {u.get('rol','').capitalize()} · {u.get('correo')}" : u
                for u in validadores_lista
            }
            et_v = st.selectbox("Selecciona un validador", list(opciones_v.keys()), key="adm_reset_sel")
            val = opciones_v[et_v]
            correo_v = val.get("correo", "")
            r1, r2, r3 = st.columns(3)
            r1.metric("Rol", val.get("rol", "").capitalize())
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
