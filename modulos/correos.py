"""Compatibilidad v4.0.

El envío de correo externo está intencionalmente desactivado durante el piloto.
El flujo operativo usa database.notificaciones y la campana interna de RootMine.
Este módulo queda como punto de extensión para una integración futura sin tocar
la lógica de aprobación.
"""


def correo_habilitado() -> bool:
    return False


def enviar_correo(*args, **kwargs) -> tuple[bool, str]:
    return False, "Correo externo desactivado. RootMine usa notificaciones internas."
