# -*- coding: utf-8 -*-
"""Carga de cronogramas de la financiera (acción JS: adt_flota_360_carga_pdf).

Vista de Flota 360 sobre la carga masiva de adt_comercial (adt.financiera.carga.pdf),
que sigue haciendo la lectura del plan de pagos, la búsqueda del cliente por DNI y la
carga en la moto. Aquí cada subida es un lote: los PDFs pasan a la cola al subirse y la
vista los procesa en tandas pequeñas para mostrar en vivo con qué cliente, cuenta y moto
quedó vinculado cada uno. Si la vista se cierra a medias, termina el cron.

Aquí se agrega lo que la vista necesita para aceptar todos los formatos en que llegan
los cronogramas: PDFs sueltos (con o sin extensión), ZIPs con PDFs (incluso en
subcarpetas o ZIPs dentro de ZIPs) y carpetas completas (las recorre el navegador).
"""
import io
import os
import zipfile

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

GRUPO_GERENCIA = 'adt_comercial.group_access_adt_comercial_gerencia'
MAX_LOTES = 50
TANDA_MAX = 5                          # PDFs por llamada de la vista (respuesta en ~1-3 s)
MAX_ZIP_PROFUNDIDAD = 3
MAX_ZIP_BYTES = 300 * 1024 * 1024   # tamaño descomprimido máximo de un ZIP (evita bombas zip)
FIRMA_PDF = b'%PDF'
FIRMA_ZIP = (b'PK\x03\x04', b'PK\x05\x06')
# Archivos que el sistema de archivos agrega a los ZIP y no son del usuario.
BASURA_ZIP = ('__MACOSX/', '.DS_Store', 'Thumbs.db', 'desktop.ini')


def tipo_archivo(nombre, contenido):
    """'pdf', 'zip' o None según el contenido (la extensión puede faltar o mentir)."""
    cabeza = (contenido or b'')[:1024]
    # Primero el ZIP: uno sin comprimir lleva el «%PDF» de sus PDFs en los primeros bytes.
    if cabeza[:4] in FIRMA_ZIP:
        return 'zip'
    if FIRMA_PDF in cabeza:
        return 'pdf'
    return None


