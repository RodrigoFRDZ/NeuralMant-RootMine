"""Same-origin offline routes registered at startup through Streamlit App."""
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


def marcar_rutas_registradas():
    global _registradas
    _registradas=True


def instalar_en_streamlit():
    """Compatibility name: routes are registered by app.py before server startup."""
    return _registradas


def diagnostico():
    import streamlit
    return f'Streamlit {streamlit.__version__}. Inicia con app.py de v4.8.1 y copia neuralmant_ui.py, requirements.txt y la carpeta campo. Reinicia la aplicación después de actualizar dependencias.'
