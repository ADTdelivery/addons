# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied
import base64
from werkzeug.datastructures import FileStorage
import logging

_logger = logging.getLogger(__name__)


class AdtExpedientesMobileAPI(http.Controller):
    """
    API Móvil con Sistema de Seguridad de Nivel Producción.

    Características de seguridad:
    - Token-based authentication con hashing SHA256
    - Validación automática del estado del usuario en cada request
    - Auditoría completa de accesos
    - Rate limiting básico
    - Device binding para un token por dispositivo
    - Respuestas HTTP estándar (401 Unauthorized, 403 Forbidden)
    """

    # -----------------------------
    # Helpers de autenticación MEJORADOS
    # -----------------------------
    def _extract_token_from_header(self):
        """Extrae el token del header Authorization."""
        auth = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        if not auth:
            return None
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            return parts[1]
        return None

    def _get_request_info(self):
        """Extrae información del request para auditoría."""
        try:
            return {
                'ip': request.httprequest.remote_addr,
                'endpoint': request.httprequest.path,
                'method': request.httprequest.method,
                'user_agent': request.httprequest.headers.get('User-Agent', ''),
            }
        except:
            return {}

    def _authenticate_request(self):
        """
        Valida la autenticación del request (token o sesión).

        Returns:
            tuple: (user_sudo, token_record, error_response)
            - Si autenticado: (user, token, None)
            - Si error: (None, None, {'success': False, 'error': '...', 'code': 401})
        """
        # 1. Intentar autenticación por token (prioritario para app móvil)
        plain_token = self._extract_token_from_header()

        if plain_token:
            # Validar token con auditoría
            request_info = self._get_request_info()
            Token = request.env['adt.mobile.token'].sudo()

            token_rec = Token.validate_token(plain_token, request_info)

            if not token_rec:
                _logger.warning(f'Invalid token attempted from IP {request_info.get("ip")}')
                return (None, None, {
                    'success': False,
                    'error': 'Invalid or expired token',
                    'code': 401,
                    'message': 'Tu sesión ha expirado o tu cuenta fue desactivada. Por favor inicia sesión nuevamente.'
                })

            # Token válido - verificar usuario activo (doble check)
            if not token_rec.user_id.active:
                _logger.warning(f'Attempt to use token of disabled user {token_rec.user_id.login}')
                return (None, None, {
                    'success': False,
                    'error': 'User account disabled',
                    'code': 403,
                    'message': 'Tu cuenta ha sido desactivada. Contacta al administrador.'
                })

            return (token_rec.user_id.sudo(), token_rec, None)

        # 2. Sin token = sin autenticación (NO hay fallback a sesión)
        # Esto asegura que la app móvil SIEMPRE debe usar tokens
        return (None, None, {
            'success': False,
            'error': 'Authentication required - Token missing',
            'code': 401,
            'message': 'No se proporcionó token de autenticación. Por favor inicia sesión.'
        })

    def _require_auth(self):
        """
        Wrapper para endpoints que requieren autenticación.
        Retorna (user, token) o error response.
        """
        user, token, error = self._authenticate_request()
        if error:
            return (None, None, error)
        return (user, token, None)

    def _ensure_auth(self):
        """
        Alias simplificado de _require_auth() para compatibilidad con endpoints existentes.
        Retorna (user, error_dict).

        Uso típico:
            user, err = self._ensure_auth()
            if err:
                return err
            # continuar con lógica del endpoint
        """
        user, token, error = self._authenticate_request()
        if error:
            return (None, error)
        return (user, None)

    # -----------------------------
    # Token endpoints MEJORADOS
    # -----------------------------
    @http.route('/adt_expedientes/mobile/token/create', type='json', auth='none', methods=['POST'], csrf=False)
    def create_token(self, db=None, login=None, password=None, device_info=None, days_valid=30, **kwargs):
        """
        Genera un token seguro para autenticación móvil.

        Request:
        {
            "db": "nombre_bd",
            "login": "usuario",
            "password": "contraseña",
            "device_info": {
                "device_id": "UUID-del-dispositivo",
                "device_name": "iPhone 13 Pro",
                "device_os": "iOS 15.1",
                "app_version": "1.0.0"
            },
            "days_valid": 30
        }

        Response OK:
        {
            "success": true,
            "data": {
                "token": "token_seguro_64_caracteres",
                "expiry": "2026-03-05 10:30:00",
                "user": {"id": 1, "name": "Usuario"},
                "device_bound": true
            }
        }

        Response Error:
        {
            "success": false,
            "error": "Invalid credentials",
            "message": "Usuario o contraseña incorrectos"
        }
        """
        try:
            # Extraer parámetros
            payload = {}
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)

            db = db or payload.get('db')
            login = login or payload.get('login')
            password = password or payload.get('password')
            device_info = device_info or payload.get('device_info') or {}
            days_valid = days_valid or payload.get('days_valid', 30)

            if not all([db, login, password]):
                return {
                    'success': False,
                    'error': 'Missing required fields',
                    'message': 'Se requieren db, login y password'
                }

            # Autenticar usuario
            try:
                uid = request.session.authenticate(db, login, password)
                if not uid:
                    return {
                        'success': False,
                        'error': 'Invalid credentials',
                        'message': 'Usuario o contraseña incorrectos'
                    }
            except AccessDenied:
                _logger.warning(f'Failed login attempt for {login} from {request.httprequest.remote_addr}')
                return {
                    'success': False,
                    'error': 'Access denied',
                    'message': 'Credenciales inválidas'
                }

            # Generar token seguro
            Token = request.env['adt.mobile.token'].sudo()
            token_rec, plain_token = Token.generate_token(
                user_id=uid,
                days_valid=int(days_valid),
                description=f"Mobile App - {device_info.get('device_name', 'Unknown')}",
                device_info=device_info
            )

            user = request.env['res.users'].sudo().browse(uid)

            _logger.info(f'Token generated for user {user.login} (device: {device_info.get("device_name")})')

            return {
                'success': True,
                'data': {
                    'token': plain_token,  # Solo se retorna UNA VEZ
                    'expiry': token_rec.expiry,
                    'user': {
                        'id': user.id,
                        'name': user.name,
                        'login': user.login,
                    },
                    'device_bound': bool(device_info.get('device_id')),
                    'message': 'Token generado exitosamente. Guárdalo de forma segura.'
                }
            }

        except Exception as e:
            _logger.error(f'Error creating token: {e}', exc_info=True)
            return {
                'success': False,
                'error': 'Server error',
                'message': 'Error al generar token. Intenta nuevamente.'
            }

    @http.route('/adt_expedientes/mobile/token/revoke', type='json', auth='none', methods=['POST'], csrf=False)
    def revoke_token(self, token=None, **kwargs):
        """
        Revoca un token (logout desde app).

        Request:
        {
            "token": "token_a_revocar"
        }
        O enviar token en header Authorization: Bearer <token>
        """
        try:
            payload = {}
            if hasattr(request, 'jsonrequest'):
                payload.update(request.jsonrequest or {})

            # Token desde body o header
            plain_token = token or payload.get('token') or self._extract_token_from_header()

            if not plain_token:
                return {
                    'success': False,
                    'error': 'Token required',
                    'message': 'No se proporcionó token para revocar'
                }

            Token = request.env['adt.mobile.token'].sudo()
            revoked = Token.revoke_token(plain_token, reason='logout')

            if revoked:
                return {
                    'success': True,
                    'data': {'revoked': True},
                    'message': 'Sesión cerrada exitosamente'
                }
            else:
                return {
                    'success': False,
                    'error': 'Token not found',
                    'message': 'Token no encontrado o ya revocado'
                }

        except Exception as e:
            _logger.error(f'Error revoking token: {e}')
            return {
                'success': False,
                'error': str(e)
            }

    def _get_param(self, key, arg_value=None, kwargs=None, default=None):
        """Normalize parameter extraction from multiple possible sources.
        Priority: explicit arg_value -> JSON body -> kwargs -> form -> request.params -> default
        """
        # 1. explicit argument provided
        if arg_value is not None:
            return arg_value
        payload = {}
        try:
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)
        except Exception:
            pass
        # 2. kwargs
        if kwargs and key in kwargs and kwargs.get(key) is not None:
            return kwargs.get(key)
        # 3. json payload
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
        # 4. form data
        try:
            form = request.httprequest.form
            if key in form and form.get(key):
                return form.get(key)
        except Exception:
            pass
        # 5. request params (query string)
        try:
            if key in request.params and request.params.get(key):
                return request.params.get(key)
        except Exception:
            pass
        return default

    @http.route('/adt_expedientes/mobile/partner/find_by_dni', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_find_by_dni(self, dni=None, **kwargs):
        """Find a partner by document_number (dni).
        Request: {"dni": "12345678"} or form/query param document_number
        Response: {success: True, data: partner dict or null, suggested: {...}}
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        # Collect dni from multiple possible sources (JSON body, kwargs, form, params)
        payload = {}
        try:
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)
        except Exception:
            pass
        # kwargs may include the values
        payload.update({k: v for k, v in kwargs.items() if k in ('dni', 'document_number', 'nationality', 'country_code')})
        # form/query params fallback
        try:
            form = request.httprequest.form
            for key in ('dni', 'document_number', 'nationality', 'country_code'):
                if key in form and form.get(key):
                    payload.setdefault(key, form.get(key))
        except Exception:
            pass
        try:
            for key in ('dni', 'document_number', 'nationality', 'country_code'):
                if key in request.params and request.params.get(key):
                    payload.setdefault(key, request.params.get(key))
        except Exception:
            pass

        # Prefer explicit arg, then payload fields; accept alias 'document_number'
        dni = dni or payload.get('dni') or payload.get('document_number')
        if not dni:
            return {'success': False, 'error': 'dni required'}

        user, err = self._ensure_auth()
        if err:
            return err
        partner = request.env['res.partner'].sudo().search([('document_number', '=', dni)], limit=1)
        if not partner:
            # If client indicated Peru (e.g. nationality == 'peruana' or country_code == 'PE'),
            # provide suggested country/state data to help creating the contact.
            nationality = (payload.get('nationality') or '').strip().lower()
            country_code_hint = (payload.get('country_code') or '').strip().upper()
            if nationality in ('peruana', 'peru') or country_code_hint == 'PE':
                Country = request.env['res.country'].sudo()
                State = request.env['res.country.state'].sudo()
                country = Country.search([('code', '=', 'PE')], limit=1)
                suggested = {}
                if country:
                    states = State.search([('country_id', '=', country.id)], order='name')
                    suggested = {
                        'country_id': country.code or country.name,
                        'country_name': country.name,
                        'states': [{'id': s.code or str(s.id), 'name': s.name} for s in states],
                    }
                return {'success': True, 'data': None, 'suggested': suggested}
            return {'success': True, 'data': None}

        # helper: resolve selection label for a field
        def _selection_label(record, field_name, value):
            if value in (False, None, ''):
                return ''
            field = record._fields.get(field_name)
            if not field:
                return str(value)
            selection = field.selection(record.env) if callable(field.selection) else field.selection
            if not selection:
                return str(value)
            # selection can be list of (key, label) tuples
            for key, label in selection:
                if key == value:
                    return label
            return str(value)

        # Build user-friendly response: return codes for country/state when possible,
        # and readable city/street/etc. Include both key and readable label for selection fields.
        data = {
            'id': partner.id,
            'name': partner.name or '',
            'document_number': partner.document_number or '',
            'nationality': partner.nationality or '',
            'nationality_label': _selection_label(partner, 'nationality', partner.nationality),
            'occupation': partner.occupation or '',
            'occupation_label': _selection_label(partner, 'occupation', partner.occupation),
            'phone': partner.phone or '',
            'mobile': partner.mobile or '',
            'email': partner.email or '',
            'street': partner.street or '',
            'city': partner.city or '',
            'marital_status': partner.marital_status or '',
            'children_count': str(partner.children_count) if partner.children_count is not None else '',
        }
        # country: return code (e.g. 'PE') for display; fallback to name
        if partner.country_id:
            country_code = getattr(partner.country_id, 'code', None)
            data['country_id'] = country_code if country_code else partner.country_id.name
            data['country_name'] = partner.country_id.name
        else:
            data['country_id'] = ''
            data['country_name'] = ''

        # state: return state code (e.g. 'LIM') for display; fallback to name
        if partner.state_id:
            state_code = getattr(partner.state_id, 'code', None)
            data['state_id'] = state_code if state_code else partner.state_id.name
            data['state_name'] = partner.state_id.name
        else:
            data['state_id'] = ''
            data['state_name'] = ''

        return {'success': True, 'data': data}

    @http.route('/adt_expedientes/mobile/partner/create', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_create(self, vals=None, **kwargs):
        """Create a partner/contact. Accepts partial data.
        Accepts country/state as codes or ids. Example:
          {
              "vals": {
                  "nombre_completo": "Juan",
                  "apellido_paterno": "Perez",
                  "apellido_materno": "Lopez",
                  "document_number": "12345678",
                  "country_id": "PE",
                  "state_id": "15",
                  ...
              },
              "created_by_user_id": 8
          }

        The created_by_user_id parameter is optional. If provided, the partner's create_uid
        will be set to that user, allowing tracking of who created the partner via the mobile app.
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        # Collect payload from possible sources (JSON body, kwargs, form, params)
        payload = {}
        try:
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)
        except Exception:
            pass
        payload.update({k: v for k, v in kwargs.items()})
        try:
            form = request.httprequest.form
            for key in form:
                if form.get(key):
                    payload.setdefault(key, form.get(key))
        except Exception:
            pass
        try:
            for key in request.params:
                if request.params.get(key):
                    payload.setdefault(key, request.params.get(key))
        except Exception:
            pass

        # Extract created_by_user_id from payload
        created_by_user_id = payload.get('created_by_user_id')

        # If vals not provided explicitly, try to extract from payload
        if not vals or not isinstance(vals, dict):
            if isinstance(payload.get('vals'), dict):
                vals = payload.get('vals')
            else:
                candidate_keys = [
                    'name', 'document_number', 'dni', 'nationality', 'occupation',
                    'mobile', 'phone', 'email', 'street', 'street2', 'city', 'zip',
                    'country_id', 'state_id', 'marital_status', 'children_count',
                    'nombre_completo', 'apellido_paterno', 'apellido_materno'
                ]
                vals = {}
                for k in candidate_keys:
                    if k in payload and payload.get(k) is not None:
                        vals[k] = payload.get(k)
                # alias: accept 'dni' as document_number
                if not vals.get('document_number') and payload.get('dni'):
                    vals['document_number'] = payload.get('dni')

        if not vals or not isinstance(vals, dict):
            return {'success': False, 'error': 'vals dict required'}

        # 🔹 Procesar nombre completo si se reciben los campos individuales
        nombre_completo = vals.get('nombre_completo', '').strip() if vals.get('nombre_completo') else ''
        apellido_paterno = vals.get('apellido_paterno', '').strip() if vals.get('apellido_paterno') else ''
        apellido_materno = vals.get('apellido_materno', '').strip() if vals.get('apellido_materno') else ''

        # Si se proporcionan los campos de nombre, construir el campo 'name'
        if nombre_completo or apellido_paterno or apellido_materno:
            name_parts = []
            if nombre_completo:
                name_parts.append(nombre_completo)
            if apellido_paterno:
                name_parts.append(apellido_paterno)
            if apellido_materno:
                name_parts.append(apellido_materno)

            # Construir el nombre completo y asignarlo
            full_name = ' '.join(name_parts)
            vals['name'] = full_name
            _logger.info(f"Construyendo nombre completo: {full_name}")
        elif not vals.get('name'):
            # Si no hay nombre construido ni proporcionado, es un error
            return {'success': False, 'error': 'name or (nombre_completo/apellido_paterno/apellido_materno) required'}

        # Normalize and resolve country/state if provided as codes/strings
        try:
            # Resolve country_id: accept numeric id, numeric string, or country code/name
            cval = vals.get('country_id')
            if cval is not None and cval != '':
                Country = request.env['res.country'].sudo()
                resolved_country_id = None
                if isinstance(cval, int):
                    resolved_country_id = cval
                else:
                    s = str(cval).strip()
                    if s.isdigit():
                        resolved_country_id = int(s)
                    else:
                        # try by code then by name
                        country = Country.search([('code', '=', s.upper())], limit=1)
                        if not country:
                            country = Country.search([('name', 'ilike', s)], limit=1)
                        if country:
                            resolved_country_id = country.id
                if resolved_country_id:
                    vals['country_id'] = resolved_country_id
                else:
                    return {'success': False, 'error': 'country not found for \"%s\"' % str(cval)}

            # Resolve state_id: accept numeric id, numeric string, state code or name
            sval = vals.get('state_id')
            if sval is not None and sval != '':
                State = request.env['res.country.state'].sudo()
                resolved_state_id = None
                if isinstance(sval, int):
                    resolved_state_id = sval
                else:
                    s = str(sval).strip()
                    if s.isdigit():
                        resolved_state_id = int(s)
                    else:
                        domain = []
                        # prefer search by code, optionally restrict by country
                        if s:
                            domain = [('code', '=', s)]
                        country_id_for_state = vals.get('country_id')
                        if country_id_for_state:
                            domain.append(('country_id', '=', int(country_id_for_state)))
                        state = None
                        if domain:
                            state = State.search(domain, limit=1)
                        # fallback search by name
                        if not state:
                            domain_name = [('name', 'ilike', s)]
                            if country_id_for_state:
                                domain_name.append(('country_id', '=', int(country_id_for_state)))
                            state = State.search(domain_name, limit=1)
                        if state:
                            resolved_state_id = state.id
                if resolved_state_id:
                    vals['state_id'] = resolved_state_id
                else:
                    return {'success': False, 'error': 'state not found for \"%s\"' % str(sval)}
        except Exception as e:
            return {'success': False, 'error': 'failed resolving country/state: %s' % str(e)}

        # Coerce some numeric fields if they were sent as strings
        # python
        # Replace the existing coercion block for children_count with this normalization
        if 'children_count' in vals:
            cc = vals.get('children_count')
            try:
                # Normalize types to string
                if isinstance(cc, int):
                    cc = str(cc)
                elif isinstance(cc, str):
                    cc = cc.strip()
                else:
                    cc = str(cc)

                # If purely numeric, map >=4 to '4+' and keep others as digits
                if cc.isdigit():
                    num = int(cc)
                    cc = '4+' if num >= 4 else str(num)

                allowed = {'0', '1', '2', '3', '4+'}
                if cc not in allowed:
                    return {'success': False, 'error': f'children_count invalid: {vals.get("children_count")}'}

                vals['children_count'] = cc
            except Exception:
                # leave original value if unexpected error; optionally return an error instead
                return {'success': False, 'error': 'failed normalizing children_count'}

        #user, err = self._ensure_auth()
        #if err:
        #    return err

        # Determine the user context for partner creation
        Partner = request.env['res.partner'].sudo()

        # If created_by_user_id is provided, use that user's context
        if created_by_user_id:
            try:
                creator_user_id = int(created_by_user_id)
                # Verify the user exists
                user_obj = request.env['res.users'].sudo().browse(creator_user_id)
                if user_obj.exists():
                    Partner = request.env['res.partner'].with_user(creator_user_id).sudo()
                    _logger.info(f"Partner will be created by user ID: {creator_user_id} ({user_obj.name})")
                else:
                    _logger.warning(f"User ID {creator_user_id} not found, using sudo()")
            except (ValueError, TypeError) as e:
                _logger.warning(f"Invalid created_by_user_id: {created_by_user_id}, using sudo()")

        # try to avoid duplicate documents
        doc = vals.get('document_number')
        if doc:
            existing = Partner.search([('document_number', '=', doc)], limit=1)
            if existing:
                return {'success': True, 'data': {'id': existing.id, 'message': 'existing'}}

        try:
            partner = Partner.create(vals)
            _logger.info(f"Partner created with ID: {partner.id}, created by user: {partner.create_uid.name if partner.create_uid else 'Unknown'}")
            return {'success': True, 'data': {'id': partner.id}}
        except Exception as e:
            _logger.error(f"Error creating partner: {e}")
            return {'success': False, 'error': str(e)}

    # Expediente (case) management - incremental
    @http.route('/adt_expedientes/mobile/expediente/create', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_create(self, vals=None, **kwargs):
        """Create an expediente (partial). Expected minimal vals: {'cliente_id': <partner_id>}.
        Accepts multiple payload formats:
          - {"vals": { ... }}
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err
        #  - direct fields: {"cliente_id": 12, "vehiculo": "moto_deluxe_200"}
        #  - accept 'dni' or 'document_number' to lookup partner
        #Returns the expediente id so app can continue uploading more data referencing it.

        # Collect payload from possible sources (JSON body, kwargs, form, params)
        payload = {}
        try:
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)
        except Exception:
            pass
        # kwargs may include values
        payload.update({k: v for k, v in kwargs.items()})
        # form/query params fallback
        try:
            form = request.httprequest.form
            for key in form:
                if form.get(key):
                    payload.setdefault(key, form.get(key))
        except Exception:
            pass
        try:
            for key in request.params:
                if request.params.get(key):
                    payload.setdefault(key, request.params.get(key))
        except Exception:
            pass

        # If vals not provided explicitly, try to extract from payload
        if not vals or not isinstance(vals, dict):
            if isinstance(payload.get('vals'), dict):
                vals = payload.get('vals')
            else:
                # Build vals from common expediente fields
                candidate_keys = ['cliente_id', 'vehiculo', 'fecha', 'direccion_cliente', 'placa', 'chasis']
                vals = {}
                for k in candidate_keys:
                    if k in payload and payload.get(k) is not None:
                        vals[k] = payload.get(k)
                # Accept partner by document number alias
                if not vals.get('cliente_id'):
                    doc = payload.get('document_number') or payload.get('dni') or payload.get('document')
                    if doc:
                        partner = request.env['res.partner'].sudo().search([('document_number', '=', doc)], limit=1)
                        if partner:
                            vals['cliente_id'] = partner.id
                        else:
                            return {'success': False, 'error': 'partner not found with document_number=%s; create partner first' % str(doc)}

        if not vals or not isinstance(vals, dict):
            return {'success': False, 'error': 'vals dict required'}

        # Ensure we have cliente_id
        if not vals.get('cliente_id'):
            return {'success': False, 'error': 'cliente_id is required (or provide document_number/dni to lookup partner)'}

        #user, err = self._ensure_auth()
        #if err:
        #    return err

        Exp = request.env['adt.expediente'].sudo()
        try:
            rec = Exp.create(vals)
            return {'success': True, 'data': {'id': rec.id}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/adt_expedientes/mobile/expediente/update', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_update(self, expediente_id=None, vals=None, **kwargs):
        """Partial update: app can send any fields to update an existing expediente.
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err
        #Request: {"expediente_id": 10, "vals": {"direccion_cliente": "..."}}

        expediente_id = self._get_param('expediente_id', expediente_id, kwargs)
        # vals can be passed in body as 'vals' or directly as payload fields
        if not vals or not isinstance(vals, dict):
            try:
                if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict) and isinstance(request.jsonrequest.get('vals'), dict):
                    vals = request.jsonrequest.get('vals')
            except Exception:
                pass
            # also accept vals in kwargs
            if not vals and 'vals' in kwargs and isinstance(kwargs.get('vals'), dict):
                vals = kwargs.get('vals')
        if not expediente_id or not vals or not isinstance(vals, dict):
            return {'success': False, 'error': 'expediente_id and vals required'}
        #user, err = self._ensure_auth()
        #if err:
        #    return err
        Exp = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not Exp.exists():
            return {'success': False, 'error': 'expediente not found'}
        try:
            # Sanitize vals: mobile clients sometimes send empty strings for binary fields
            # to indicate "no change". Writing '' to a binary field will clear the stored
            # image and may change computed state unexpectedly. We'll skip such keys.
            write_vals = dict(vals)
            for key in list(write_vals.keys()):
                field = Exp._fields.get(key)
                if field and field.type == 'binary':
                    v = write_vals.get(key)
                    if v is None or (isinstance(v, str) and v.strip() == ''):
                        # skip updating this binary field
                        write_vals.pop(key, None)

            Exp.write(write_vals)
            return {'success': True, 'data': {'id': Exp.id}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/adt_expedientes/mobile/expediente/get', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_get(self, expediente_id=None, **kwargs):
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        expediente_id = self._get_param('expediente_id', expediente_id, kwargs)
        if not expediente_id:
            return {'success': False, 'error': 'expediente_id required'}
        if err:
            return err
        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'not found'}
        # return selected fields and status
        data = {
            'id': rec.id,
            'cliente_id': rec.cliente_id.id if rec.cliente_id else None,
            'cliente_name': rec.cliente_id.name if rec.cliente_id else None,
            'cliente_nationality_code': rec.cliente_nationality_code,
            'cliente_nationality_label': rec.cliente_nationality,
            'cliente_occupation_code': rec.cliente_occupation_code,
            'vehiculo': rec.vehiculo,
            'state': rec.state,
        }
        return {'success': True, 'data': data}

    # File upload helper: upload a binary field (single image) for an expediente
    @http.route('/adt_expedientes/mobile/expediente/upload_image', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_upload_image(self, expediente_id=None, field_name=None, image_base64=None, **kwargs):
        """Upload a base64 image and write to the given binary field on the expediente.
        Example: {expediente_id: 10, field_name: 'foto_dni_frente', image_base64: '<base64>'}
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        expediente_id = self._get_param('expediente_id', expediente_id, kwargs)
        field_name = self._get_param('field_name', field_name, kwargs)
        if not image_base64:
            # attempt to get from json body
            try:
                if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                    image_base64 = request.jsonrequest.get('image_base64')
            except Exception:
                pass
        if not expediente_id or not field_name or not image_base64:
            return {'success': False, 'error': 'expediente_id, field_name and image_base64 required'}
        user, err = self._ensure_auth()
        if err:
            return err
        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'expediente not found'}
        # validate that the field exists and is binary
        field = rec._fields.get(field_name)
        if not field or field.type not in ('binary',):
            return {'success': False, 'error': 'invalid field_name'}
        try:
            # the app should send raw base64 string
            # optionally we can validate image size/type
            rec.write({field_name: image_base64})
            return {'success': True, 'data': {'id': rec.id, 'field': field_name}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # Endpoint to mark a document state (aceptado/rechazado) optionally with an observation
    @http.route('/adt_expedientes/mobile/expediente/set_doc_state', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_set_doc_state(self, expediente_id=None, field_state=None, state=None, obs=None, **kwargs):
        """Example: {expediente_id:10, field_state: 'estado_foto_dni', state:'aceptado', obs:'OK'}"""
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        expediente_id = self._get_param('expediente_id', expediente_id, kwargs)
        field_state = self._get_param('field_state', field_state, kwargs)
        state = self._get_param('state', state, kwargs)
        obs = self._get_param('obs', obs, kwargs)
        if not expediente_id or not field_state or not state:
            return {'success': False, 'error': 'expediente_id, field_state and state required'}
        user, err = self._ensure_auth()
        if err:
            return err
        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'expediente not found'}
        if field_state not in rec._fields:
            return {'success': False, 'error': 'invalid state field'}
        try:
            vals = {field_state: state}
            # map obs field conventionally as obs_<fieldname> or obs_foto_* fields
            if obs:
                # try common obs field
                obs_field = 'obs_' + field_state.replace('estado_', '')
                if obs_field in rec._fields:
                    vals[obs_field] = obs
            rec.write(vals)
            return {'success': True, 'data': {'id': rec.id}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # Finalize fase final
    @http.route('/adt_expedientes/mobile/expediente/finalize', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_finalize(self, expediente_id=None, **kwargs):
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        expediente_id = self._get_param('expediente_id', expediente_id, kwargs)
        if not expediente_id:
            return {'success': False, 'error': 'expediente_id required'}
        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'expediente not found'}
        # Optionally trigger any business logic; here we just recompute and return status
        rec.invalidate_cache()
        rec._compute_state()
        return {'success': True, 'data': {'id': rec.id, 'state': rec.state}}

    # List expedientes for a partner
    @http.route('/adt_expedientes/mobile/partner/expedientes', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_expedientes(self, partner_id=None, **kwargs):
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        partner_id = self._get_param('partner_id', partner_id, kwargs)
        if not partner_id:
            return {'success': False, 'error': 'partner_id required'}
            return err
        recs = request.env['adt.expediente'].sudo().search([('cliente_id', '=', int(partner_id))])
        data = []
        for r in recs:
            data.append({'id': r.id, 'state': r.state, 'fecha': str(r.fecha)})
        return {'success': True, 'data': data}

    # -----------------------------
    # Progress endpoint (checks missing fields according to rules)
    # -----------------------------
    @http.route('/adt_expedientes/mobile/expediente/progress', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_progress(self, expediente_id=None, **kwargs):
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        if not expediente_id:
            return {'success': False, 'error': 'expediente_id required'}
        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'expediente not found'}

        # Build a checklist of required fields and which are missing
        missing = []
        nat = getattr(rec.cliente_id, 'nationality', False)
        # nationality-specific
        if nat == 'peruana':
            if not rec.foto_dni_frente:
                missing.append('foto_dni_frente')
            if not rec.foto_dni_reverso:
                missing.append('foto_dni_reverso')
        elif nat and nat != 'peruana':
            # require CE or passport
            if not (rec.foto_ce_frente and rec.foto_ce_reverso) and not (rec.foto_pasaporte_frente and rec.foto_pasaporte_reverso):
                missing.append('foto_ce_or_pasaporte')

        # common documents
        for f in ['foto_licencia', 'foto_recibo', 'foto_sentinel_1']:
            if not getattr(rec, f):
                missing.append(f)

        # occupation-specific
        occ = getattr(rec.cliente_id, 'occupation', False)
        if occ == 'mototaxista':
            for f in ['foto_moto', 'foto_soat', 'foto_tarjeta_propiedad_frente']:
                if not getattr(rec, f):
                    missing.append(f)
        else:
            for f in ['foto_lugar_trabajo', 'foto_boletas', 'foto_estado_cuenta']:
                if not getattr(rec, f):
                    missing.append(f)

        # vivienda
        if rec.tipo_vivienda == 'alquilada':
            if not rec.foto_contrato_alquiler and not rec.propietario_contacto:
                missing.append('foto_contrato_alquiler_or_propietario_contacto')

        return {'success': True, 'data': {'missing': missing}}

    # -----------------------------
    # Multipart upload endpoint (for clients that prefer multipart/form-data)
    # -----------------------------
    @http.route('/adt_expedientes/mobile/expediente/upload_image_multipart', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_upload_image_multipart(self, expediente_id=None, field_name=None, image_base64=None, **kwargs):
        """Upload image: accepts either JSON with base64 or multipart/form-data.
        JSON example: {"expediente_id": 34, "field_name": "foto_dni_frente", "image_base64": "<base64>"}
        Multipart example: form fields expediente_id, field_name and file under 'file'.
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        # Accept token or session
        user, err = self._ensure_auth()
        if err:
            return err

        # If JSON path (type='json'), the parameters may come as function args or in kwargs
        expediente_id = expediente_id or kwargs.get('expediente_id')
        field_name = field_name or kwargs.get('field_name')
        image_base64 = image_base64 or kwargs.get('image_base64')

        # If no base64 provided, check multipart files (backwards compat)
        if not image_base64:
            try:
                file_storage = request.httprequest.files.get('file')
            except Exception:
                file_storage = None
            if file_storage:
                try:
                    data = file_storage.read()
                    image_base64 = base64.b64encode(data).decode('utf-8')
                except Exception as e:
                    return {'success': False, 'error': 'failed reading uploaded file: %s' % str(e)}

        if not expediente_id or not field_name or not image_base64:
            return {'success': False, 'error': 'expediente_id, field_name and image_base64 (or file) required'}

        rec = request.env['adt.expediente'].sudo().browse(int(expediente_id))
        if not rec.exists():
            return {'success': False, 'error': 'expediente not found'}
        field = rec._fields.get(field_name)
        if not field or field.type not in ('binary',):
            return {'success': False, 'error': 'invalid field_name'}
        try:
            rec.write({field_name: image_base64})
            return {'success': True, 'data': {'id': rec.id, 'field': field_name}}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/adt_expedientes/mobile/expedientes/by_asesora', type='json', auth='none', methods=['POST'], csrf=False)
    def expedientes_by_asesora(self, asesora_id=None, **kwargs):
        """
        Return expedientes for an asesora (agent) with detailed payload so the mobile app can show which fields are missing.
        Params:
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err
        #  - asesora_id: id (or numeric string) of the user/asesora. If omitted, use the authenticated user.
        #Response: {success: True, data: [ { expediente fields..., cliente: {...}, asesor: {...}, missing: [...] } ]}

        # Accept parameter from multiple sources
        asesora_id = self._get_param('asesora_id', asesora_id, kwargs)
        #user, err = self._ensure_auth()
        #if err:
        #    return err

        # default to current user if no asesora_id provided
        if not asesora_id:
            asesora_id = user.id
        try:
            asesora_id = int(asesora_id)
        except Exception:
            return {'success': False, 'error': 'invalid asesora_id'}

        Exp = request.env['adt.expediente'].sudo()
        recs = Exp.search([('asesora_id', '=', asesora_id)], order='id desc')
        data = []

        def _selection_label(record, field_name, value):
            if value in (False, None, ''):
                return ''
            field = record._fields.get(field_name)
            if not field:
                return str(value)
            selection = field.selection(record.env) if callable(field.selection) else field.selection
            if not selection:
                return str(value)
            for key, label in selection:
                if key == value:
                    return label
            return str(value)

        for r in recs:
            exp = {'id': r.id}
            # serialize expediente fields: include readable values and flags for binaries
            for fname, field in r._fields.items():
                ftype = field.type
                try:
                    val = getattr(r, fname)
                except Exception:
                    val = None
                # skip internal relational helpers
                if fname.startswith('_'):
                    continue
                if ftype == 'binary':
                    # don't send base64 content; instead send presence flag and length hint
                    exp[fname + '_present'] = bool(val)
                elif ftype in ('char', 'text', 'date', 'datetime', 'boolean', 'integer', 'float', 'monetary', 'selection'):
                    exp[fname] = val
                elif ftype == 'many2one':
                    if val:
                        exp[fname] = {'id': val.id, 'name': getattr(val, 'name', False)}
                    else:
                        exp[fname] = None
                elif ftype in ('one2many', 'many2many'):
                    # return list of ids for relations
                    try:
                        exp[fname] = [rec.id for rec in val]
                    except Exception:
                        exp[fname] = []
                else:
                    # fallback to string representation
                    exp[fname] = None if val is None else str(val)

            # include cliente (partner) readable info
            cliente = r.cliente_id
            if cliente:
                p = cliente.sudo()
                cliente_data = {
                    'id': p.id,
                    'name': p.name or '',
                    'document_number': p.document_number or '',
                    'nationality': p.nationality or '',
                    'nationality_label': _selection_label(p, 'nationality', p.nationality),
                    'occupation': p.occupation or '',
                    'occupation_label': _selection_label(p, 'occupation', p.occupation),
                    'phone': p.phone or '',
                    'mobile': p.mobile or '',
                    'email': p.email or '',
                    'street': p.street or '',
                    'city': p.city or '',
                    'marital_status': p.marital_status or '',
                    'children_count': str(p.children_count) if p.children_count is not None else '',
                    'country_id': getattr(p.country_id, 'code', '') or (p.country_id.name if p.country_id else ''),
                    'country_name': p.country_id.name if p.country_id else '',
                    'state_id': getattr(p.state_id, 'code', '') or (p.state_id.name if p.state_id else ''),
                    'state_name': p.state_id.name if p.state_id else '',
                }
            else:
                cliente_data = None
            exp['cliente'] = cliente_data

            # include asesor info
            asesor = r.asesora_id
            if asesor:
                a = asesor.sudo()
                exp['asesor'] = {'id': a.id, 'name': a.name or '', 'email': getattr(a, 'email', '')}
            else:
                exp['asesor'] = None

            # ensure vehiculo is explicit top-level (if exists)
            exp['vehiculo'] = getattr(r, 'vehiculo', None)

            # compute missing documents checklist similar to expediente_progress
            missing = []
            nat = cliente and getattr(cliente, 'nationality', False) or False
            if nat == 'peruana':
                if not getattr(r, 'foto_dni_frente'):
                    missing.append('foto_dni_frente')
                if not getattr(r, 'foto_dni_reverso'):
                    missing.append('foto_dni_reverso')
            elif nat and nat != 'peruana':
                if not (getattr(r, 'foto_ce_frente') and getattr(r, 'foto_ce_reverso')) and not (getattr(r, 'foto_pasaporte_frente') and getattr(r, 'foto_pasaporte_reverso')):
                    missing.append('foto_ce_or_pasaporte')

            # common documents
            for f in ['foto_licencia', 'foto_recibo', 'foto_sentinel_1']:
                if not getattr(r, f):
                    missing.append(f)

            # occupation-specific
            occ = cliente and getattr(cliente, 'occupation', False) or False
            if occ == 'mototaxista':
                for f in ['foto_moto', 'foto_soat', 'foto_tarjeta_propiedad_frente']:
                    if not getattr(r, f):
                        missing.append(f)
            else:
                for f in ['foto_lugar_trabajo', 'foto_boletas', 'foto_estado_cuenta']:
                    if not getattr(r, f):
                        missing.append(f)

            # vivienda
            if getattr(r, 'tipo_vivienda', None) == 'alquilada':
                if not getattr(r, 'foto_contrato_alquiler') and not getattr(r, 'propietario_contacto'):
                    missing.append('foto_contrato_alquiler_or_propietario_contacto')

            exp['missing'] = missing

            data.append(exp)

        return {'success': True, 'data': data}

    @http.route('/adt_expedientes/mobile/partner/card', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_card(self, partner_id=None, **kwargs):
        """Return lightweight partner info and the number of expedientes associated.

        Request: {"partner_id": 123}
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err
        #Response: {success: True, data: {partner: {...}, expediente_count: 5}}

        partner_id = self._get_param('partner_id', partner_id, kwargs)
        if not partner_id:
            return {'success': False, 'error': 'partner_id required'}
        try:
            pid = int(partner_id)
        except Exception:
            return {'success': False, 'error': 'invalid partner_id'}

        Partner = request.env['res.partner'].sudo()
        p = Partner.browse(pid)
        if not p.exists():
            return {'success': False, 'error': 'partner not found'}

        def _selection_label(record, field_name, value):
            if value in (False, None, ''):
                return ''
            field = record._fields.get(field_name)
            if not field:
                return str(value)
            try:
                selection = field.selection(record.env) if callable(field.selection) else field.selection
            except Exception:
                selection = field.selection if hasattr(field, 'selection') else None
            if not selection:
                return str(value)
            for key, label in selection:
                if key == value:
                    return label
            return str(value)

        country_code = getattr(p.country_id, 'code', None) or ''
        country_name = p.country_id.name if p.country_id else ''
        state_code = getattr(p.state_id, 'code', None) or ''
        state_name = p.state_id.name if p.state_id else ''

        partner_data = {
            'id': p.id,
            'name': p.name or '',
            'document_number': p.document_number or '',
            'nationality': p.nationality or '',
            'nationality_label': _selection_label(p, 'nationality', p.nationality),
            'occupation': p.occupation or '',
            'occupation_label': _selection_label(p, 'occupation', p.occupation),
            'phone': p.phone or '',
            'mobile': p.mobile or '',
            'email': p.email or '',
            'street': p.street or '',
            'city': p.city or '',
            'country_id': country_code,
            'country_name': country_name,
            'state_id': state_code,
            'state_name': state_name,
        }

        Exp = request.env['adt.expediente'].sudo()
        recs = Exp.search([('cliente_id', '=', p.id)], order='id desc')
        expedientes = []
        for r in recs:
            expedientes.append({
                'id': r.id,
                'state': r.state,
                'fecha': str(r.fecha) if getattr(r, 'fecha', False) else None,
                'vehiculo': r.vehiculo,
                'placa': r.placa or '',
                'chasis': r.chasis or '',
                'asesor': {'id': r.asesora_id.id if r.asesora_id else None, 'name': r.asesora_id.name if r.asesora_id else ''}
            })

        # Return partner info plus a minimal list of expedientes for card UI
        return {'success': True, 'data': {'partner': partner_data, 'expedientes': expedientes}}

    @http.route('/adt_expedientes/mobile/partner/search_by_dni', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_search_by_dni(self, query=None, limit=50, **kwargs):
        """Search partners by partial document_number (dni). Minimum 5 characters required.
        Request example: {"query": "77100"}
        Response: {success: True, data: [ {id, name, document_number, nationality, nationality_label, occupation, occupation_label, phone, mobile, email, street, city, marital_status, children_count, country_id, country_name, state_id, state_name} ]}
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        # accept parameter from multiple sources
        query = self._get_param('query', query, kwargs)
        if not query:
            return {'success': False, 'error': 'query required'}
        q = str(query).strip()
        if len(q) < 5:
            return {'success': False, 'error': 'query must be at least 5 characters'}
        try:
            limit = int(self._get_param('limit', limit, kwargs) or limit)
        except Exception:
            limit = 50

        #user, err = self._ensure_auth()
        #if err:
        #    return err

        Partner = request.env['res.partner'].sudo()
        # search by document_number containing the query (case-insensitive)
        recs = Partner.search([('document_number', 'ilike', q)], limit=limit, order='id desc')

        def _selection_label(record, field_name, value):
            if value in (False, None, ''):
                return ''
            field = record._fields.get(field_name)
            if not field:
                return str(value)
            selection = field.selection(record.env) if callable(field.selection) else field.selection
            if not selection:
                return str(value)
            for key, label in selection:
                if key == value:
                    return label
            return str(value)

        data = []
        for p in recs:
            country_code = ''
            country_name = ''
            if p.country_id:
                country_code = getattr(p.country_id, 'code', None) or p.country_id.name or ''
                country_name = p.country_id.name or ''
            state_code = ''
            state_name = ''
            if p.state_id:
                state_code = getattr(p.state_id, 'code', None) or p.state_id.name or ''
                state_name = p.state_id.name or ''

            children = p.children_count if getattr(p, 'children_count', False) is not None else ''
            # ensure string representation
            if children is False or children is None:
                children = ''
            else:
                children = str(children)

            data.append({
                'id': p.id,
                'name': p.name or '',
                'document_number': p.document_number or '',
                'nationality': p.nationality or '',
                'nationality_label': _selection_label(p, 'nationality', p.nationality),
                'occupation': p.occupation or '',
                'occupation_label': _selection_label(p, 'occupation', p.occupation),
                'phone': p.phone or '',
                'mobile': p.mobile or '',
                'email': p.email or '',
                'street': p.street or '',
                'city': p.city or '',
                'marital_status': p.marital_status or '',
                'children_count': children,
                'country_id': country_code,
                'country_name': country_name,
                'state_id': state_code,
                'state_name': state_name,
            })

        return {'success': True, 'data': data}

    @http.route('/adt_expedientes/mobile/partner/update', type='json', auth='none', methods=['POST'], csrf=False)
    def partner_update(self, partner_id=None, vals=None, **kwargs):
        """Update an existing partner (partial). Accepts partner_id (id or numeric string) or document_number/dni to find the partner.
        Body examples:
          {"partner_id": 12, "vals": {"phone": "999111222"}}
          {"document_number": "77100152", "vals": {"city": "SJM", "country_id": "PE", "state_id": "LIM"}}
          {"partner_id": 12, "created_by_user_id": 8, "vals": {"phone": "999111222"}}

        El campo created_by_user_id (opcional) permite usar el contexto de ese usuario para la actualización,
        estableciendo correctamente el write_uid.
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err
        #Returns: {success: True, data: {id: partner.id}}

        # Collect payload to extract created_by_user_id
        payload = {}
        try:
            if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                payload.update(request.jsonrequest)
        except Exception:
            pass
        payload.update({k: v for k, v in kwargs.items()})

        # Extract created_by_user_id from payload
        created_by_user_id = payload.get('created_by_user_id')

        # Accept parameters from multiple sources
        partner_id = self._get_param('partner_id', partner_id, kwargs)
        # vals can be passed as 'vals' dict, or individual fields in payload
        if not vals or not isinstance(vals, dict):
            try:
                if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict) and isinstance(request.jsonrequest.get('vals'), dict):
                    vals = request.jsonrequest.get('vals')
            except Exception:
                pass
            if not vals and 'vals' in kwargs and isinstance(kwargs.get('vals'), dict):
                vals = kwargs.get('vals')
            # also allow building vals from top-level payload fields when 'vals' not provided
            if not vals:
                payload = {}
                try:
                    if hasattr(request, 'jsonrequest') and isinstance(request.jsonrequest, dict):
                        payload.update(request.jsonrequest)
                except Exception:
                    pass
                payload.update({k: v for k, v in kwargs.items()})
                try:
                    form = request.httprequest.form
                    for key in form:
                        if form.get(key):
                            payload.setdefault(key, form.get(key))
                except Exception:
                    pass
                try:
                    for key in request.params:
                        if request.params.get(key):
                            payload.setdefault(key, request.params.get(key))
                except Exception:
                    pass
                # take common partner fields
                candidate_keys = ['name', 'phone', 'mobile', 'email', 'street', 'city', 'zip', 'country_id', 'state_id', 'marital_status', 'children_count', 'occupation', 'nationality']
                vals = {}
                for k in candidate_keys:
                    if k in payload and payload.get(k) is not None:
                        vals[k] = payload.get(k)
                # alias: accept 'dni' as document_number
                if not partner_id and (payload.get('document_number') or payload.get('dni')):
                    # leave partner lookup for below
                    pass

        if not vals or not isinstance(vals, dict):
            return {'success': False, 'error': 'vals dict required'}

        # find partner either by id or by document_number/dni
        doc = self._get_param('document_number', None, kwargs) or self._get_param('dni', None, kwargs)
        if not partner_id and doc:
            Partner = request.env['res.partner'].sudo()
            partner = Partner.search([('document_number', '=', doc)], limit=1)
            if not partner:
                return {'success': False, 'error': 'partner not found by document_number'}
        else:
            if not partner_id:
                return {'success': False, 'error': 'partner_id or document_number/dni required'}
            try:
                pid = int(partner_id)
            except Exception:
                return {'success': False, 'error': 'invalid partner_id'}
            partner = request.env['res.partner'].sudo().browse(pid)
            if not partner.exists():
                return {'success': False, 'error': 'partner not found'}

        # Resolve country/state codes if present in vals (reuse logic from partner_create)
        try:
            cval = vals.get('country_id')
            if cval is not None and cval != '':
                Country = request.env['res.country'].sudo()
                resolved_country_id = None
                if isinstance(cval, int):
                    resolved_country_id = cval
                else:
                    s = str(cval).strip()
                    if s.isdigit():
                        resolved_country_id = int(s)
                    else:
                        country = Country.search([('code', '=', s.upper())], limit=1)
                        if not country:
                            country = Country.search([('name', 'ilike', s)], limit=1)
                        if country:
                            resolved_country_id = country.id
                if resolved_country_id:
                    vals['country_id'] = resolved_country_id
                else:
                    return {'success': False, 'error': 'country not found for "%s"' % str(cval)}

            sval = vals.get('state_id')
            if sval is not None and sval != '':
                State = request.env['res.country.state'].sudo()
                resolved_state_id = None
                if isinstance(sval, int):
                    resolved_state_id = sval
                else:
                    s = str(sval).strip()
                    if s.isdigit():
                        resolved_state_id = int(s)
                    else:
                        domain = []
                        if s:
                            domain = [('code', '=', s)]
                        country_id_for_state = vals.get('country_id')
                        if country_id_for_state:
                            try:
                                domain.append(('country_id', '=', int(country_id_for_state)))
                            except Exception:
                                pass
                        state = None
                        if domain:
                            state = State.search(domain, limit=1)
                        if not state:
                            domain_name = [('name', 'ilike', s)]
                            if country_id_for_state:
                                try:
                                    domain_name.append(('country_id', '=', int(country_id_for_state)))
                                except Exception:
                                    pass
                            state = State.search(domain_name, limit=1)
                        if state:
                            resolved_state_id = state.id
                if resolved_state_id:
                    vals['state_id'] = resolved_state_id
                else:
                    return {'success': False, 'error': 'state not found for "%s"' % str(sval)}
        except Exception as e:
            return {'success': False, 'error': 'failed resolving country/state: %s' % str(e)}

        # Normalize children_count to selection keys
        if 'children_count' in vals:
            cc = vals.get('children_count')
            try:
                if isinstance(cc, int):
                    cc = str(cc)
                elif isinstance(cc, str):
                    cc = cc.strip()
                else:
                    cc = str(cc)
                if cc.isdigit():
                    num = int(cc)
                    cc = '4+' if num >= 4 else str(num)
                allowed = {'0', '1', '2', '3', '4+'}
                if cc not in allowed:
                    return {'success': False, 'error': f'children_count invalid: {vals.get("children_count")}'}
                vals['children_count'] = cc
            except Exception:
                return {'success': False, 'error': 'failed normalizing children_count'}

        # require authentication
        #user, err = self._ensure_auth()
        #if err:
        #    return err

        try:
            # 🔹 Si se proporciona created_by_user_id, usar ese contexto de usuario para el write
            Partner = partner
            if created_by_user_id:
                try:
                    updater_user_id = int(created_by_user_id)
                    # Verify the user exists
                    user_obj = request.env['res.users'].sudo().browse(updater_user_id)
                    if user_obj.exists():
                        Partner = partner.with_user(updater_user_id).sudo()
                        _logger.info(f"Partner {partner.id} será actualizado por user ID: {updater_user_id} ({user_obj.name})")
                    else:
                        _logger.warning(f"User ID {updater_user_id} not found, using default context")
                except (ValueError, TypeError) as e:
                    _logger.warning(f"Invalid created_by_user_id: {created_by_user_id}, using default context")

            Partner.write(vals)
            _logger.info(f"Partner {partner.id} actualizado exitosamente. Actualizado por: {Partner.write_uid.name if Partner.write_uid else 'Unknown'}")
            return {'success': True, 'data': {'id': partner.id}}
        except Exception as e:
            _logger.error(f"Error updating partner {partner.id}: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/adt_expedientes/mobile/expediente/summary_by_asesora', type='json', auth='none', methods=['POST'], csrf=False)
    def expediente_summary_by_asesora(self, asesora_id=None, **kwargs):
        """
        Return a structured summary of expedientes for an asesora for mobile consumption.
        Response per expediente contains grouped sections (identity, general docs, ingresos/ocupacion,
        ubicacion/vivienda, referencias, meta) with per-field objects:
          { present: bool, state: 'aceptado'|'rechazado'|None, obs: str, value: any }
        Also returns missing_fields (list of keys) and progress (0-100 integer)
        """
        # 🔒 VALIDACIÓN DE AUTENTICACIÓN
        user, err = self._ensure_auth()
        if err:
            return err

        asesora_id = self._get_param('asesora_id', asesora_id, kwargs)
        if not asesora_id:
            asesora_id = user.id
        try:
            asesora_id = int(asesora_id)
        except Exception:
            return {'success': False, 'error': 'invalid asesora_id'}

        Exp = request.env['adt.expediente'].sudo()
        recs = Exp.search([('asesora_id', '=', asesora_id)], order='id desc')

        def doc_field(record, photo_field=None, estado_field=None, obs_field=None, value_field=None):
            # Returns a standard descriptor for a field
            val = None
            if value_field:
                val = getattr(record, value_field)
            present = False
            if photo_field:
                present = bool(getattr(record, photo_field))
            else:
                # if no photo_field, use value presence
                present = val not in (False, None, '', [])
            state = getattr(record, estado_field) if estado_field and estado_field in record._fields else None
            obs = getattr(record, obs_field) if obs_field and obs_field in record._fields else None
            # convert booleans to python bools and selections kept raw
            res = {'present': bool(present), 'state': state, 'obs': obs or ''}
            # include value only when it has a non-null value to avoid 'value': null
            if val not in (None, ''):
                res['value'] = val
            return res

        def sel_label(rec, field_name, key):
            if not key:
                return ''
            f = rec._fields.get(field_name)
            if not f:
                return key
            selection = f.selection(rec.env) if callable(f.selection) else f.selection
            if not selection:
                return key
            return dict(selection).get(key, key)

        def compute_required_and_completed(r):
            required = []
            completed = []
            cliente = r.cliente_id
            nat = getattr(cliente, 'nationality', False) if cliente else False
            # identity docs
            if nat == 'peruana':
                required += ['foto_dni_frente', 'foto_dni_reverso']
                if getattr(r, 'foto_dni_frente') and getattr(r, 'foto_dni_reverso') and getattr(r, 'estado_foto_dni') == 'aceptado':
                    completed += ['foto_dni_frente', 'foto_dni_reverso']
            else:
                # foreign: either CE or passport
                required += ['foto_ce_frente|foto_pasaporte_frente']
                # mark completed if either set accepted
                ce_ok = bool(getattr(r, 'foto_ce_frente') and getattr(r, 'foto_ce_reverso') and getattr(r, 'estado_foto_ce') == 'aceptado')
                pas_ok = bool(getattr(r, 'foto_pasaporte_frente') and getattr(r, 'foto_pasaporte_reverso') and getattr(r, 'estado_foto_pasaporte') == 'aceptado')
                if ce_ok or pas_ok:
                    completed += ['foto_ce_frente|foto_pasaporte_frente']

            # general docs always apply
            general = ['foto_licencia', 'foto_recibo', 'foto_sentinel_1']
            for f in general:
                required.append(f)
                if getattr(r, f) and getattr(r, f.replace('foto', 'estado').replace('sentinel_1', 'foto_sentinel_1'), None) is None:
                    # if state not defined, consider presence as completed
                    completed.append(f)
                elif getattr(r, f) and r._fields.get('estado_' + f.split('foto_')[-1]) is None:
                    completed.append(f)
                elif getattr(r, f):
                    # if a corresponding estado field exists and is aceptado
                    estado_name = 'estado_' + f.split('foto_')[-1]
                    estado_val = getattr(r, estado_name, None) if estado_name in r._fields else None
                    if estado_val == 'aceptado' or estado_val is None:
                        completed.append(f)

            # occupation-specific
            occ = getattr(cliente, 'occupation', False) if cliente else False
            if occ == 'mototaxista':
                mot = ['foto_moto', 'foto_soat', 'foto_tarjeta_propiedad_frente']
                for f in mot:
                    required.append(f)
                    # simple accepted check
                    estado_name = 'estado_' + f.split('foto_')[-1] if f.startswith('foto_') else None
                    if getattr(r, f) and (estado_name not in r._fields or getattr(r, estado_name) == 'aceptado'):
                        completed.append(f)
            else:
                nonmot = ['foto_lugar_trabajo', 'foto_lugar_negocio', 'foto_boletas', 'foto_estado_cuenta']
                for f in nonmot:
                    required.append(f)
                    estado_name = 'estado_' + f.split('foto_')[-1] if f.startswith('foto_') else None
                    if getattr(r, f) and (estado_name not in r._fields or getattr(r, estado_name) == 'aceptado'):
                        completed.append(f)

            # vivienda
            required.append('tipo_vivienda')
            if getattr(r, 'tipo_vivienda'):
                completed.append('tipo_vivienda')
                if getattr(r, 'tipo_vivienda') == 'alquilada':
                    required += ['propietario_contacto', 'foto_contrato_alquiler']
                    if getattr(r, 'propietario_contacto'):
                        completed.append('propietario_contacto')
                    if getattr(r, 'foto_contrato_alquiler') and getattr(r, 'estado_foto_contrato') == 'aceptado':
                        completed.append('foto_contrato_alquiler')
            # references
            required += ['ref_1_name', 'ref_1_phone']
            if getattr(r, 'ref_1_name') and getattr(r, 'ref_1_phone'):
                completed += ['ref_1_name', 'ref_1_phone']
            # You can expand references required logic as needed

            return required, completed

        results = []
        for r in recs:
            cliente = r.cliente_id
            nat_code = getattr(cliente, 'nationality', '') if cliente else ''
            occ_code = getattr(cliente, 'occupation', '') if cliente else ''

            # Build sections
            identity = {}
            if nat_code == 'peruana':
                identity['dni_frente'] = doc_field(r, 'foto_dni_frente', 'estado_foto_dni', 'obs_foto_dni')
                identity['dni_reverso'] = doc_field(r, 'foto_dni_reverso', 'estado_foto_dni', 'obs_foto_dni')
            else:
                identity['ce_frente'] = doc_field(r, 'foto_ce_frente', 'estado_foto_ce', 'obs_foto_ce')
                identity['ce_reverso'] = doc_field(r, 'foto_ce_reverso', 'estado_foto_ce', 'obs_foto_ce')
                identity['pasaporte_frente'] = doc_field(r, 'foto_pasaporte_frente', 'estado_foto_pasaporte', 'obs_foto_pasaporte')
                identity['pasaporte_reverso'] = doc_field(r, 'foto_pasaporte_reverso', 'estado_foto_pasaporte', 'obs_foto_pasaporte')

            # Expose licencia, recibo and sentinel as top-level keys (mobile-friendly)
            licencia = doc_field(r, 'foto_licencia', 'estado_foto_licencia', 'obs_foto_licencia')
            recibo = doc_field(r, 'foto_recibo', 'estado_foto_recibo', 'obs_foto_recibo')
            sentinel = {
                'sentinel_1': doc_field(r, 'foto_sentinel_1', 'estado_foto_sentinel', 'obs_foto_sentinel'),
                'sentinel_2': doc_field(r, 'foto_sentinel_2', 'estado_foto_sentinel', 'obs_foto_sentinel'),
                'estado': getattr(r, 'estado_foto_sentinel', None),
                'obs': getattr(r, 'obs_foto_sentinel', '') or ''
            }

            ingresos = {}
            if occ_code == 'mototaxista':
                ingresos['vehiculo'] = {'value': r.vehiculo, 'label': sel_label(r, 'vehiculo', r.vehiculo)}
                ingresos['foto_moto'] = doc_field(r, 'foto_moto', 'estado_foto_moto', 'obs_foto_moto')
                ingresos['foto_soat'] = doc_field(r, 'foto_soat', 'estado_foto_soat', 'obs_foto_soat')
                ingresos['foto_tarjeta_frente'] = doc_field(r, 'foto_tarjeta_propiedad_frente', 'estado_foto_tarjeta', 'obs_foto_tarjeta')
                ingresos['foto_tarjeta_reverso'] = doc_field(r, 'foto_tarjeta_propiedad_reverso', 'estado_foto_tarjeta', 'obs_foto_tarjeta')
                ingresos['ganancia_diaria_mensual'] = {'value': r.ganancia_diaria_mensual}
                ingresos['tiempo_trabajando'] = {'value': r.tiempo_trabajando}
                ingresos['moto_empresa'] = {'value': r.moto_empresa}
                ingresos['moto_propiedad'] = {'value': r.moto_propiedad, 'label': sel_label(r, 'moto_propiedad', r.moto_propiedad)}
            else:
                ingresos['foto_lugar_trabajo'] = doc_field(r, 'foto_lugar_trabajo', 'estado_foto_lugar_trabajo', 'obs_foto_lugar_trabajo')
                ingresos['foto_lugar_negocio'] = doc_field(r, 'foto_lugar_negocio', 'estado_foto_lugar_negocio', 'obs_foto_lugar_negocio')
                ingresos['foto_boletas'] = doc_field(r, 'foto_boletas', 'estado_foto_boletas', 'obs_foto_boletas')
                ingresos['foto_estado_cuenta'] = doc_field(r, 'foto_estado_cuenta', 'estado_foto_estado_cuenta', 'obs_foto_estado_cuenta')
                ingresos['ganancia_diaria_mensual_no'] = {'value': r.ganancia_diaria_mensual_no}
                ingresos['tiempo_trabajando_no'] = {'value': r.tiempo_trabajando_no}

            vivienda = {}
            vivienda['foto_ubicacion_actual'] = doc_field(r, 'foto_ubicacion_actual', 'estado_foto_ubicacion', 'obs_foto_ubicacion')
            vivienda['foto_fachada_domicilio'] = doc_field(r, 'foto_fachada_domicilio', 'estado_foto_fachada', 'obs_foto_fachada')
            vivienda['tipo_vivienda'] = {'value': r.tipo_vivienda, 'label': sel_label(r, 'tipo_vivienda', r.tipo_vivienda)}
            vivienda['tiempo_viviendo'] = {'value': r.tiempo_viviendo}
            vivienda['propietario_contacto'] = {'value': r.propietario_contacto}
            vivienda['foto_contrato_alquiler'] = doc_field(r, 'foto_contrato_alquiler', 'estado_foto_contrato', 'obs_foto_contrato')

            referencias = {
                'ref_1': {'name': r.ref_1_name, 'phone': r.ref_1_phone, 'vinculo': r.ref_1_vinculo, 'vinculo_label': sel_label(r, 'ref_1_vinculo', r.ref_1_vinculo)},
                'ref_2': {'name': r.ref_2_name, 'phone': r.ref_2_phone, 'vinculo': r.ref_2_vinculo, 'vinculo_label': sel_label(r, 'ref_2_vinculo', r.ref_2_vinculo)},
                'ref_3': {'name': r.ref_3_name, 'phone': r.ref_3_phone, 'vinculo': r.ref_3_vinculo, 'vinculo_label': sel_label(r, 'ref_3_vinculo', r.ref_3_vinculo)},
                'ref_4': {'name': r.ref_4_name, 'phone': r.ref_4_phone, 'vinculo': r.ref_4_vinculo, 'vinculo_label': sel_label(r, 'ref_4_vinculo', r.ref_4_vinculo)},
                'estado_referencias': {'value': r.estado_referencias},
                'obs_referencias': {'value': r.obs_referencias}
            }

            meta = {
                'expediente_id': r.id,
                'state': r.state,
                'fecha': str(r.fecha) if getattr(r, 'fecha', False) else None,
                'cliente': {
                    'id': cliente.id if cliente else None,
                    'nombre_completo': cliente.name if cliente else None,
                    'phone': cliente.phone if cliente else None,
                    'mobile': cliente.mobile if cliente else None,
                    'nacionalidad': nat_code,
                    'nacionalidad_label': sel_label(cliente, 'nationality', nat_code) if cliente else '' ,
                    'ocupacion': occ_code,
                    'ocupacion_label': sel_label(cliente, 'occupation', occ_code) if cliente else ''
                },
                'asesora': {'id': r.asesora_id.id if r.asesora_id else None, 'nombre': r.asesora_id.name if r.asesora_id else None, 'email': getattr(r.asesora_id, 'email', None)}
            }

            # compute required and completed to produce progress (do not return missing_fields per request)
            required, completed = compute_required_and_completed(r)
            progress = 0
            try:
                total = len(required) if required else 1
                progress = int((len(completed) / total) * 100)
            except Exception:
                progress = 0

            results.append({
                'meta': meta,
                'identity': identity,
                'licencia': licencia,
                'recibo': recibo,
                'sentinel': sentinel,
                'ingresos': ingresos,
                'vivienda': vivienda,
                'referencias': referencias,
                'progress': progress
            })

        return {'success': True, 'data': results}