def pdfs_de_zip(contenido, nombre_zip='', profundidad=0):
    """[(nombre, bytes)] de los PDFs de un ZIP, y [(nombre, motivo)] de lo que se ignoró."""
    pdfs, ignorados = [], []
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        return pdfs, [(nombre_zip, _('El ZIP está dañado o no es un ZIP.'))]
    total = sum(i.file_size for i in zf.infolist())
    if total > MAX_ZIP_BYTES:
        return pdfs, [(nombre_zip, _('El ZIP descomprimido pesa más de %s MB.') % (MAX_ZIP_BYTES // 1048576))]
    for info in zf.infolist():
        ruta = info.filename
        base = os.path.basename(ruta.rstrip('/'))
        if info.is_dir() or not base or base.startswith('._') or any(b in ruta for b in BASURA_ZIP):
            continue
        if info.flag_bits & 0x1:
            ignorados.append((base, _('Está protegido con contraseña.')))
            continue
        try:
            datos = zf.read(info)
        except Exception as e:  # noqa: BLE001 — un miembro dañado no debe frenar el resto
            ignorados.append((base, _('No se pudo extraer: %s') % e))
            continue
        tipo = tipo_archivo(base, datos)
        if tipo == 'pdf':
            pdfs.append((base if base.lower().endswith('.pdf') else base + '.pdf', datos))
        elif tipo == 'zip' and profundidad < MAX_ZIP_PROFUNDIDAD:
            sub_pdfs, sub_ign = pdfs_de_zip(datos, base, profundidad + 1)
            pdfs += sub_pdfs
            ignorados += sub_ign
        else:
            ignorados.append((base, _('No es un PDF.')))
    return pdfs, ignorados


class AdtFlota360CargaPdf(models.AbstractModel):
    _inherit = 'adt.flota360'

    def _carga_check(self):
        if not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(_('Solo gerencia puede cargar los cronogramas de la financiera.'))
        return self.env['adt.financiera.carga.pdf'].with_context(carga_sin_cron=True)

    def _carga_lote(self, carga_id):
        lote = self._carga_check().browse(int(carga_id)).exists()
        if not lote:
            raise UserError(_('La carga ya no existe.'))
        return lote

    def _carga_linea_dict(self, l):
        v = l.vehiculo_id
        return {
            'id': l.id, 'attachment_id': l.attachment_id.id or False, 'archivo': l.nombre_archivo or '',
            'size': l.attachment_id.file_size or 0, 'state': l.state, 'mensaje': l.mensaje or '',
            'dni': l.dni or '', 'socio': l.socio_pdf or '',
            'cliente': l.partner_id.display_name or '', 'cuenta': l.cuenta_id.reference_no or '',
            'cuenta_id': l.cuenta_id.id or False,
            'vehiculo_id': v.id or False, 'placa': v.license_plate or v.display_name or '',
            'deuda': l.situacion_deuda or '', 'cuotas': l.cuotas_pdf, 'monto': l.monto_credito,
            'lectura': l.cf_estado or '', 'confianza': l.confianza,
        }

    def _carga_totales(self, lote):
        return {
            'total': lote.total, 'pendiente': lote.total_pendiente, 'cargado': lote.total_cargado,
            'atencion': lote.total_sin_cliente + lote.total_revisar + lote.total_error,
            'sin_cliente': lote.total_sin_cliente, 'revisar': lote.total_revisar, 'error': lote.total_error,
            'omitido': lote.total_omitido,
        }

    def _carga_lote_dict(self, lote, lineas=True):
        d = {'id': lote.id, 'name': lote.name, 'state': lote.state, 'reemplazar': lote.reemplazar,
             'autor': lote.create_uid.name or '', 'fecha': fields.Datetime.to_string(lote.create_date),
             'totales': self._carga_totales(lote)}
        if lineas:
            d['lineas'] = [self._carga_linea_dict(l) for l in lote.linea_ids]
        return d

    # ------------------------------------------------------------------ lectura

    @api.model
    def carga_historial(self):
        """Cargas anteriores, la más reciente primero."""
        return [self._carga_lote_dict(l, lineas=False) for l in self._carga_check().search([], limit=MAX_LOTES)]

    @api.model
    def carga_lote(self, carga_id):
        return self._carga_lote_dict(self._carga_lote(carga_id))

    @api.model
    def carga_lineas(self, carga_id, linea_ids):
        lote = self._carga_lote(carga_id)
        lineas = lote.linea_ids.filtered(lambda l: l.id in linea_ids)
        return {'lineas': [self._carga_linea_dict(l) for l in lineas], 'totales': self._carga_totales(lote)}

    # ------------------------------------------------------------------ subida y proceso

    @api.model
    def carga_crear(self, reemplazar=True):
        return self._carga_check().create({'reemplazar': bool(reemplazar)}).id

    @api.model
    def carga_opciones(self, carga_id, reemplazar):
        self._carga_lote(carga_id).reemplazar = bool(reemplazar)
        return True

    @api.model
    def carga_agregar(self, carga_id, attachment_ids):
        """Agrega a la carga los archivos subidos y los deja en cola para leerse.

        Los ZIP se abren y se agregan sus PDFs; lo que no es PDF se descarta. Devuelve, por
        archivo subido, su tipo, los PDFs que aportó (con su línea) y lo que se ignoró."""
        lote = self._carga_lote(carga_id)
        Att = self.env['ir.attachment']
        nuevos, resultado = Att, []
        for att in Att.browse(attachment_ids).exists():
            if att.res_model != lote._name or att.res_id != lote.id:
                continue  # solo archivos subidos a esta carga
            contenido = att.raw or b''
            tipo = tipo_archivo(att.name, contenido)
            item = {'id': att.id, 'name': att.name, 'tipo': tipo, 'pdfs': [], 'ignorados': []}
            resultado.append(item)
            if tipo == 'pdf':
                if not (att.name or '').lower().endswith('.pdf'):
                    att.write({'name': (att.name or 'documento') + '.pdf', 'mimetype': 'application/pdf'})
                nuevos |= att
                item['pdfs'] = [att.id]
                continue
            if tipo == 'zip':
                pdfs, ignorados = pdfs_de_zip(contenido, att.name)
                creados = Att.create([{
                    'name': nombre, 'raw': datos, 'mimetype': 'application/pdf',
                    'res_model': lote._name, 'res_id': lote.id,
                } for nombre, datos in pdfs]) if pdfs else Att
                nuevos |= creados
                item['pdfs'] = creados.ids
                item['ignorados'] = [{'name': n, 'motivo': m} for n, m in ignorados]
            else:
                item['ignorados'] = [{'name': att.name, 'motivo': _('No es un PDF ni un ZIP.')}]
            att.unlink()
        if nuevos:
            lote.write({'attachment_ids': [(4, a.id) for a in nuevos]})
            lote.action_procesar()  # crea una línea por PDF (repetidos: «Omitido»), sin cron
        por_att = {l.attachment_id.id: self._carga_linea_dict(l) for l in lote.linea_ids if l.attachment_id in nuevos}
        for item in resultado:
            item['lineas'] = [por_att[a] for a in item['pdfs'] if a in por_att]
        return {'archivos': resultado, 'totales': self._carga_totales(lote)}

    @api.model
    def carga_tanda(self, carga_id, limite=3):
        """Lee los siguientes PDFs en cola (los que el cron no tenga tomados) y devuelve su resultado."""
        lote = self._carga_lote(carga_id)
        limite = max(1, min(int(limite), TANDA_MAX))
        hechas = self.env['adt.financiera.carga.pdf.linea']
        for linea in lote.linea_ids.filtered(lambda l: l.state == 'pendiente'):
            if len(hechas) >= limite:
                break
            hechas |= lote._procesar_lineas(linea, commit=False)  # salta las que tenga el cron
        lote._cerrar_terminados()
        return {'lineas': [self._carga_linea_dict(l) for l in hechas], 'totales': self._carga_totales(lote)}

    @api.model
    def carga_reintentar(self, carga_id, linea_ids=None):
        """Vuelve a la cola los PDFs con problema (o los indicados)."""
        lote = self._carga_lote(carga_id)
        lineas = lote.linea_ids.filtered(lambda l: l.state in ('error', 'sin_cliente', 'revisar')
                                         and (not linea_ids or l.id in linea_ids))
        lineas.write({'state': 'pendiente', 'mensaje': False})
        if lineas:
            lote.state = 'procesando'
        return {'lineas': [self._carga_linea_dict(l) for l in lineas], 'totales': self._carga_totales(lote)}

    @api.model
    def carga_segundo_plano(self, carga_id):
        """La vista se cerró con PDFs en cola: los termina el cron."""
        lote = self._carga_lote(carga_id)
        if lote.total_pendiente:
            lote.with_context(carga_sin_cron=False)._disparar_cron()
        return True
