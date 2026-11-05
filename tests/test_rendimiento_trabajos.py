import json,unittest
from contextlib import contextmanager
from sqlalchemy import event,select
from sqlalchemy.orm import Session
from database import trabajos as db,campo
import test_trabajos as fixtures

@contextmanager
def consultas():
    sql=[]
    def contar(conn,cursor,statement,parameters,context,executemany):sql.append(statement)
    event.listen(db.engine,'before_cursor_execute',contar)
    try:yield sql
    finally:event.remove(db.engine,'before_cursor_execute',contar)

class RendimientoTrabajosTest(unittest.TestCase):
    setUp=fixtures.TrabajosTest.setUp
    tearDown=fixtures.TrabajosTest.tearDown
    trabajo=fixtures.TrabajosTest.trabajo

    def test_snapshot_consultas_constantes_con_96_trabajos_y_ultima_ia(self):
        token=campo.activar(campo.emitir_ticket('sup@test.cl',self.n))
        with consultas() as inicial:campo.snapshot(token)
        dato=self.trabajo()
        with Session(db.engine) as s,s.begin():
            for _ in range(95):s.add(db.TrabajoFinSemana(programa=self.n,datos=json.dumps({k:v for k,v in dato.items() if k not in ('id','version','historial')}),historial='[]'))
            s.flush()
            for t in s.scalars(select(db.TrabajoFinSemana).where(db.TrabajoFinSemana.programa==self.n)):
                for estado in ['pregunta','lista']:
                    s.add(db.NovedadIA(trabajo=t.id,programa=self.n,usuario='sup@test.cl',version=t.version,datos='{}',estado=estado,detalle=estado))
        with consultas() as cargado:resultado=campo.snapshot(token)
        self.assertEqual(len(resultado['trabajos']),96)
        self.assertTrue(all(t['ia']['estado']=='lista' for t in resultado['trabajos']))
        self.assertEqual(len(inicial),len(cargado))
        self.assertLessEqual(len(cargado),6)
        self.assertFalse(any('programa_fin_semana.pdf' in q or 'historico_trabajo.pdf' in q for q in cargado))

    def test_listado_no_descarga_pdf_y_descargas_explicitas_siguen_disponibles(self):
        siguiente=db.crear_programa('admin@test.cl','Siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        with consultas() as sql:programas=db.programas('sup@test.cl')
        self.assertTrue(next(p for p in programas if p['id']==self.n)['cerrado'])
        self.assertFalse(next(p for p in programas if p['id']==siguiente)['cerrado'])
        self.assertFalse(any('programa_fin_semana.pdf' in q or 'historico_trabajo.pdf' in q for q in sql))
        self.assertEqual(db.fuente('sup@test.cl',siguiente),self.pdf)
        self.assertTrue(db.historico_pdf('sup@test.cl',self.n).startswith(b'%PDF'))
