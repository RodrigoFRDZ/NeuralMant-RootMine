"""Integration: submit the real chat fragment through Streamlit WebSocket."""
import asyncio,os,sys,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
from test_trabajos_ui import SCRIPT

async def recibir(ws):
    mensajes=[]
    for _ in range(300):
        raw=await asyncio.wait_for(ws.recv(),15);f=ForwardMsg();f.ParseFromString(raw);mensajes.append(f)
        if f.HasField('delta') and f.delta.HasField('new_element') and f.delta.new_element.HasField('exception'):raise RuntimeError(f.delta.new_element.exception.message)
        if f.HasField('script_finished') and f.script_finished!=2:return mensajes
    raise RuntimeError('No terminó el fragmento')

async def comprobar():
    async with websockets.connect('ws://127.0.0.1:8853/_stcore/stream',subprotocols=['streamlit']) as ws:
        m=BackMsg();m.rerun_script.query_string='';await ws.send(m.SerializeToString());inicio=await recibir(ws)
        entradas=[f for f in inicio if f.HasField('delta') and f.delta.HasField('new_element') and f.delta.new_element.HasField('chat_input')]
        assert len(entradas)==1
        entrada=entradas[0];fragmento=entrada.delta.fragment_id;assert fragmento
        m=BackMsg();m.rerun_script.fragment_id=fragmento
        w=m.rerun_script.widget_states.widgets.add();w.id=entrada.delta.new_element.chat_input.id;w.chat_input_value.data='avance 60%'
        await ws.send(m.SerializeToString());respuesta=await recibir(ws)
        textos=[f.delta.new_element.markdown.body for f in respuesta if f.HasField('delta') and f.delta.HasField('new_element') and f.delta.new_element.HasField('markdown')]
        assert any('60%' in t for t in textos),textos
        assert not any('PÁGINA COMPLETA' in t for t in textos),textos
        # A full rerun can report how many times the outer page executed.
        m=BackMsg();m.rerun_script.query_string='';await ws.send(m.SerializeToString());final=await recibir(ws)
        textos=[f.delta.new_element.markdown.body for f in final if f.HasField('delta') and f.delta.HasField('new_element') and f.delta.new_element.HasField('markdown')]
        assert 'PÁGINA COMPLETA: 2' in textos,textos
        print('OK: enviar un mensaje actualiza el chat y limpia la entrada sin volver a ejecutar la página completa.')

with tempfile.TemporaryDirectory(prefix='nm483-fragment-') as d:
    ruta=Path(d);script=SCRIPT.replace('m.mostrar_trabajos()',"st.session_state.setdefault('trab_vista','Chat de avance')\nst.session_state.setdefault('trab_chat_area_1','Faena')\nst.session_state.setdefault('trab_chat_activo_1',1)\nst.session_state['_pagina_completa']=st.session_state.get('_pagina_completa',0)+1\nst.write('PÁGINA COMPLETA: '+str(st.session_state['_pagina_completa']))\nm.mostrar_trabajos()")
    (ruta/'app.py').write_text('import sys\nsys.path.insert(0,'+repr(str(root))+')\n'+script)
    with open(ruta/'server.log','w+') as log:
        servidor=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ruta/'app.py'),'--server.port=8853','--server.address=127.0.0.1','--server.headless=true','--browser.gatherUsageStats=false'],cwd=d,stdout=log,stderr=log,env=dict(os.environ,NO_PROXY='127.0.0.1,localhost'))
        try:
            for _ in range(80):
                try:urllib.request.urlopen('http://127.0.0.1:8853/_stcore/health',timeout=1);break
                except (urllib.error.URLError,TimeoutError):time.sleep(.2)
            asyncio.run(comprobar())
        finally:
            servidor.terminate()
            try:servidor.wait(timeout=8)
            except subprocess.TimeoutExpired:servidor.kill()
            log.seek(0);print(log.read()[-1000:])
