import io
import zipfile

from odoo.tests.common import SavepointCase, tagged

from ..models.flota_360_carga_pdf import pdfs_de_zip, tipo_archivo

PDF = b'%PDF-1.4\n%fake\n'


def zip_de(archivos):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for nombre, datos in archivos:
            zf.writestr(nombre, datos)
    return buf.getvalue()


@tagged('post_install', '-at_install')
class TestCargaPdfFlota360(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref('adt_comercial.group_access_adt_comercial_gerencia')
        cls.service = cls.env['adt.flota360']

    def subir(self, lote_id, nombre, datos):
        return self.env['ir.attachment'].create({'name': nombre, 'raw': datos,
                                                 'res_model': 'adt.financiera.carga.pdf', 'res_id': lote_id})

    def test_tipo_por_contenido(self):
        self.assertEqual(tipo_archivo('x', PDF), 'pdf')
        # Un ZIP sin comprimir lleva «%PDF» de sus PDFs en los primeros bytes: sigue siendo ZIP.
        self.assertEqual(tipo_archivo('x.pdf', zip_de([('a.pdf', PDF)])), 'zip')
        self.assertIsNone(tipo_archivo('foto.pdf', b'\xff\xd8\xff\xe0JFIF'))

    def test_zip_con_subcarpetas_y_zip_anidado(self):
        interno = zip_de([('c.pdf', PDF)])
        pdfs, ignorados = pdfs_de_zip(zip_de([
            ('lote/a.pdf', PDF), ('lote/sub/b', PDF), ('lote/foto.jpg', b'\xff\xd8'),
            ('__MACOSX/lote/._a.pdf', b'x'), ('otro.zip', interno),
        ]))
        self.assertEqual(sorted(n for n, _d in pdfs), ['a.pdf', 'b.pdf', 'c.pdf'])
        self.assertEqual([n for n, _m in ignorados], ['foto.jpg'])

    def test_agregar_pone_en_cola_y_tanda_lee(self):
        lote_id = self.service.carga_crear(reemplazar=True)
        sin_ext = self.subir(lote_id, 'cronograma', PDF)
        zip_att = self.subir(lote_id, 'lote.zip', zip_de([('x.pdf', PDF), ('y.PDF', PDF), ('nota.txt', b'hola')]))
        foto = self.subir(lote_id, 'foto.png', b'\x89PNG\r\n')
        r = self.service.carga_agregar(lote_id, [sin_ext.id, zip_att.id, foto.id])
        por_id = {a['id']: a for a in r['archivos']}
        self.assertEqual(por_id[sin_ext.id]['tipo'], 'pdf')
        self.assertEqual(por_id[sin_ext.id]['lineas'][0]['archivo'], 'cronograma.pdf')
        self.assertEqual(len(por_id[zip_att.id]['lineas']), 2)
        self.assertEqual([i['name'] for i in por_id[zip_att.id]['ignorados']], ['nota.txt'])
        self.assertIsNone(por_id[foto.id]['tipo'])
        self.assertFalse(zip_att.exists() or foto.exists())
        self.assertEqual(r['totales']['pendiente'], 3)

        # La vista lee por tandas: los PDFs falsos terminan con error, sin quedar en cola.
        t = self.service.carga_tanda(lote_id, limite=2)
        self.assertEqual(len(t['lineas']), 2)
        t = self.service.carga_tanda(lote_id, limite=2)
        self.assertEqual(t['totales']['pendiente'], 0)
        self.assertEqual(t['totales']['error'], 3)

        # Reintentar los vuelve a la cola.
        rr = self.service.carga_reintentar(lote_id)
        self.assertEqual(len(rr['lineas']), 3)
        self.assertEqual(rr['totales']['pendiente'], 3)

    def test_historial_y_detalle(self):
        lote_id = self.service.carga_crear()
        self.service.carga_agregar(lote_id, [self.subir(lote_id, 'a.pdf', PDF).id])
        self.assertIn(lote_id, [l['id'] for l in self.service.carga_historial()])
        lote = self.service.carga_lote(lote_id)
        self.assertEqual([l['archivo'] for l in lote['lineas']], ['a.pdf'])
