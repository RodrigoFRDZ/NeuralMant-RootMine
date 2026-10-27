import base64,json
from datetime import datetime,timedelta
from uuid import uuid4
from io import BytesIO
from PIL import Image
from sqlalchemy.orm import Session
from database import campo,trabajos as db
from test_trabajos import TrabajosTest
import unittest

class CampoTest(unittest.TestCase):
    setUp=TrabajosTest.setUp
    tearDown=TrabajosTest.tearDown
    trabajo=TrabajosTest.trabajo
    def token(self,correo='sup@test.cl'):
        return campo.activar(campo.emitir_ticket(correo,self.n))
    def evento(self,texto='60%',accion='mensaje',prev=None):
        return dict(uuid=str(uuid4()),trabajo_id=self.trabajo()['id'],accion=accion,texto=texto,capturado='2026-10-14T12:00:00Z',base_version=self.trabajo()['version'],prev_uuid=prev,fotos=[])
    def test_ticket_un_solo_uso_sesion_y_roles(self):
        ticket=campo.emitir_ticket('sup@test.cl',self.n);token=campo.activar(ticket)
        self.assertEqual(campo.snapshot(token)['usuario']['correo'],'sup@test.cl')
        with self.assertRaises(campo.AccesoInvalido):campo.activar(ticket)
        prog=self.token('prog@test.cl');self.assertFalse(campo.snapshot(prog)['usuario']['puede_editar'])
        with self.assertRaises(campo.AccesoInvalido):campo.sincronizar(prog,self.evento())
        campo.cerrar(token)
        with self.assertRaises(campo.AccesoInvalido):campo.snapshot(token)
    def test_reintento_no_duplica_historial_ni_foto(self):
        token=self.token();e=self.evento();foto=BytesIO();Image.new('RGB',(40,40),'red').save(foto,format='PNG')
        e['fotos']=[dict(nombre='prueba.png',datos=base64.b64encode(foto.getvalue()).decode())]
        self.assertFalse(campo.sincronizar(token,e)['repetido'])
        self.assertTrue(campo.sincronizar(token,e)['repetido'])
        d=self.trabajo();self.assertEqual(d['avance'],60);self.assertEqual(len(d['historial']),1)
        self.assertEqual(d['historial'][0]['usuario'],'sup@test.cl')
        self.assertEqual(d['historial'][0]['capturado_dispositivo'],e['capturado'])
        self.assertEqual(len(db.evidencia('sup@test.cl',self.n,d['id'])),1)
        with self.assertRaises(ValueError):campo.sincronizar(token,e|{'texto':'70%'})
    def test_secuencia_offline_y_pruebas_con_observaciones(self):
        token=self.token();primero=self.evento('trabajo terminado');base=primero['base_version']
        campo.sincronizar(token,primero)
        prev=primero['uuid']
        for accion,texto in [('iniciar_prueba',''),('con_observaciones',''),('describir_observacion','Vibración anormal en soporte'),('impide_partida','')]:
            e=self.evento(texto,accion,prev);e['base_version']=base;campo.sincronizar(token,e);prev=e['uuid']
        d=self.trabajo();self.assertEqual(d['avance'],100);self.assertEqual(d['prueba'],'Fallida')
        self.assertIn('Vibración anormal',d['hallazgos']);self.assertEqual(db.lineas([d])[0]['partida'],'Pendiente')
    def test_sin_observaciones_aprobada_y_sin_borrar_otro_pendiente(self):
        token=self.token();campo.sincronizar(token,self.evento('trabajo terminado'))
        campo.sincronizar(token,self.evento('', 'iniciar_prueba'))
        campo.sincronizar(token,self.evento('no'))
        self.assertEqual(self.trabajo()['prueba'],'Aprobada')
    def test_conflicto_no_sobrescribe_y_raw_se_conserva(self):
        token=self.token();e=self.evento('40%');d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')};c.update(estado='En ejecución',avance=80)
        db.actualizar('otro@test.cl',self.n,d['id'],d['version'],c,mensaje='80%')
        self.assertTrue(campo.sincronizar(token,e)['conflicto'])
        self.assertEqual(self.trabajo()['avance'],80)
        self.assertEqual(self.trabajo()['ultimo_mensaje'],'40%')
        self.assertEqual(db.ultima_novedad('sup@test.cl',self.n,d['id'])['estado'],'pregunta')
    def test_resultado_ia_propio_no_rompe_cadena_offline(self):
        token=self.token();e=self.evento('Montaje iniciado');base=e['base_version'];campo.sincronizar(token,e)
        job=db.tomar_novedad();db.resultado_novedad(job,dict(estado='En ejecución',avance=40,origen_avance='informado_supervisor'))
        segundo=self.evento('60%',prev=e['uuid']);segundo['base_version']=base
        self.assertFalse(campo.sincronizar(token,segundo)['conflicto'])
        self.assertEqual(self.trabajo()['avance'],60)
    def test_archivado_acepta_ack_repetido_y_rechaza_novedad_nueva(self):
        token=self.token();e=self.evento();campo.sincronizar(token,e)
        db.crear_programa('prog@test.cl','Nueva','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        self.assertTrue(campo.snapshot(token)['programa']['cerrado'])
        self.assertTrue(campo.sincronizar(token,e)['repetido'])
        with self.assertRaisesRegex(ValueError,'cerrado'):campo.sincronizar(token,e|{'uuid':str(uuid4())})
    def test_foto_invalida_no_deja_recibo_ni_cambio_parcial(self):
        token=self.token();e=self.evento();e['fotos']=[dict(nombre='no.png',datos=base64.b64encode(b'no es imagen').decode())]
        with self.assertRaises(ValueError):campo.sincronizar(token,e)
        self.assertEqual(self.trabajo()['historial'],[])
        with Session(db.engine) as s:self.assertEqual(s.query(campo.ReciboCampo).count(),0)

class PruebaConversacionTest(unittest.TestCase):
    def test_no_declara_partida_por_terminar_trabajo(self):
        from motores.pruebas_trabajos import transicion,desde_mensaje
        d=dict(estado='Terminado',avance=100,pendiente='Retirar herramientas',hallazgos='',prueba='Pendiente',detalle_prueba='')
        d.update(transicion(d,'iniciar_prueba'));self.assertEqual(d['prueba'],'En prueba')
        d.update(desde_mensaje(d,'no'));self.assertEqual(d['prueba'],'Aprobada')
        self.assertEqual(d['pendiente'],'Retirar herramientas')
        self.assertEqual(db.lineas([d|{'area':'Faena','linea':''}])[0]['partida'],'Pendiente')
