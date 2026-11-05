import unittest, tempfile
from io import BytesIO
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from PIL import Image
from database.modelos import Base, UsuarioRootMine
from database import trabajos as db
from modulos.programacion_pdf import texto_pdf, extraer_trabajos, ProgramacionExtraida, TrabajoExtraido
from reportes.trabajos import generar_pdf

class TrabajosTest(unittest.TestCase):
    def setUp(self):
        import database.campo  # register device models before creating the test schema
        self.tmp=tempfile.TemporaryDirectory();self.original=db.engine
        db.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'trabajos.db'))
        Base.metadata.create_all(db.engine)
        with Session(db.engine) as s:
            for correo,rol,centro,admin in [('admin@test.cl','ingeniero','1802',True),('sup@test.cl','supervisor','1802',False),('otro@test.cl','supervisor','1802',False),('coord@test.cl','coordinador_mantenimiento','1802',False),('coordfuera@test.cl','coordinador_mantenimiento','1803',False),('fuera@test.cl','supervisor','1803',False),('tec@test.cl','tecnico','1802',False),('prog@test.cl','programador_mantenimiento','1802',False),('jefe@test.cl','jefe','1802',False),('ing@test.cl','ingeniero','1802',False),('sub@test.cl','subgerente','1802',False)]:
                s.add(UsuarioRootMine(nombre=correo,correo=correo,rol=rol,centro=centro,area='FAENA',activo=True,es_admin=admin,responsable_de='[]'))
            s.commit()
        out=BytesIO();c=canvas.Canvas(out);c.drawString(40,760,'Faena L1 - Cambio de rodamiento del transportador');c.save();self.pdf=out.getvalue()
        self.fila=dict(descripcion='Cambio de rodamiento',linea='L1',area='Faena',equipo='Transportador',supervisor='sup@test.cl',referencia_pdf='página 1')
        self.n=db.crear_programa('admin@test.cl','Fin de semana','1802','2026-10-17','2026-10-18','plan.pdf',self.pdf,[self.fila])
    def tearDown(self):
        db.engine.dispose();db.engine=self.original;self.tmp.cleanup()
    def trabajo(self):return db.trabajos('sup@test.cl',self.n)[0]
    def guardar(self,**cambios):
        d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')};c.update(cambios)
        db.actualizar('sup@test.cl',self.n,d['id'],d['version'],c)
    def test_pruebas_guardan_fotos_y_rechazo_no_cambia_resultado(self):
        self.guardar(estado='Terminado',avance=100)
        out=BytesIO();Image.new('RGB',(40,30),'green').save(out,format='PNG')
        foto=('prueba.png',out.getvalue())
        for accion in ('posponer_prueba','iniciar_prueba','sin_observaciones'):
            d=self.trabajo()
            db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],accion,fotos=[foto])
        d=self.trabajo()
        self.assertEqual(d['prueba'],'Aprobada')
        self.assertEqual(len(d['fotos']),3)
        self.assertEqual([f['contenido'] for f in db.evidencia('sup@test.cl',self.n,d['id'])],[foto[1]]*3)

    def test_imagen_invalida_o_conflicto_no_guarda_prueba_ni_foto(self):
        self.guardar(estado='Terminado',avance=100)
        d=self.trabajo()
        with self.assertRaises(ValueError):
            db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],'iniciar_prueba',fotos=[('rota.png',b'invalido')])
        self.assertEqual(self.trabajo(),d)
        out=BytesIO();Image.new('RGB',(40,30),'green').save(out,format='PNG')
        with self.assertRaises(ValueError):
            db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version']-1,'iniciar_prueba',fotos=[('prueba.png',out.getvalue())])
        self.assertEqual(self.trabajo(),d)
        self.assertEqual(db.evidencia('sup@test.cl',self.n,d['id']),[])

    def test_roles_programador_supervisor_administrador_y_lectura(self):
        d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        for correo in ['prog@test.cl','jefe@test.cl','ing@test.cl','sub@test.cl','tec@test.cl']:
            self.assertEqual(len(db.trabajos(correo,self.n)),1)
            with self.assertRaises(ValueError):db.actualizar(correo,self.n,d['id'],d['version'],c,mensaje='Intento sin permiso')
            with self.assertRaises(ValueError):db.cerrar_turno(correo,self.n,'2026-10-17','Día','',str(uuid4()))
            if correo!='prog@test.cl':
                with self.assertRaises(ValueError):db.crear_programa(correo,'Otro','1802','2026-10-19','2026-10-20','plan.pdf',self.pdf,[self.fila])
        db.actualizar('admin@test.cl',self.n,d['id'],d['version'],c,mensaje='Administrador puede actualizar')
        d=self.trabajo();self.assertEqual(d['ultimo_mensaje'],'Administrador puede actualizar')
        self.assertEqual(d['historial'][-1]['mensaje'],d['ultimo_mensaje'])
        db.cerrar_turno('admin@test.cl',self.n,'2026-10-17','Día','',str(uuid4()))
        n=db.crear_programa('prog@test.cl','Siguiente semana','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        self.assertTrue(n>self.n)

    def test_novedad_y_estado_sin_porcentaje_no_inventan_avance(self):
        self.guardar(estado='En ejecución',avance=None)
        self.assertIsNone(self.trabajo()['avance'])
        self.assertIsNone(db.lineas([self.trabajo()])[0]['avance'])
        self.assertEqual(db.lineas([self.trabajo()])[0]['sin_porcentaje'],1)
        with self.assertRaises(ValueError):self.guardar(estado='Terminado',avance=None)

    def test_permisos_centro_responsable_y_duplicados(self):
        self.assertEqual(db.programas('fuera@test.cl'),[])
        with self.assertRaises(ValueError):db.trabajos('fuera@test.cl',self.n)
        d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        for correo in ['fuera@test.cl','coordfuera@test.cl','tec@test.cl']:
            with self.assertRaises(ValueError):db.actualizar(correo,self.n,d['id'],d['version'],c)
        with self.assertRaisesRegex(ValueError,'ya fue publicado'):db.crear_programa('admin@test.cl','Otro','1802','2026-10-17','2026-10-18','plan.pdf',self.pdf,[self.fila])
        with self.assertRaises(ValueError):db.crear_programa('sup@test.cl','Otro','1802','2026-10-19','2026-10-20','plan.pdf',self.pdf,[self.fila])
    def test_pruebas_y_bloqueos_separados_del_avance(self):
        self.guardar(estado='Terminado',avance=100)
        self.assertEqual(db.lineas([self.trabajo()])[0]['partida'],'Pendiente')
        self.guardar(prueba='Aprobada',detalle_prueba='Prueba de marcha sin carga, sin anomalías',pendiente='Falta retirar herramientas')
        self.assertEqual(db.lineas([self.trabajo()])[0]['partida'],'Pendiente')
        self.guardar(pendiente='')
        self.assertEqual(db.lineas([self.trabajo()])[0]['partida'],'Lista según registros')
        with self.assertRaises(ValueError):self.guardar(estado='Terminado',avance=95)
        with self.assertRaises(ValueError):self.guardar(prueba='No requerida',detalle_prueba='')
    def test_version_cierre_fotos_y_reporte_inmutables(self):
        d=self.trabajo();version=d['version']
        imagen=BytesIO();Image.new('RGB',(100,80),'blue').save(imagen,format='PNG')
        cambio=dict(estado='En ejecución',avance=50,pendiente='Falta montaje',hallazgos='Desgaste en soporte',prueba='Pendiente',detalle_prueba='')
        db.actualizar('sup@test.cl',self.n,d['id'],version,cambio,[('soporte.png',imagen.getvalue())])
        with self.assertRaises(ValueError):db.actualizar('sup@test.cl',self.n,d['id'],version,cambio)
        clave=str(uuid4());i=db.cerrar_turno('sup@test.cl',self.n,'2026-10-17','Día','Continuar montaje',clave)
        self.assertEqual(db.cerrar_turno('sup@test.cl',self.n,'2026-10-17','Día','Continuar montaje',clave),i)
        self.guardar(estado='Terminado',avance=100,pendiente='',prueba='Aprobada',detalle_prueba='Prueba en vacío OK')
        corte=db.cierres('sup@test.cl',self.n)[0]
        self.assertEqual(corte['trabajos'][0]['avance'],50)
        pdf=generar_pdf('sup@test.cl',self.n,corte,True)
        texto=' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn('50%',texto);self.assertIn('Falta montaje',texto);self.assertIn('soporte.png',texto)
        Path('/tmp/neuralmant_reporte_prueba.pdf').write_bytes(pdf)
        self.assertEqual(len(db.evidencia('sup@test.cl',self.n,d['id'])),1)
        with self.assertRaises(ValueError):db.evidencia('fuera@test.cl',self.n,d['id'])
    def test_estimacion_se_calcula_con_plan_validado_en_servidor(self):
        d=self.trabajo();plan=[dict(etapa='Desmontaje',peso=40),dict(etapa='Montaje y prueba',peso=60)]
        cambio=dict(estado='En ejecución',avance=40,pendiente='Montaje',hallazgos='',prueba='Pendiente',detalle_prueba='',origen_avance='estimado_etapas',etapas=plan,plan_nuevo=True,etapas_confirmadas=[1])
        with self.assertRaises(ValueError):db.actualizar('sup@test.cl',self.n,d['id'],d['version'],cambio|{'avance':80})
        db.actualizar('sup@test.cl',self.n,d['id'],d['version'],cambio)
        actual=self.trabajo()
        self.assertEqual(actual['avance'],40)
        self.assertEqual(actual['origen_avance'],'estimado_etapas')
        self.assertEqual(actual['etapas_confirmadas'],[1])
        self.assertEqual(actual['prueba'],'Pendiente')
        with self.assertRaises(ValueError):db.configurar_etapas('admin@test.cl',self.n,d['id'],actual['version'],plan)

    def test_supervisor_y_coordinador_actualizan_ot_de_otra_area_con_autor(self):
        d=self.trabajo()
        with Session(db.engine) as s,s.begin():
            for correo in ['otro@test.cl','coord@test.cl']:
                usuario=s.query(UsuarioRootMine).filter_by(correo=correo).one()
                usuario.area='SERVICIOS'
        for correo in ['otro@test.cl','coord@test.cl']:
            d=self.trabajo()
            cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
            cambio.update(estado='En ejecución',avance=50)
            db.actualizar(correo,self.n,d['id'],d['version'],cambio,mensaje='Revisión de toda la planta')
            actual=self.trabajo()
            self.assertEqual(actual['autor'],correo)
            self.assertEqual(actual['historial'][-1]['usuario'],correo)
            self.assertNotIn('supervisor',actual)
        with self.assertRaises(ValueError):
            db.actualizar('otro@test.cl',self.n,d['id'],d['version'],cambio)
        db.cerrar_turno('coord@test.cl',self.n,'2026-10-17','Noche','',str(uuid4()))
        with self.assertRaises(ValueError):
            db.crear_programa('coord@test.cl','Otro','1802','2026-10-19','2026-10-20','plan.pdf',self.pdf,[self.fila])

    def test_publicar_siguiente_cierra_archiva_y_purga_solo_el_mismo_centro(self):
        from datetime import timedelta
        d=self.trabajo()
        foto=BytesIO();Image.new('RGB',(150,100),'orange').save(foto,format='PNG')
        cambio=dict(estado='En ejecución',avance=50,pendiente='Falta montaje',hallazgos='Desgaste en soporte',prueba='Pendiente',detalle_prueba='')
        db.actualizar('sup@test.cl',self.n,d['id'],d['version'],cambio,[('evidencia.png',foto.getvalue())],mensaje='Cambio parcial realizado, falta montaje')
        db.cerrar_turno('sup@test.cl',self.n,'2026-10-17','Noche','Continuar montaje',str(uuid4()),sugerencias='Coordinar apoyo en la partida')
        fila_otro=dict(self.fila,supervisor='fuera@test.cl')
        otro=db.crear_programa('admin@test.cl','Otra planta','1803','2026-10-17','2026-10-18','plan.pdf',self.pdf,[fila_otro])
        with patch('reportes.trabajos.render_pdf',side_effect=RuntimeError('Falla generando PDF')):
            with self.assertRaises(RuntimeError):
                db.crear_programa('prog@test.cl','Siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        self.assertEqual(len(db.trabajos('sup@test.cl',self.n)),1)
        self.assertEqual(len(db.programas('sup@test.cl')),1)
        siguiente=db.crear_programa('prog@test.cl','Siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        self.assertGreater(siguiente,self.n)
        pdf=db.historico_pdf('sup@test.cl',self.n)
        Path('/tmp/neuralmant475-final.pdf').write_bytes(pdf)
        lector=PdfReader(BytesIO(pdf));texto=' '.join(pg.extract_text() for pg in lector.pages)
        for esperado in ['50%','Falta montaje','Coordinar apoyo en la partida','evidencia.png']:
            self.assertIn(esperado,texto)
        self.assertTrue(any(len(pg.images)>0 for pg in lector.pages))
        actual=db.programas('sup@test.cl');self.assertTrue(next(p for p in actual if p['id']==self.n)['cerrado'])
        self.assertEqual(db.trabajos('sup@test.cl',self.n),[])
        self.assertEqual(len(db.trabajos('fuera@test.cl',otro)),1)
        with self.assertRaises(ValueError):db.historico_pdf('fuera@test.cl',self.n)
        for accion in [lambda:db.actualizar('admin@test.cl',self.n,d['id'],d['version'],cambio),lambda:db.configurar_etapas('admin@test.cl',self.n,d['id'],d['version'],[dict(etapa='A',peso=50),dict(etapa='B',peso=50)]),lambda:db.cerrar_turno('sup@test.cl',self.n,'2026-10-17','Día','',str(uuid4()))]:
            with self.assertRaisesRegex(ValueError,'cerrado'):accion()
        with Session(db.engine) as s:
            self.assertEqual(s.query(db.FotoTrabajo).count(),0)
            self.assertEqual(s.query(db.CierreTrabajo).count(),0)
            self.assertEqual(s.get(db.ProgramaFinSemana,self.n).pdf,b'')
            archivo=s.get(db.HistoricoTrabajo,self.n);vence=archivo.vence
        with patch('database.trabajos.datetime') as reloj:
            reloj.utcnow.return_value=vence-timedelta(seconds=1)
            self.assertEqual(db.limpiar_historial(),0)
            reloj.utcnow.return_value=vence
            self.assertEqual(db.limpiar_historial(),1)
        with Session(db.engine) as s:
            self.assertIsNone(s.get(db.HistoricoTrabajo,self.n))
            self.assertIsNone(s.get(db.ProgramaFinSemana,self.n))
            self.assertIsNotNone(s.get(db.ProgramaFinSemana,siguiente))

    def test_retencion_tres_meses_calendario(self):
        from datetime import datetime
        self.assertEqual(db._tres_meses(datetime(2026,11,30)),datetime(2027,2,28))

    def test_publicar_por_area_sin_linea_equipo_ni_asignacion(self):
        fila=dict(descripcion='Pintura paneles cielo',area='Faena',linea='',equipo='')
        n=db.crear_programa('prog@test.cl','Programa por área','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[fila])
        d=db.trabajos('otro@test.cl',n)[0]
        self.assertEqual(d['area'],'Faena')
        self.assertEqual(d['linea'],'')
        self.assertEqual(d['equipo'],'')
        self.assertNotIn('supervisor',d)
        cambio={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        cambio.update(estado='En ejecución',avance=50)
        db.actualizar('otro@test.cl',n,d['id'],d['version'],cambio,mensaje='Pintura iniciada')
        d=db.trabajos('coord@test.cl',n)[0]
        self.assertEqual(d['historial'][-1]['usuario'],'otro@test.cl')
        self.assertEqual(d['historial'][-1]['nombre'],'otro@test.cl')
        self.assertEqual(d['historial'][-1]['rol'],'supervisor')
        self.assertTrue(d['historial'][-1]['fecha'])
        with self.assertRaisesRegex(ValueError,'area'):
            db.crear_programa('prog@test.cl','Inválido','1802','2026-10-31','2026-11-01','plan.pdf',self.pdf,[fila|{'area':''}])

    def test_lineas_no_mezclan_areas_y_admiten_trabajos_generales(self):
        base=self.trabajo()
        filas=[base|{'area':'Faena','linea':'L1','avance':100,'estado':'Terminado','prueba':'Aprobada'},base|{'area':'Procesos','linea':'L1'},base|{'area':'Faena','linea':''}]
        grupos=db.lineas(filas)
        self.assertEqual(len(grupos),3)
        self.assertEqual(next(g for g in grupos if g['línea']=='Faena · L1')['partida'],'Lista según registros')
        self.assertEqual(next(g for g in grupos if g['línea']=='Procesos · L1')['partida'],'Pendiente')
        self.assertTrue(any(g['línea']=='Faena · Sin línea informada' for g in grupos))

    def _encolar(self,mensaje):
        d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        version=db.actualizar('sup@test.cl',self.n,d['id'],d['version'],c,mensaje=mensaje)
        ident=db.encolar_novedad('sup@test.cl',self.n,d['id'],version,mensaje)
        return ident,db.tomar_novedad()

    def test_cola_persistente_aplica_sin_confirmacion_y_conserva_mensaje(self):
        ident,job=self._encolar('Montaje iniciado')
        self.assertIsNone(db.tomar_novedad())
        self.assertEqual(db.ultima_novedad('sup@test.cl',self.n,job['ident'])['estado'],'procesando')
        db.resultado_novedad(job,dict(estado='En ejecución',avance=40,origen_avance='informado_supervisor'))
        d=self.trabajo()
        self.assertEqual(d['avance'],40)
        self.assertEqual(d['ultimo_mensaje'],'Montaje iniciado')
        self.assertEqual(d['autor'],'sup@test.cl')
        self.assertEqual(db.ultima_novedad('sup@test.cl',self.n,d['id'])['estado'],'lista')

    def test_cola_pregunta_solo_lo_faltante_y_usa_respuesta(self):
        ident,job=self._encolar('Quedó listo')
        db.resultado_novedad(job,dict(pregunta='¿Terminó toda la pega o solo el montaje?'))
        self.assertEqual(self.trabajo()['avance'],0)
        self.assertEqual(db.ultima_novedad('sup@test.cl',self.n,job['ident'])['estado'],'pregunta')
        siguiente,job2=self._encolar('Terminó toda la pega, falta probar')
        self.assertIn('solo el montaje',job2['contexto'])
        self.assertEqual(job2['mensaje'],'Terminó toda la pega, falta probar')
        db.resultado_novedad(job2,dict(estado='Terminado'))
        self.assertEqual(self.trabajo()['avance'],100)
        self.assertEqual(self.trabajo()['prueba'],'Pendiente')

    def test_cola_no_sobrescribe_otro_supervisor_y_purga_al_archivar(self):
        ident,job=self._encolar('Montaje iniciado')
        d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
        c.update(estado='En ejecución',avance=60)
        db.actualizar('otro@test.cl',self.n,d['id'],d['version'],c,mensaje='Avance 60%')
        db.resultado_novedad(job,dict(estado='En ejecución',avance=30,origen_avance='informado_supervisor'))
        self.assertEqual(self.trabajo()['avance'],60)
        self.assertEqual(db.ultima_novedad('sup@test.cl',self.n,d['id'])['estado'],'error')
        db.crear_programa('prog@test.cl','Nueva','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        with Session(db.engine) as s:self.assertEqual(s.query(db.NovedadIA).count(),0)
        db.resultado_novedad(job,dict(estado='Terminado'))  # A late worker cannot reopen the archived program.

    def test_cola_recupera_proceso_interrumpido_sin_aplicar_token_antiguo(self):
        from datetime import datetime,timedelta
        ident,primero=self._encolar('Montaje iniciado')
        with Session(db.engine) as s,s.begin():s.get(db.NovedadIA,ident).actualizado=datetime.utcnow()-timedelta(minutes=3)
        segundo=db.tomar_novedad()
        self.assertNotEqual(primero['token'],segundo['token'])
        db.resultado_novedad(primero,dict(estado='Terminado'))
        self.assertEqual(self.trabajo()['avance'],0)
        db.resultado_novedad(segundo,dict(estado='En ejecución',avance=40,origen_avance='informado_supervisor'))
        self.assertEqual(self.trabajo()['avance'],40)

    def test_importacion_propuesta_necesita_revision(self):
        texto=texto_pdf(self.pdf);self.assertIn('rodamiento',texto)
        with patch('modulos.programacion_pdf._generar',return_value=ProgramacionExtraida(trabajos=[TrabajoExtraido(descripcion='Cambio de rodamiento',linea='L1')])):
            filas=extraer_trabajos(texto)
        self.assertNotIn('supervisor',filas[0])
        with self.assertRaises(ValueError):db.crear_programa('admin@test.cl','Prueba','1802','2026-10-19','2026-10-20','plan.pdf',self.pdf,filas)
        with self.assertRaises(ValueError):extraer_trabajos('')

    def test_finalizacion_guarda_pregunta_y_prueba_se_puede_posponer_y_retomar(self):
        self.guardar(estado='Terminado',avance=100)
        d=self.trabajo()
        self.assertEqual(d['dialogo_prueba']['paso'],'realizacion')
        db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],'posponer_prueba')
        d=self.trabajo()
        self.assertEqual(d['estado'],'Terminado');self.assertEqual(d['prueba'],'Pendiente')
        self.assertTrue(d['dialogo_prueba']['postergada'])
        self.assertIn('aún no se han realizado',d['detalle_prueba'])
        db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],'iniciar_prueba')
        d=self.trabajo()
        db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],'sin_observaciones')
        d=self.trabajo();self.assertEqual(d['prueba'],'Aprobada')
        with self.assertRaises(ValueError):db.registrar_prueba('sup@test.cl',self.n,d['id'],d['version'],'posponer_prueba')

    def test_cinco_fotos_de_la_misma_actividad_en_pdf_y_archivo_final(self):
        fotos=[]
        for i in range(5):
            salida=BytesIO();Image.new('RGB',(100+i,80),(30*i,80,160)).save(salida,format='PNG')
            fotos.append((f'foto_{i+1}.png',salida.getvalue()))
        for lote in [fotos[:3],fotos[3:]]:
            d=self.trabajo();c={k:d[k] for k in ('estado','avance','pendiente','hallazgos','prueba','detalle_prueba')}
            db.actualizar('sup@test.cl',self.n,d['id'],d['version'],c,lote,mensaje='Registro con fotos')
        d=self.trabajo();self.assertEqual(len(d['fotos']),5)
        self.assertEqual(len(db.evidencia('sup@test.cl',self.n,d['id'])),5)
        corte=dict(titulo='Evidencia',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=[d],novedades_area=[])
        pdf=generar_pdf('sup@test.cl',self.n,corte,True)
        Path('/tmp/fotos4816-cinco.pdf').write_bytes(pdf)
        lector=PdfReader(BytesIO(pdf));texto=' '.join(' '.join(p.extract_text().split()) for p in lector.pages)
        self.assertIn('Se incluyen 5 de 5',texto)
        for i in range(5):self.assertIn(f'foto_{i+1}.png',texto)
        self.assertEqual(sum(len(p.images) for p in lector.pages),5)
        recuperada=db.evidencia('sup@test.cl',self.n,d['id'])[:1]
        with patch('database.trabajos.evidencia',return_value=recuperada):
            parcial=PdfReader(BytesIO(generar_pdf('sup@test.cl',self.n,corte,True)))
        aviso=' '.join(' '.join(p.extract_text().split()) for p in parcial.pages)
        self.assertIn('Se incluyen 1 de 5',aviso);self.assertIn('faltan imágenes por recuperar',aviso)
        db.crear_programa('admin@test.cl','Siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        lector=PdfReader(BytesIO(db.historico_pdf('sup@test.cl',self.n)))
        texto=' '.join(' '.join(p.extract_text().split()) for p in lector.pages)
        for i in range(5):self.assertIn(f'foto_{i+1}.png',texto)
        self.assertEqual(sum(len(p.images) for p in lector.pages),5)
