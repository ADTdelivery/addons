import json

from odoo import fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import content_disposition, request

from ..models.calculo import FRECUENCIAS

MENSAJE_SIMULACION = 'Simulación generada correctamente.'
LIMITE_MAXIMO = 50


class ApiError(Exception):
    def __init__(self, codigo, mensaje, **extra):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.extra = extra


def _error(codigo, mensaje, **extra):
    return dict({'ok': False, 'codigo': codigo, 'error': mensaje}, **extra)


class SimuladorFinanciamientoController(http.Controller):
    """Servicios que consume la app. Todos son JSON-RPC (POST) con sesión de usuario.

    Errores: {ok: false, codigo, error}. La TEA y el importe a financiar nunca se
    reciben ni se devuelven; los toma el backend del vehículo configurado.
    """

    # ------------------------------------------------------------------ catálogo
    @http.route('/api/simulador/vehiculos', type='json', auth='user', methods=['POST'])
    def vehiculos(self, **kw):
        """Vehículos financiables activos."""
        vehiculos = request.env['financing.vehicle'].search([])
        return {
            'ok': True,
            'vehiculos': [{'id': v.id, 'nombre': v.name} for v in vehiculos],
        }

    # ------------------------------------------------------------------ clientes
    @http.route('/api/simulador/clientes/buscar', type='json', auth='user', methods=['POST'])
    def clientes_buscar(self, texto=None, limite=20, **kw):
        """Busca clientes por nombre, documento o teléfono."""
        texto = (texto or '').strip() if isinstance(texto, str) else ''
        if len(texto) < 2:
            return _error('parametros_invalidos', 'Ingresa al menos 2 caracteres para buscar.')
        limite = self._limite(limite)
        dominio = ['|', '|', '|',
                   ('name', 'ilike', texto), ('vat', 'ilike', texto),
                   ('phone', 'ilike', texto), ('mobile', 'ilike', texto)]
        clientes = request.env['res.partner'].search(dominio, limit=limite, order='name')
        return {'ok': True, 'clientes': [self._cliente_dict(c) for c in clientes]}

    @http.route('/api/simulador/clientes/crear', type='json', auth='user', methods=['POST'])
    def clientes_crear(self, nombre=None, documento=None, telefono=None, email=None, **kw):
        """Registra un cliente nuevo y devuelve su id para relacionarlo a la simulación."""
        try:
            nombre = self._texto(nombre, 'nombre', obligatorio=True)
            documento = self._texto(documento, 'documento')
            telefono = self._texto(telefono, 'telefono')
            email = self._texto(email, 'email')

            if documento:
                existente = request.env['res.partner'].search([('vat', '=', documento)], limit=1)
                if existente:
                    return _error('cliente_existente',
                                  'Ya existe un cliente con ese documento.',
                                  cliente=self._cliente_dict(existente))
            with request.env.cr.savepoint():
                # sudo: los usuarios internos pueden no tener permiso de crear contactos.
                cliente = request.env['res.partner'].sudo().create({
                    'name': nombre,
                    'vat': documento or False,
                    'phone': telefono or False,
                    'email': email or False,
                })
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)
        except (UserError, ValidationError) as e:
            return _error('validacion', self._mensaje(e))
        return {'ok': True, 'mensaje': 'Cliente registrado correctamente.',
                'cliente': self._cliente_dict(cliente)}

    @http.route('/api/simulador/clientes/detalle', type='json', auth='user', methods=['POST'])
    def clientes_detalle(self, cliente_id=None, **kw):
        try:
            return {'ok': True, 'cliente': self._cliente_dict(self._cliente(cliente_id))}
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)

    # ------------------------------------------------------------------ simulaciones
    @http.route('/api/simulador/cuotas', type='json', auth='user', methods=['POST'])
    def cuotas(self, vehiculo_id=None, cuota_inicial=None, plazo_meses=None,
               cliente_id=None, fecha_inicio=None, frecuencia=None, **kw):
        """Calcula y registra la simulación (las tres cuotas siempre a la vez).

        Opcionales: `cliente_id` (relaciona la simulación con un cliente),
        `fecha_inicio` (AAAA-MM-DD; genera el cronograma) y `frecuencia`
        (mensual | semanal | diaria; por defecto mensual).
        """
        try:
            vehiculo_id = self._entero(vehiculo_id, 'vehiculo_id')
            plazo_meses = self._entero(plazo_meses, 'plazo_meses')
            cuota_inicial = self._numero(cuota_inicial, 'cuota_inicial')
            cliente = self._cliente(cliente_id) if cliente_id not in (None, '', False) else None
            fecha = self._fecha(fecha_inicio)
            frecuencia = self._frecuencia(frecuencia)

            vehiculo = request.env['financing.vehicle'].search([('id', '=', vehiculo_id)])
            if not vehiculo:
                raise ApiError('no_encontrado', 'El vehículo seleccionado no existe o no está activo.')

            # Savepoint: si una validación falla tras el INSERT, no debe quedar registro.
            with request.env.cr.savepoint():
                simulacion = request.env['financing.simulation'].create({
                    'vehicle_id': vehiculo.id,
                    'cuota_inicial': cuota_inicial,
                    'plazo_meses': plazo_meses,
                    'partner_id': cliente.id if cliente else False,
                    'frecuencia': frecuencia,
                    'fecha_inicio': fecha or False,
                    'origen': 'app',
                })
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)
        except (UserError, ValidationError) as e:
            return _error('validacion', self._mensaje(e))

        return dict({'ok': True, 'mensaje': MENSAJE_SIMULACION},
                    **self._simulacion_dict(simulacion))

    @http.route('/api/simulador/simulaciones/listar', type='json', auth='user', methods=['POST'])
    def simulaciones_listar(self, cliente_id=None, limite=20, offset=0, **kw):
        """Historial de simulaciones (más recientes primero), filtrable por cliente."""
        try:
            dominio = []
            if cliente_id not in (None, '', False):
                dominio.append(('partner_id', '=', self._entero(cliente_id, 'cliente_id')))
            offset = max(self._entero(offset, 'offset'), 0)
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)
        modelo = request.env['financing.simulation']
        return {
            'ok': True,
            'total': modelo.search_count(dominio),
            'simulaciones': [self._simulacion_dict(s) for s in modelo.search(
                dominio, limit=self._limite(limite), offset=offset)],
        }

    @http.route('/api/simulador/simulaciones/detalle', type='json', auth='user', methods=['POST'])
    def simulaciones_detalle(self, simulacion_id=None, **kw):
        try:
            simulacion = self._simulacion(simulacion_id)
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)
        return dict({'ok': True}, **self._simulacion_dict(simulacion))

    @http.route('/api/simulador/simulaciones/cronograma', type='json', auth='user', methods=['POST'])
    def simulaciones_cronograma(self, simulacion_id=None, **kw):
        """Cuotas del cronograma (existe solo si la simulación tiene fecha de inicio)."""
        try:
            simulacion = self._simulacion(simulacion_id)
        except ApiError as e:
            return _error(e.codigo, e.mensaje, **e.extra)
        return {
            'ok': True,
            'simulacion_id': simulacion.id,
            'numero': simulacion.name,
            'frecuencia': simulacion.frecuencia,
            'fecha_inicio': self._iso(simulacion.fecha_inicio),
            'cantidad_cuotas': simulacion.cantidad_cuotas,
            'total_a_pagar': simulacion.total_credito,
            'cuotas': [{
                'numero': linea.numero,
                'fecha': self._iso(linea.fecha),
                'cuota': linea.cuota,
                'saldo': linea.saldo,
            } for linea in simulacion.linea_ids.sorted('numero')],
        }

    @http.route('/api/simulador/simulaciones/<int:simulacion_id>/pdf',
                type='http', auth='user', methods=['GET'])
    def simulacion_pdf(self, simulacion_id, **kw):
        """Descarga el PDF de la simulación (con el cronograma si lo tiene)."""
        simulacion = request.env['financing.simulation'].search([('id', '=', simulacion_id)])
        if not simulacion:
            return self._respuesta_error(
                404, _error('no_encontrado', 'La simulación indicada no existe.'))
        reporte = request.env.ref('adt_simulador_prospecto_financiamiento.action_report_simulacion')
        try:
            pdf, _tipo = reporte._render_qweb_pdf(simulacion.ids)
        except UserError as e:
            return self._respuesta_error(500, _error('pdf_no_disponible', self._mensaje(e)))
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition('%s.pdf' % simulacion.name)),
        ])

    @staticmethod
    def _respuesta_error(status, cuerpo):
        respuesta = request.make_response(
            json.dumps(cuerpo), headers=[('Content-Type', 'application/json')])
        respuesta.status_code = status
        return respuesta

    # ------------------------------------------------------------------ serialización
    @staticmethod
    def _iso(valor):
        return fields.Date.to_string(valor) if valor else None

    @staticmethod
    def _cliente_dict(cliente):
        return {
            'id': cliente.id,
            'nombre': cliente.name,
            'documento': cliente.vat or None,
            'telefono': cliente.phone or cliente.mobile or None,
            'email': cliente.email or None,
        }

    def _simulacion_dict(self, s):
        lineas = s.linea_ids.sorted('numero')
        return {
            'simulacion_id': s.id,
            'numero': s.name,
            'fecha': fields.Datetime.to_string(s.fecha),
            'origen': s.origen,
            'vehiculo': {'id': s.vehicle_id.id, 'nombre': s.vehicle_id.name},
            'cliente': self._cliente_dict(s.partner_id) if s.partner_id else None,
            'cuota_inicial': s.cuota_inicial,
            'plazo_meses': s.plazo_meses,
            'frecuencia': s.frecuencia,
            'fecha_inicio': self._iso(s.fecha_inicio),
            'capital': s.capital,
            'cuota_mensual': s.cuota_mensual,
            'cuota_semanal': s.cuota_semanal,
            'cuota_diaria': s.cuota_diaria,
            'cronograma': {
                'generado': bool(lineas),
                'cantidad_cuotas': len(lineas),
                'total_a_pagar': s.total_credito,
                'primera_fecha': self._iso(lineas[0].fecha) if lineas else None,
                'ultima_fecha': self._iso(lineas[-1].fecha) if lineas else None,
            },
        }

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _mensaje(e):
        return e.args[0] if e.args else str(e)

    @staticmethod
    def _limite(valor):
        try:
            return max(1, min(int(valor), LIMITE_MAXIMO))
        except (TypeError, ValueError):
            return 20

    @staticmethod
    def _texto(valor, campo, obligatorio=False):
        if valor is None or valor is False or valor == '':
            if obligatorio:
                raise ApiError('parametros_invalidos', 'El campo %s es obligatorio.' % campo)
            return ''
        if not isinstance(valor, str):
            raise ApiError('parametros_invalidos', 'El campo %s debe ser texto.' % campo)
        valor = valor.strip()
        if obligatorio and not valor:
            raise ApiError('parametros_invalidos', 'El campo %s es obligatorio.' % campo)
        return valor

    @staticmethod
    def _numero(valor, campo):
        if isinstance(valor, bool) or valor is None or valor == '':
            raise ApiError('parametros_invalidos',
                           'El campo %s es obligatorio y debe ser numérico.' % campo)
        try:
            return float(valor)
        except (TypeError, ValueError):
            raise ApiError('parametros_invalidos', 'El campo %s debe ser numérico.' % campo)

    @classmethod
    def _entero(cls, valor, campo):
        numero = cls._numero(valor, campo)
        if numero != int(numero):
            raise ApiError('parametros_invalidos', 'El campo %s debe ser un número entero.' % campo)
        return int(numero)

    @staticmethod
    def _fecha(valor):
        if valor in (None, '', False):
            return None
        try:
            if not isinstance(valor, str):
                raise ValueError
            return fields.Date.from_string(valor)
        except ValueError:
            raise ApiError('parametros_invalidos', 'fecha_inicio debe tener el formato AAAA-MM-DD.')

    @staticmethod
    def _frecuencia(valor):
        valor = (valor or 'mensual')
        valor = valor.strip().lower() if isinstance(valor, str) else ''
        if valor not in FRECUENCIAS:
            raise ApiError('parametros_invalidos',
                           'frecuencia debe ser una de: %s.' % ', '.join(FRECUENCIAS))
        return valor

    def _cliente(self, cliente_id):
        cliente = request.env['res.partner'].search(
            [('id', '=', self._entero(cliente_id, 'cliente_id'))])
        if not cliente:
            raise ApiError('no_encontrado', 'El cliente indicado no existe.')
        return cliente

    def _simulacion(self, simulacion_id):
        simulacion = request.env['financing.simulation'].search(
            [('id', '=', self._entero(simulacion_id, 'simulacion_id'))])
        if not simulacion:
            raise ApiError('no_encontrado', 'La simulación indicada no existe.')
        return simulacion
