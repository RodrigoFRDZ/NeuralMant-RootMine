"""Solicitudes persistentes con autorización, historial y avisos en una transacción."""
import json
import math
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from database.conexion import engine
from database.modelos import SolicitudMaterial, NotificacionInterna, UsuarioRootMine
from database.usuarios import _a_dict, _areas_responsabilidad, _norm

PERFILES = ("Contrapedido", "Stock de seguridad", "Pronóstico")
ESTADOS = ("Borrador", "Pendiente jefe", "Pendiente análisis", "Pendiente subgerente", "Pendiente carga SAP", "Cargado en SAP", "Devuelta", "Rechazada")


def criticidad(m_rotativo, smac, co, te, ma, estrategico):
    if m_rotativo:
        return "M"
    if any(x not in (1, 2, 3) for x in (smac, co, te, ma)):
        raise ValueError("Selecciona todas las respuestas de criticidad.")
    # Árbol SV-DC-MAN-019, revisión de mayo 2025.
    if smac == 1 or co == 1 or (te == 1 and ma == 1):
        return "Z" if estrategico else "A"
    if te == 3 or ma == 3:
        return "C"
    return "B"


def impacto(d):
    def n(k):
        v = Decimal(str(d.get(k, 0)))
        if not v.is_finite() or v < 0:
            raise ValueError(f"{k}: debe ser un número no negativo.")
        return v
    incremento = max(Decimal(0), n("ss_propuesto") - n("ss_actual")) * n("precio")
    compra = max(Decimal(0), n("ss_propuesto") + n("reservas") - n("stock") - n("oc")) * n("precio")
    bodega = n("valor_bodega")
    return {"incremento_ss": float(incremento), "reposicion": float(compra),
            "porcentaje": float(incremento / bodega * 100) if bodega else None,
            "bodega_proyectada": float(bodega + compra),
            "porcentaje_reposicion": float(compra / bodega * 100) if bodega else None}


def _usuario(s, correo):
    reg = s.scalar(select(UsuarioRootMine).where(UsuarioRootMine.correo == correo.strip().lower(), UsuarioRootMine.activo.is_(True)))
    if not reg:
        raise ValueError("La cuenta no está activa.")
    return _a_dict(reg)


def candidatos(usuarios, etapa, centro, area):
    return [u for u in usuarios if u.get("activo", True) and elegible(u, etapa, centro, area)]


def elegible(u, etapa, centro, area):
    mismo = str(u.get("centro", "")) == str(centro)
    if etapa == "analista":
        return (u.get("es_admin") or u.get("rol") in ("ingeniero", "analizador_materiales")) and (mismo or u.get("es_admin"))
    if not mismo:
        return False
    if etapa == "subgerente":
        return u.get("rol") == "subgerente"
    areas = _areas_responsabilidad(u)
    return u.get("rol") == "jefe" and (_norm(area) in areas or "TODAS" in areas)


def _visible(r, u):
    correo = u["correo"]
    return bool(u.get("es_admin") or correo in (r.solicitante_email, r.jefe_email, r.analista_email, r.subgerente_email))


def _dict(r):
    return {c.name: getattr(r, c.name) for c in r.__table__.columns} | {"datos": json.loads(r.datos_json), "historial": json.loads(r.historial_json)}


def listar(correo):
    with Session(engine) as s:
        u = _usuario(s, correo)
        q = select(SolicitudMaterial).order_by(SolicitudMaterial.id.desc())
        if not u.get("es_admin"):
            q = q.where(or_(SolicitudMaterial.solicitante_email == correo,
                           SolicitudMaterial.jefe_email == correo,
                           SolicitudMaterial.analista_email == correo,
                           SolicitudMaterial.subgerente_email == correo))
        return [_dict(r) for r in s.scalars(q).all()]


