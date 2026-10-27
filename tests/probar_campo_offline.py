"""Integration test: synthetic server + JS DOM/IndexedDB network-loss simulation.
Run npm install --prefix tests/js, then python tests/probar_campo_offline.py.
Does not change production data and does not need a Gemini key.
"""
import json,os,subprocess,sys,tempfile,threading,time
from pathlib import Path
from io import BytesIO
import urllib.request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from reportlab.pdfgen import canvas
from PIL import Image
from starlette.applications import Starlette
import uvicorn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from database import trabajos as db,campo
from database.modelos import Base,UsuarioRootMine
from campo.api import routes

def main():
    original=db.engine
    with tempfile.TemporaryDirectory(prefix='neuralmant-offline-test-') as temporal:
        db.engine=create_engine('sqlite:///'+str(Path(temporal)/'prueba.db'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(db.engine)
        with Session(db.engine) as s,s.begin():s.add(UsuarioRootMine(nombre='Supervisor de prueba',correo='supervisor@test.cl',rol='supervisor',centro='0001',area='FAENA',activo=True,es_admin=True,responsable_de='[]'))
        out=BytesIO();c=canvas.Canvas(out);c.drawString(20,700,'Programacion de prueba');c.save()
        filas=[dict(descripcion='Cambio de aceite del transportador',area='Faena',ot='10000001',linea='L1',equipo='Transportador'),dict(descripcion='Revision rodamiento',area='Procesos',ot='10000002',linea='L1',equipo='Motor')]
        n=db.crear_programa('supervisor@test.cl','Fin de semana de prueba','0001','2026-10-17','2026-10-18','prueba.pdf',out.getvalue(),filas)
        config=Path(temporal)/'config.json';config.write_text(json.dumps({'ticket':campo.emitir_ticket('supervisor@test.cl',n)}))
        foto=Path(temporal)/'foto.png';Image.new('RGB',(40,40),'orange').save(foto)
        servidor=uvicorn.Server(uvicorn.Config(Starlette(routes=routes()),host='127.0.0.1',port=8850,log_level='warning'))
        thread=threading.Thread(target=servidor.run,daemon=True);thread.start()
        try:
            for _ in range(60):
                if servidor.started:break
                time.sleep(.1)
            if not servidor.started:raise RuntimeError('No arrancó el servidor de prueba')
            env=dict(os.environ,NEURALMANT_TEST_CONFIG=str(config),NEURALMANT_TEST_PHOTO=str(foto),NEURALMANT_TEST_ORIGIN='http://127.0.0.1:8850',NO_PROXY='127.0.0.1,localhost')
            result=subprocess.run(['node',str(ROOT/'tests/js/campo_offline.cjs')],env=env,timeout=35)
            return result.returncode
        finally:
            servidor.should_exit=True;thread.join(timeout=5);db.engine.dispose();db.engine=original
if __name__=='__main__':sys.exit(main())
