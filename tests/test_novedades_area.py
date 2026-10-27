import unittest,json
from uuid import uuid4
from io import BytesIO
from sqlalchemy import select
from sqlalchemy.orm import Session
from pypdf import PdfReader
from database import trabajos as db,novedades_area as area
from motores.foco_partida import focos,senales
from ia.resumen_turno import resumen_base
import test_trabajos as fixtures

class NovedadesAreaTest(unittest.TestCase):
    setUp=fixtures.TrabajosTest.setUp
    tearDown=fixtures.TrabajosTest.tearDown
    trabajo=fixtures.TrabajosTest.trabajo
    def test_novedad_sin_trabajo_conserva_autor_y_no_modifica_avance(self):
        antes=self.trabajo();clave=str(uuid4())
        ident=area.guardar('sup@test.cl',self.n,'Faena','Hallazgo de calidad: producto expuesto',clave,impacto='Partida')
        self.assertEqual(area.guardar('sup@test.cl',self.n,'Faena','Hallazgo de calidad: producto expuesto',clave,impacto='Partida'),ident)
        registros=area.listar('tec@test.cl',self.n)
        self.assertEqual(len(registros),1);self.assertEqual(registros[0]['usuario'],'sup@test.cl');self.assertEqual(registros[0]['categoria'],'Calidad')
        self.assertEqual(self.trabajo(),antes)
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Faena','Texto diferente',clave)
    def test_permisos_area_centro_y_cierre(self):
        for correo in ['prog@test.cl','tec@test.cl','fuera@test.cl']:
            with self.assertRaises(ValueError):area.guardar(correo,self.n,'Faena','Hallazgo',str(uuid4()))
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Otra área','Hallazgo',str(uuid4()))
        ident=area.guardar('coord@test.cl',self.n,'Faena','Riesgo de atrapamiento sin resguardo',str(uuid4()),impacto='Partida')
        resuelto=area.guardar('otro@test.cl',self.n,'Faena','Resguardo repuesto y verificado',str(uuid4()),resuelve=ident)
        registros=area.listar('sup@test.cl',self.n)
        self.assertEqual(registros[0]['estado'],'Resuelto');self.assertEqual(registros[0]['cierre']['usuario'],'otro@test.cl')
        self.assertEqual(registros[1]['resuelve'],ident)
        self.assertEqual(focos([self.trabajo()],registros)['partida'],[])
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Faena','Otra resolución',str(uuid4()),resuelve=ident)
    def test_hallazgo_archivado_en_pdf_y_filas_purgadas(self):
        area.guardar('sup@test.cl',self.n,'Faena','Hallazgo de calidad: contaminación en zona',str(uuid4()),impacto='Partida')
        db.crear_programa('admin@test.cl','Semana siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        texto='\n'.join(p.extract_text() for p in PdfReader(BytesIO(db.historico_pdf('sup@test.cl',self.n))).pages)
        self.assertIn('contaminación en zona',texto)
        with Session(db.engine) as s:self.assertEqual(list(s.scalars(select(db.NovedadArea).where(db.NovedadArea.programa==self.n))),[])
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Faena','No puede editarse',str(uuid4()))
    def test_focos_por_nombre_y_sin_inventar_entrega_tardia(self):
        d=self.trabajo();d.update(descripcion='Cambio de rodamiento del transportador',estado='Terminado',avance=100,prueba='Aprobada',detalle_prueba='Normal',actualizado='2026-10-25T23:00:00',fin_plan='18-oct-26')
        self.assertEqual(focos([d])['retrasos'],[])
        d['historial']=[dict(nombre='Supervisor',fecha='2026-10-18T12:00:00',mensaje='El cambio de rodamiento se entregó tarde por falta de repuesto')]
        f=focos([d]);self.assertIn('Cambio de rodamiento',f['retrasos'][0]['referencia']);self.assertNotIn('OT',f['retrasos'][0]['referencia'])
        self.assertNotIn('Retraso',senales('Sin retrasos ni observaciones'))
        self.assertIn('Retraso',senales('El motor se entregó 2 horas tarde'))
        self.assertNotIn('Retraso',senales('Se revisó el motor hoy en la tarde'))
        resumen=resumen_base([d]);self.assertIn('Cambio de rodamiento',resumen['comentario'])

    def test_reinicio_crea_tabla_nueva_sobre_base_existente(self):
        from unittest.mock import patch
        from sqlalchemy import inspect
        from database.conexion import crear_tablas
        db.NovedadArea.__table__.drop(db.engine)
        with patch('database.conexion.engine',db.engine):crear_tablas()
        self.assertIn('novedad_area_trabajo',inspect(db.engine).get_table_names())
        area.guardar('sup@test.cl',self.n,'Faena','Novedad posterior a actualización',str(uuid4()))
        self.assertEqual(len(area.listar('sup@test.cl',self.n)),1)

    def test_fotos_area_reintento_pdf_y_archivo_final(self):
        from PIL import Image
        from reportes.trabajos import generar_pdf
        import base64
        out=BytesIO();Image.new('RGB',(120,90),'orange').save(out,format='PNG')
        foto=('hallazgo.png',out.getvalue());clave=str(uuid4())
        args=('sup@test.cl',self.n,'Faena','Fuga observada junto al transportador',clave)
        ident=area.guardar(*args,categoria='Operación',fotos=[foto])
        self.assertEqual(area.guardar(*args,categoria='Operación',fotos=[foto]),ident)
        registros=area.listar('sup@test.cl',self.n)
        self.assertEqual(len(registros),1)
        self.assertEqual(registros[0]['fotos'][0]['nombre'],'hallazgo.png')
        Image.open(BytesIO(base64.b64decode(registros[0]['fotos'][0]['contenido']))).verify()
        corte=dict(titulo='Prueba',centro='1802',fecha='2026-10-17',turno='Día',generado='2026-10-17T12:00:00',nombre='Supervisor',trabajos=[self.trabajo()],novedades_area=registros)
        lector=PdfReader(BytesIO(generar_pdf('sup@test.cl',self.n,corte,True)))
        self.assertTrue(any(len(p.images)>0 for p in lector.pages))
        self.assertNotIn('Impacto:', ' '.join(p.extract_text() for p in lector.pages))
        db.crear_programa('admin@test.cl','Siguiente','1802','2026-10-24','2026-10-25','plan.pdf',self.pdf,[self.fila])
        lector=PdfReader(BytesIO(db.historico_pdf('sup@test.cl',self.n)))
        self.assertTrue(any(len(p.images)>0 for p in lector.pages))

    def test_rechaza_fotos_invalidas_y_exceso_sin_guardado_parcial(self):
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Faena','Novedad',str(uuid4()),fotos=[('falsa.png',b'no es imagen')])
        with self.assertRaises(ValueError):area.guardar('sup@test.cl',self.n,'Faena','Novedad',str(uuid4()),fotos=[('falsa.png',b'')]*4)
        self.assertEqual(area.listar('sup@test.cl',self.n),[])

    def test_cinco_imagenes_area_en_varias_novedades_se_incluyen_todas(self):
        from PIL import Image
        from reportes.trabajos import generar_pdf
        fotos=[]
        for i in range(5):
            out=BytesIO();Image.new('RGB',(90+i,60),(50,35*i,200)).save(out,format='PNG')
            fotos.append((f'area_{i+1}.png',out.getvalue()))
        for lote in [fotos[:3],fotos[3:]]:area.guardar('sup@test.cl',self.n,'Faena','Hallazgo con evidencia',str(uuid4()),categoria='Calidad',fotos=lote)
        registros=area.listar('sup@test.cl',self.n)
        self.assertEqual(sum(len(a['fotos']) for a in registros),5)
        corte=dict(titulo='Evidencia de área',centro='1802',fecha='2026-10-18',turno='Día',generado='2026-10-18T12:00:00',nombre='Supervisor',trabajos=[self.trabajo()],novedades_area=registros)
        lector=PdfReader(BytesIO(generar_pdf('sup@test.cl',self.n,corte,True)))
        texto=' '.join(' '.join(p.extract_text().split()) for p in lector.pages)
        self.assertIn('Se incluyen 5 de 5',texto)
        for i in range(5):self.assertIn(f'area_{i+1}.png',texto)
        self.assertEqual(sum(len(p.images) for p in lector.pages),5)