def _validar(d, tipo, completo=True):
    if tipo not in ("Stock de seguridad", "MRP"):
        raise ValueError("Tipo de solicitud inválido.")
    if completo:
        for k in ("material", "descripcion", "unidad", "centro", "area", "justificacion"):
            if not str(d.get(k, "")).strip():
                raise ValueError(f"Debes completar {k}.")
        if d.get("criticidad") not in ("A", "B", "C", "Z", "M"):
            raise ValueError("Selecciona una criticidad válida.")
        if d.get("m_rotativo") and d.get("criticidad") != "M":
            raise ValueError("Un motor o bomba reparable rotativo debe conservar la categoría M.")
    if tipo == "MRP":
        if d.get("criticidad") == "M" or d.get("m_rotativo"):
            raise ValueError("Los materiales M no se pueden incorporar al MRP.")
        if completo:
            if d.get("perfil") == "Stock de seguridad" and float(d.get("cantidad", 0)) <= 0:
                raise ValueError("Indica la cantidad solicitada de stock de seguridad.")
            if d.get("perfil") not in PERFILES or d.get("mercado") not in ("Nacional", "Importado"):
                raise ValueError("Completa perfil y mercado.")
            lt = d.get("lead_time", 0)
            if not isinstance(lt, int) or isinstance(lt, bool) or lt < 1:
                raise ValueError("El lead time debe ser una cantidad entera de días mayor a cero.")
    if completo and tipo == "Stock de seguridad":
        if float(d.get("cantidad", 0)) <= 0:
            raise ValueError("La cantidad solicitada debe ser mayor a cero.")
    for k in ("cantidad", "ss_actual", "ss_propuesto", "precio", "stock", "reservas", "oc", "valor_bodega"):
        if k in d and (not math.isfinite(float(d[k])) or float(d[k]) < 0):
            raise ValueError(f"Valor inválido para {k}.")


def _log(r, u, accion, comentario=""):
    h = json.loads(r.historial_json or "[]")
    h.append({"fecha": datetime.utcnow().isoformat(), "usuario": u["nombre"], "correo": u["correo"],
              "accion": accion, "estado": r.estado, "comentario": comentario,
              "version_datos": json.loads(r.datos_json or "{}")})
    r.historial_json = json.dumps(h, ensure_ascii=False)


def _aviso(s, correo, r, mensaje):
    s.add(NotificacionInterna(destinatario_email=correo, adf_id=None, tipo="materiales",
        titulo=f"Materiales #{r.id} · {r.estado}", mensaje=mensaje))


def guardar(correo, tipo, d, responsables, enviar=False, solicitud_id=None, version=None):
    _validar(d, tipo, completo=enviar)
    with Session(engine) as s:
        u = _usuario(s, correo)
        if not u.get("es_admin") and str(d.get("centro")) != str(u.get("centro")):
            raise ValueError("Solo puedes solicitar para tu centro.")
        if solicitud_id:
            r = s.get(SolicitudMaterial, solicitud_id, with_for_update=True)
            if not r or r.solicitante_email != correo or r.estado not in ("Borrador", "Devuelta"):
                raise ValueError("No puedes editar esta solicitud.")
            if r.version != version:
                raise ValueError("La solicitud cambió. Actualiza antes de continuar.")
            if r.tipo != tipo:
                raise ValueError("No puedes cambiar el tipo de una solicitud.")
        else:
            r = SolicitudMaterial(tipo=tipo, solicitante_email=correo, solicitante_nombre=u["nombre"],
                centro=str(d.get("centro", "")), area=d.get("area", ""), material=d.get("material", ""),
                estado="Borrador", historial_json="[]")
            s.add(r)
        if enviar:
            for etapa in ("jefe", "analista", "subgerente"):
                elegido = _usuario(s, responsables.get(etapa, ""))
                if not elegible(elegido, etapa, d["centro"], d["area"]):
                    raise ValueError(f"Responsable {etapa} inválido para el centro/área.")
            if len(set(responsables.values())) != 3:
                raise ValueError("Selecciona responsables distintos para las tres etapas.")
            duplicada = s.scalar(select(SolicitudMaterial.id).where(
                SolicitudMaterial.centro == d["centro"], SolicitudMaterial.material == d["material"],
                SolicitudMaterial.tipo == tipo, SolicitudMaterial.estado.in_(ESTADOS[1:5]),
                SolicitudMaterial.id != (r.id or -1)))
            if duplicada:
                raise ValueError(f"Ya existe la solicitud activa #{duplicada} para este material y centro.")
        r.centro = str(d.get("centro", "")); r.area = d.get("area", ""); r.material = d.get("material", "")
        # Cualquier reenvío invalida la evaluación y vuelve al jefe.
        r.datos_json = json.dumps(d, ensure_ascii=False)
        r.jefe_email = responsables.get("jefe", ""); r.analista_email = responsables.get("analista", "")
        r.subgerente_email = responsables.get("subgerente", "")
        if enviar:
            r.estado = "Pendiente jefe"
            if not r.fecha_envio:
                r.fecha_envio = datetime.utcnow()
        s.flush()
        _log(r, u, "Enviada" if enviar else "Borrador guardado")
        if enviar:
            _aviso(s, r.jefe_email, r, f"{r.solicitante_nombre} solicita {r.tipo}: {r.material}. Revisa Gestión de Materiales.")
        try:
            s.commit()
        except StaleDataError:
            raise ValueError("La solicitud cambió. Actualiza e intenta nuevamente.") from None
        return r.id


