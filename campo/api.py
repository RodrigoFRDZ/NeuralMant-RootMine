"""Same-origin offline routes registered at startup through Streamlit App."""
import gc
import threading
from pathlib import Path
from starlette.routing import Route,Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import JSONResponse,FileResponse
from starlette.concurrency import run_in_threadpool
from database import campo as datos

ROOT=Path(__file__).resolve().parent/'web'
HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}

async def api(request):
    metodo=request.path_params['accion']
    token=request.headers.get('X-Neuralmant-Session','')
    try:
        if request.method=='POST':
            cuerpo=await request.body()
            if len(cuerpo)>9*1024*1024:return JSONResponse({'error':'Novedad demasiado grande.'},status_code=413,headers=HEADERS)
            import json
            payload=json.loads(cuerpo)
        if metodo=='activar' and request.method=='POST':
            token=await run_in_threadpool(datos.activar,str(payload.get('ticket','')))
            estado=await run_in_threadpool(datos.snapshot,token)
            return JSONResponse(dict(token=token,snapshot=estado),headers=HEADERS)
        if not token:raise datos.AccesoInvalido('Abre Vista de terreno desde tu sesión de NeuralMant.')
        if metodo=='estado' and request.method=='GET':resultado=await run_in_threadpool(datos.snapshot,token)
        elif metodo=='sincronizar' and request.method=='POST':resultado=await run_in_threadpool(datos.sincronizar,token,payload)
        elif metodo=='salir' and request.method=='POST':await run_in_threadpool(datos.cerrar,token);resultado={'ok':True}
        else:return JSONResponse({'error':'Ruta desconocida.'},status_code=404,headers=HEADERS)
        return JSONResponse(resultado,headers=HEADERS)
    except datos.AccesoInvalido as exc:return JSONResponse({'error':str(exc)},status_code=401,headers=HEADERS)
    except (ValueError,KeyError,TypeError) as exc:return JSONResponse({'error':str(exc)},status_code=409,headers=HEADERS)
    except Exception:return JSONResponse({'error':'No se pudo guardar ahora. La novedad se conserva en el dispositivo.'},status_code=503,headers=HEADERS)

async def shell(request):
    return FileResponse(ROOT/'index.html',headers={'Cache-Control':'no-cache','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'"})

async def service_worker(request):
    return FileResponse(ROOT/'sw.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})

def routes(prefijo=''):
    base=('/'+prefijo.strip('/') if prefijo else '')+'/neuralmant-campo'
    return [Route(base+'/',shell),Route(base+'/sw.js',service_worker),Route(base+'/api/{accion}',api,methods=['GET','POST']),Mount(base+'/assets',app=StaticFiles(directory=ROOT))]

_registradas=False
_lock=threading.Lock()
_detalle='Rutas de terreno pendientes de preparación.'


def marcar_rutas_registradas():
    global _registradas
    _registradas=True


def instalar_en_streamlit():
    """Register field routes on the existing server; never start a second runtime."""
    global _registradas,_detalle
    with _lock:
        if _registradas:return True
        try:
            from starlette.applications import Starlette
            from streamlit.runtime import Runtime
            from streamlit import config
            if not Runtime.exists():
                _detalle='El servidor de Streamlit aún no ha iniciado.'
                return False
            loop=Runtime.instance()._get_async_objs().eventloop
            aplicaciones=[obj for obj in gc.get_objects() if isinstance(obj,Starlette) and any(getattr(r,'path','').endswith('/_stcore/health') for r in obj.routes)]
            if not aplicaciones:
                _detalle='Este servidor no expone el router compatible con Vista de terreno. El chat conectado sigue disponible.'
                return False
            terminado=threading.Event();errores=[]
            def agregar():
                try:
                    prefijo=config.get_option('server.baseUrlPath') or ''
                    for app in aplicaciones:
                        base=('/'+prefijo.strip('/') if prefijo else '')+'/neuralmant-campo/'
                        if not any(getattr(r,'path','')==base for r in app.routes):app.router.routes[:0]=routes(prefijo)
                except Exception as exc:errores.append(type(exc).__name__)
                finally:terminado.set()
            loop.call_soon_threadsafe(agregar)
            if not terminado.wait(5):
                _detalle='El servidor no alcanzó a preparar Vista de terreno. Reintenta con conexión.'
                return False
            if errores:
                _detalle='No se pudieron registrar las rutas de Vista de terreno ('+errores[0]+').'
                return False
            _registradas=True;_detalle='Rutas de terreno registradas.'
            return True
        except Exception as exc:
            _detalle='No se pudo preparar Vista de terreno ('+type(exc).__name__+'). Revisa que requirements.txt esté actualizado.'
            return False


def diagnostico():
    import streamlit
    return f'Streamlit {streamlit.__version__}: {_detalle}'
