odoo.define('adt_comercial.mobile_home_preview_action', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var qweb = core.qweb;

    var AUTOPLAY_DELAY = 4000;

    // Mapa pantalla -> menú/acción de Odoo (ver context/mapa-pantallas-servicios-odoo.md).
    // Todos apuntan a acciones que ya viven dentro de Móvil > App y sus submenús —
    // no se redirige a ninguna sección fuera de ese árbol de menú.
    var ACTION_XMLIDS = {
        action_mobile_app_image: 'adt_comercial.action_mobile_app_image',
        action_mobile_content_item: 'adt_comercial.action_mobile_content_item',
        action_mobile_content_item_fullscreen: 'adt_comercial.action_mobile_content_item_fullscreen',
        action_mobile_promotion: 'adt_comercial.action_mobile_promotion',
        action_mobile_catalog_products: 'adt_comercial.action_mobile_catalog_products',
        action_mobile_benefit: 'adt_comercial.action_mobile_benefit',
        action_mobile_payment_account: 'adt_comercial.action_mobile_payment_account',
        action_mobile_support_contact: 'adt_comercial.action_mobile_support_contact',
        action_mobile_notificaciones_masivas: 'adt_comercial.action_mobile_notificacion_masiva_wizard',
    };

    var MobileHomePreviewAction = AbstractAction.extend({
        template: 'adt_comercial.MobileHomePreview',

        events: {
            'click .o_mobile_tap_zone': '_onTapZoneClick',
            'click [data-scroll-to]': '_onQuickAccessClick',
            'click .o_mobile_preview_banner_prev': '_onBannerPrev',
            'click .o_mobile_preview_banner_next': '_onBannerNext',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.data = null;
            this.bannerIndex = 0;
            this._autoplayTimer = null;
        },

        willStart: function () {
            var self = this;
            return Promise.all([
                this._super.apply(this, arguments),
                this._rpc({
                    model: 'mobile.home.preview',
                    method: 'get_preview_data',
                    args: [],
                }).then(function (data) {
                    self.data = data;
                }),
            ]);
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._renderHomeBanner();
                self._startAutoplay();
            });
        },

        destroy: function () {
            this._stopAutoplay();
            this._super.apply(this, arguments);
        },

        // ── Banner "Home" (única pieza que se re-renderiza: el resto del
        //    mapa se pinta una sola vez al montar el widget) ─────────────
        _renderHomeBanner: function () {
            var banners = (this.data && this.data.home_banners) || [];
            this.$('.o_mobile_home_banner_inner').html(
                qweb.render('adt_comercial.MobileHomeBannerSlide', {
                    banners: banners,
                    currentBanner: banners[this.bannerIndex] || {},
                    bannerIndex: this.bannerIndex,
                    bannerCount: banners.length,
                })
            );
        },

        _startAutoplay: function () {
            var self = this;
            this._stopAutoplay();
            var banners = (this.data && this.data.home_banners) || [];
            if (banners.length > 1) {
                this._autoplayTimer = setInterval(function () {
                    self._advanceBanner(1);
                }, AUTOPLAY_DELAY);
            }
        },

        _stopAutoplay: function () {
            if (this._autoplayTimer) {
                clearInterval(this._autoplayTimer);
                this._autoplayTimer = null;
            }
        },

        _advanceBanner: function (delta) {
            var banners = (this.data && this.data.home_banners) || [];
            if (!banners.length) {
                return;
            }
            this.bannerIndex = (this.bannerIndex + delta + banners.length) % banners.length;
            this._renderHomeBanner();
        },

        _onBannerPrev: function (ev) {
            ev.preventDefault();
            ev.stopPropagation(); // no disparar el tap-zone padre (redirige a Odoo)
            this._advanceBanner(-1);
            this._startAutoplay();
        },

        _onBannerNext: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            this._advanceBanner(1);
            this._startAutoplay();
        },

        // ── Tap zones: redirigen a la sección de Odoo correspondiente ──
        _onTapZoneClick: function (ev) {
            // Los botones del carrusel ya hicieron stopPropagation, así que
            // un click ahí nunca debería llegar hasta acá; esto es solo defensivo.
            if ($(ev.target).is('.o_mobile_preview_banner_prev, .o_mobile_preview_banner_next')) {
                return;
            }
            var actionKey = $(ev.currentTarget).data('action');
            var xmlId = ACTION_XMLIDS[actionKey];
            if (!xmlId) {
                return;
            }
            this.do_action(xmlId);
        },

        // ── Accesos rápidos del Home: navegan DENTRO del mapa (no son
        //    contenido de servicio, no redirigen a Odoo) ─────────────────
        _onQuickAccessClick: function (ev) {
            var targetId = $(ev.currentTarget).data('scroll-to');
            if (!targetId) {
                return;
            }
            var $target = this.$('#' + targetId);
            if ($target.length) {
                $target[0].scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        },
    });

    core.action_registry.add('mobile_home_preview', MobileHomePreviewAction);

    return MobileHomePreviewAction;
});
