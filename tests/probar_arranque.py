"""Streamlit Cloud-style entry: execute app.py within an existing runtime."""
import asyncio,os,sys,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
root=Path(__file__).resolve().parents[1]

async def ejecutar_ui():
    async with websockets.connect('ws://127.0.0.1:8851/_stcore/stream',subprotocols=['streamlit']) as ws:
        msg=BackMsg();msg.rerun_script.query_string='campo_enlace=1';await ws.send(msg.SerializeToString())
        for _ in range(100):
            raw=await asyncio.wait_for(ws.recv(),15);f=ForwardMsg();f.ParseFromString(raw)
            if f.HasField('delta') and f.delta.HasField('new_element') and f.delta.new_element.HasField('exception'):raise RuntimeError(f.delta.new_element.exception.message)
            if f.HasField('script_finished'):return
        raise RuntimeError('No terminó de abrir la interfaz')

with tempfile.TemporaryDirectory(prefix='nm482-startup-') as d:
    log=open(Path(d)/'server.log','w+')
    env=dict(os.environ,NO_PROXY='127.0.0.1,localhost')
    server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(root/'app.py'),'--server.port=8851','--server.address=127.0.0.1','--server.headless=true','--browser.gatherUsageStats=false'],cwd=d,env=env,stdout=log,stderr=log)
    try:
        for i in range(90):
            if server.poll() is not None:raise RuntimeError('No arrancó el servidor')
            try:urllib.request.urlopen('http://127.0.0.1:8851/_stcore/health',timeout=1);break
            except (urllib.error.URLError,TimeoutError):time.sleep(.2)
        else:raise RuntimeError('No arrancó Streamlit')
        asyncio.run(ejecutar_ui())
        with urllib.request.urlopen('http://127.0.0.1:8851/neuralmant-campo/',timeout=3) as r:assert r.status==200 and 'Vista de terreno' in r.read().decode()
        for req in [urllib.request.Request('http://127.0.0.1:8851/neuralmant-campo/api/estado'),urllib.request.Request('http://127.0.0.1:8851/neuralmant-campo/api/activar',data=b'{"ticket":"invalido"}',headers={'Content-Type':'application/json'})]:
            try:urllib.request.urlopen(req,timeout=3)
            except urllib.error.HTTPError as exc:assert exc.code==401,exc.code
            else:raise RuntimeError('La API aceptó un acceso inválido')
        print('OK: app.py abre la interfaz dentro de Streamlit, prepara rutas de terreno y mantiene autenticación GET/POST.')
    finally:
        server.terminate()
        try:server.wait(timeout=8)
        except subprocess.TimeoutExpired:server.kill()
        log.seek(0);print(log.read()[-1000:]);log.close()