def puede_actuar(r, u):
    campo = {"Pendiente jefe": "jefe_email", "Pendiente análisis": "analista_email",
             "Pendiente subgerente": "subgerente_email", "Pendiente carga SAP": "analista_email"}.get(r["estado"])
    if not campo:
        return False
    etapa = {"Pendiente jefe": "jefe", "Pendiente análisis": "analista",
             "Pendiente subgerente": "subgerente", "Pendiente carga SAP": "analista"}[r["estado"]]
    return u["correo"] == r[campo] and elegible(u, etapa, r["centro"], r["area"])


def decidir(correo, solicitud_id, version, accion, comentario="", analisis=None, carga=None):
    with Session(engine) as s:
        u = _usuario(s, correo)
        r = s.get(SolicitudMaterial, solicitud_id, with_for_update=True)
        if not r or not puede_actuar(_dict(r), u):
            raise ValueError("No eres el responsable de la etapa actual.")
        if r.version != version:
            raise ValueError("La solicitud cambió. Actualiza antes de continuar.")
        d = json.loads(r.datos_json)
        _validar(d, r.tipo)
        previo = r.estado
        if accion in ("Rechazar", "Devolver"):
            if not comentario.strip():
                raise ValueError("Debes indicar el motivo.")
            r.estado = "Rechazada" if accion == "Rechazar" else "Devuelta"
            destino = r.solicitante_email
        elif accion == "Aprobar" and previo == "Pendiente jefe":
            r.estado = "Pendiente análisis"; destino = r.analista_email
        elif accion == "Validar análisis" and previo == "Pendiente análisis":
            a = dict(analisis or {})
            if not a.get("fundamento", "").strip():
                raise ValueError("Debes justificar la validación de materiales.")
            _validar({**d, **a}, r.tipo)
            if a.get("criticidad") == "M" and (r.tipo == "MRP" or d.get("perfil") in PERFILES):
                raise ValueError("Los materiales M no se incorporan al MRP.")
            if r.tipo == "Stock de seguridad" or d.get("perfil") == "Stock de seguridad":
                if float(a.get("ss_propuesto", 0)) <= 0 or float(a.get("precio", 0)) <= 0 or float(a.get("valor_bodega", 0)) <= 0:
                    raise ValueError("Completa stock propuesto, precio y valor total de bodega mayores a cero.")
                if not a.get("fecha_datos") or not a.get("moneda"):
                    raise ValueError("Indica fecha y moneda de la valorización.")
                a["impacto"] = impacto(a)
            d["analisis"] = a; r.estado = "Pendiente subgerente"; destino = r.subgerente_email
        elif accion == "Aprobar" and previo == "Pendiente subgerente":
            if not d.get("analisis"):
                raise ValueError("Falta la evaluación de materiales.")
            r.estado = "Pendiente carga SAP"; destino = r.analista_email
        elif accion == "Cargado en SAP" and previo == "Pendiente carga SAP":
            c = dict(carga or {})
            if not c.get("referencia", "").strip() or not c.get("fecha"):
                raise ValueError("Indica la fecha real y referencia/evidencia de carga en SAP.")
            fecha = datetime.fromisoformat(c["fecha"])
            if fecha < r.fecha_envio or fecha > datetime.utcnow():
                raise ValueError("La fecha de carga debe estar entre el envío y el momento actual.")
            c["configuracion_aprobada"] = d.get("analisis", {})
            d["carga"] = c; r.fecha_carga = fecha; r.estado = "Cargado en SAP"; destino = r.solicitante_email
        else:
            raise ValueError("Acción inválida para la etapa actual.")
        r.datos_json = json.dumps(d, ensure_ascii=False)
        _log(r, u, accion, comentario)
        mensaje = f"Solicitud #{r.id}, material {r.material}: {r.estado}. {comentario}"
        if r.fecha_carga:
            horas = (r.fecha_carga - r.fecha_envio).total_seconds() / 3600
            mensaje += f" Tiempo desde envío hasta SAP: {horas:.1f} horas."
        _aviso(s, destino, r, mensaje)
        if destino != r.solicitante_email:
            _aviso(s, r.solicitante_email, r, mensaje)
        try:
            s.commit()
        except StaleDataError:
            raise ValueError("Otra persona actualizó la solicitud. Actualiza la pantalla.") from None
