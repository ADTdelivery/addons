import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from odoo import _, api, fields, models
from odoo.exceptions import UserError

MAX_RECORTE = 45       # % máximo a recortar por lado
LADO_VISTA_PREVIA = 800  # px del lado mayor de la vista previa


def procesar_imagen(imagen_b64, rotacion=0, arriba=0, abajo=0, izquierda=0, derecha=0, lado_maximo=None):
    """Endereza la imagen según su EXIF, la rota `rotacion` grados en sentido
    horario, recorta los porcentajes indicados por lado y la devuelve en base64."""
    try:
        img = Image.open(io.BytesIO(base64.b64decode(imagen_b64)))
        formato = img.format
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, ValueError, OSError):
        raise UserError(_('El archivo cargado no es una imagen válida.'))

    if rotacion % 360:
        img = img.rotate(-(rotacion % 360), expand=True)

    ancho, alto = img.size
    img = img.crop((
        ancho * izquierda // 100,
        alto * arriba // 100,
        ancho - ancho * derecha // 100,
        alto - alto * abajo // 100,
    ))
    if lado_maximo:
        img.thumbnail((lado_maximo, lado_maximo))

    salida = io.BytesIO()
    if formato == 'PNG':
        img.save(salida, 'PNG', optimize=True)
    else:
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(salida, 'JPEG', quality=90, optimize=True)
    return base64.b64encode(salida.getvalue())


class AdtExpedienteImagenWizard(models.TransientModel):
    _name = 'adt.expediente.imagen.wizard'
    _description = 'Editar imagen del expediente (rotar / recortar)'

    expediente_id = fields.Many2one('adt.expediente', required=True, ondelete='cascade')
    campo = fields.Char(required=True)
    campo_label = fields.Char(string='Imagen', readonly=True)
    imagen_original = fields.Binary(attachment=False)

    rotacion = fields.Integer(string='Rotación (°)', default=0, readonly=True)
    recorte_arriba = fields.Integer(string='Arriba (%)', default=0)
    recorte_abajo = fields.Integer(string='Abajo (%)', default=0)
    recorte_izquierda = fields.Integer(string='Izquierda (%)', default=0)
    recorte_derecha = fields.Integer(string='Derecha (%)', default=0)

    vista_previa = fields.Binary(string='Vista previa', compute='_compute_vista_previa')

    def _parametros(self):
        for valor in (self.recorte_arriba, self.recorte_abajo, self.recorte_izquierda, self.recorte_derecha):
            if valor < 0 or valor > MAX_RECORTE:
                raise UserError(_('El recorte por lado debe estar entre 0%% y %s%%.') % MAX_RECORTE)
        return {
            'rotacion': self.rotacion,
            'arriba': self.recorte_arriba,
            'abajo': self.recorte_abajo,
            'izquierda': self.recorte_izquierda,
            'derecha': self.recorte_derecha,
        }

    @api.depends('imagen_original', 'rotacion', 'recorte_arriba', 'recorte_abajo',
                 'recorte_izquierda', 'recorte_derecha')
    def _compute_vista_previa(self):
        for wizard in self:
            if not wizard.imagen_original:
                wizard.vista_previa = False
                continue
            try:
                wizard.vista_previa = procesar_imagen(
                    wizard.imagen_original, lado_maximo=LADO_VISTA_PREVIA, **wizard._parametros())
            except UserError:
                # Valores fuera de rango mientras se escribe: se valida al aplicar.
                wizard.vista_previa = wizard.imagen_original

    def _reabrir(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Editar imagen'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_rotar_izquierda(self):
        self.rotacion = (self.rotacion - 90) % 360
        return self._reabrir()

    def action_rotar_derecha(self):
        self.rotacion = (self.rotacion + 90) % 360
        return self._reabrir()

    def action_restablecer(self):
        self.write({'rotacion': 0, 'recorte_arriba': 0, 'recorte_abajo': 0,
                    'recorte_izquierda': 0, 'recorte_derecha': 0})
        return self._reabrir()

    def action_aplicar(self):
        self.ensure_one()
        parametros = self._parametros()
        self.expediente_id.write({self.campo: procesar_imagen(self.imagen_original, **parametros)})
        return {'type': 'ir.actions.act_window_close'}
