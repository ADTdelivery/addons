odoo.define('adt_comercial.image_carousel_widget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');
    var core = require('web.core');

    var qweb = core.qweb;

    var ImageCarouselWidget = AbstractField.extend({
        template: 'adt_comercial.ImageCarousel',
        supportedFieldTypes: ['char', 'text'],

        events: {
            'click .o_image_carousel_prev': '_onPrev',
            'click .o_image_carousel_next': '_onNext',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.urls = [];
            this.currentIndex = 0;
        },

        _parseUrls: function (raw) {
            if (!raw) {
                return [];
            }

            if (Array.isArray(raw)) {
                return raw.filter(Boolean);
            }

            if (typeof raw === 'string') {
                var payload = raw.trim();
                if (!payload) {
                    return [];
                }

                try {
                    var parsed = JSON.parse(payload);
                    if (Array.isArray(parsed)) {
                        return parsed.filter(Boolean);
                    }
                    if (typeof parsed === 'string' && parsed.trim()) {
                        return [parsed.trim()];
                    }
                } catch (error) {
                    return payload
                        .split(',')
                        .map(function (item) {
                            return item.trim();
                        })
                        .filter(Boolean);
                }
            }

            return [];
        },

        _render: function () {
            this.urls = this._parseUrls(this.value);
            if (this.currentIndex >= this.urls.length) {
                this.currentIndex = 0;
            }

            this.$el.html(
                qweb.render('adt_comercial.ImageCarouselContent', {
                    hasImages: this.urls.length > 0,
                    urls: this.urls,
                    currentIndex: this.currentIndex,
                    currentUrl: this.urls[this.currentIndex] || '',
                })
            );
        },

        _onPrev: function (ev) {
            ev.preventDefault();
            if (!this.urls.length) {
                return;
            }
            this.currentIndex = (this.currentIndex - 1 + this.urls.length) % this.urls.length;
            this._render();
        },

        _onNext: function (ev) {
            ev.preventDefault();
            if (!this.urls.length) {
                return;
            }
            this.currentIndex = (this.currentIndex + 1) % this.urls.length;
            this._render();
        },
    });

    fieldRegistry.add('image_carousel', ImageCarouselWidget);

    return ImageCarouselWidget;
});

