"""Persistent updates, processed by two background workers while the app is running."""
import logging
import threading
from database import trabajos as db
from ia.cliente import obtener_configuracion, configuracion_ia_contexto, usuario_ia_contexto
from ia.novedad_automatica import interpretar

_lock=threading.Lock()
_iniciado=False

def iniciar():
    global _iniciado
    with _lock:
        if _iniciado:return
        configuracion=obtener_configuracion()
        _iniciado=True
    def worker():
        espera=threading.Event()
        configuracion_ia_contexto.set(configuracion)
        while True:
            try:
                job=db.tomar_novedad()
                if not job:espera.wait(1);continue
                usuario_ia_contexto.set(job['usuario'])
                try:db.resultado_novedad(job,interpretar(job['trabajo'],job['mensaje'],job.get('contexto')))
                except Exception:db.resultado_novedad(job,error='Novedad guardada. GearBot no pudo actualizar el avance ahora; puedes informar un porcentaje o usar los estados rápidos.')
            except Exception:
                logging.getLogger(__name__).exception('No se pudo procesar la cola de novedades')
                espera.wait(2)
    for i in range(2):threading.Thread(target=worker,name=f'gearbot-novedades-{i}',daemon=True).start()
