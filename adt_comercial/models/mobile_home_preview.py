# -*- coding: utf-8 -*-
"""
Mapa Pantallas ↔ Servicios ↔ Odoo (Ajustes -> Móvil -> App -> Mapa de
Pantallas). Implementa el inventario funcional documentado en
`context/mapa-pantallas-servicios-odoo.md`: dibuja cada pantalla de la app
móvil ADT Client tal como la ve el cliente y expone, para cada sección que
en verdad sale de un servicio editable en Odoo, los datos reales de ese
servicio para la vista previa.

Reglas (ver el .md, sección 1):
  1. Pantalla 100% servicio -> toda el área es un solo punto de acceso.
  2. Pantalla mixta -> se dibuja completa, pero solo se resaltan las
     secciones que en verdad traen datos de un servicio; el resto se
     dibuja igual (fidelidad visual) sin punto de acceso.
  3. Una sección que abre otra pantalla completa se resalta igual,
     redirigiendo al destino de esa otra pantalla.
  4. "Seguridad / Reportar incidente" corre contra un backend externo:
     queda fuera de este mapa por completo.

Todos los datos que se exponen aquí salen ÚNICAMENTE de modelos que ya
tienen su propia opción dentro del menú Móvil > App (Imágenes de la App,
Item de contenido, Productos, Promociones, Beneficios, Cuenta de Pago,
Contacto de Soporte) — no se trae nada de otras secciones del módulo.
"""
from odoo import api, models


class MobileHomePreview(models.TransientModel):
    _name = 'mobile.home.preview'
    _description = 'Datos agregados para el Mapa de Pantallas de la app móvil'

    @api.model
    def get_preview_data(self):
        AppImage = self.env['mobile.app.image'].sudo()
        ContentItem = self.env['mobile.content.item'].sudo()
        Benefit = self.env['mobile.benefit'].sudo()
        PaymentAccount = self.env['mobile.payment.account'].sudo()
        SupportContact = self.env['mobile.support.contact'].sudo()
        Product = self.env['product.template'].sudo()
        Promotion = self.env['mobile.promotion'].sudo()

        # ── 3.1 Login: imagen hero por código LOGIN (mobile.app.image) ──
        login_image = AppImage.search([('active', '=', True), ('code', '=', 'LOGIN')], limit=1)

        # ── 3.2 Home: banner promocional superior ───────────────────────
        # mobile.content.item con section=BANNER_HOME (menú "Banner Slide",
        # ver views/view_mobile_models.xml — action_mobile_content_item),
        # mismo servicio genérico GET /v1/content-items?section=BANNER_HOME.
        home_banners = ContentItem.search(
            [('active', '=', True), ('section', '=', 'BANNER_HOME')],
            order='sequence asc', limit=6,
        )
        home_banner_data = [{
            'id': b.id,
            'title': b.title,
            'subtitle': b.subtitle or '',
            'has_image': bool(b.image),
        } for b in home_banners]

        # ── 3.2bis Publicidad Full Screen: mismo modelo/servicio, otra
        # sección (menú "Publicidad Full Screen", ver view_mobile_models.xml
        # — action_mobile_content_item_fullscreen), GET /v1/content-items
        # ?section=FULL_SCREEN. Un solo anuncio activo a la vez (interstitial).
        fullscreen_item = ContentItem.search(
            [('active', '=', True), ('section', '=', 'FULL_SCREEN')],
            order='sequence asc', limit=1,
        )
        fullscreen_ad_data = {
            'configured': bool(fullscreen_item),
            'id': fullscreen_item.id if fullscreen_item else False,
            'title': fullscreen_item.title if fullscreen_item else '',
            'subtitle': (fullscreen_item.subtitle or '') if fullscreen_item else '',
            'has_image': bool(fullscreen_item and fullscreen_item.image),
        }

        # ── 3.4 Novedades y Noticias: 100% servicio (mobile.promotion) ──
        promotions = Promotion.search([('active', '=', True)], order='priority asc', limit=5)
        promo_data = [{
            'id': pr.id,
            'title': pr.title,
            'body': pr.body,
            'has_image': bool(pr.image),
        } for pr in promotions]

        # ── 3.3 Tienda y Repuesto: 100% servicio, mismo criterio que ────
        # GET /v1/catalog/products en controllers/mobile_api.py
        store_domain = [
            ('active', '=', True),
            ('sale_ok', '=', True),
            ('mobile_published', '=', True),
        ]
        products = Product.search(store_domain, order='mobile_sequence asc', limit=6)
        product_data = [{
            'id': p.id,
            'name': p.name,
            'price': p.list_price,
            'badge': p.mobile_badge or '',
        } for p in products]
        products_count = Product.search_count(store_domain)

        # ── 3.5 Vehículo: Beneficios / Cuenta autorizada / Atención ─────
        benefits = Benefit.search([('active', '=', True)], order='sequence asc', limit=4)
        benefit_data = [{'id': be.id, 'titulo': be.titulo, 'categoria': be.categoria} for be in benefits]
        benefits_count = Benefit.search_count([('active', '=', True)])

        payment_account = PaymentAccount.search([('active', '=', True)], order='sequence asc', limit=1)
        support_contact = SupportContact.search([('active', '=', True)], order='sequence asc', limit=1)

        return {
            'login': {
                'has_image': bool(login_image and login_image.image),
                'image_id': login_image.id if login_image else False,
                'configured': bool(login_image),
            },
            'home_banners': home_banner_data,
            'fullscreen_ad': fullscreen_ad_data,
            'promotions': promo_data,
            'products': product_data,
            'products_count': products_count,
            'benefits': benefit_data,
            'benefits_count': benefits_count,
            'payment_account_name': payment_account.name if payment_account else None,
            'support_contact_name': support_contact.name if support_contact else None,
            'support_contact_phone': support_contact.phone if support_contact else None,
        }
