(function () {
    "use strict";

    const CACHE_TTL_MS = 20000;
    const FIRST_HOVER_DELAY_MS = 60;
    const MAX_CACHE_ENTRIES = 150;
    const INSTALL_RETRY_MS = 50;
    const MAX_INSTALL_ATTEMPTS = 100;
    const ITEM_PREVIEW_METHOD = "amf.amf.utils.item_hover_preview.get_item_hover_data";

    const preview_cache = Object.create(null);
    const inflight_requests = Object.create(null);

    function escape_html(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    function format_qty(value) {
        const precision = cint(frappe.defaults.get_default("float_precision")) || 3;
        return format_number(flt(value), null, precision);
    }

    function prune_cache(now) {
        Object.keys(preview_cache).forEach((cache_key) => {
            if (preview_cache[cache_key].expires_at <= now) {
                delete preview_cache[cache_key];
            }
        });

        const cache_keys = Object.keys(preview_cache);
        if (cache_keys.length <= MAX_CACHE_ENTRIES) {
            return;
        }

        cache_keys
            .sort((left, right) => (
                preview_cache[left].last_accessed - preview_cache[right].last_accessed
            ))
            .slice(0, cache_keys.length - MAX_CACHE_ENTRIES)
            .forEach((cache_key) => {
                delete preview_cache[cache_key];
            });
    }

    function get_item_preview_data(item_code) {
        const now = Date.now();
        const cached_entry = preview_cache[item_code];

        if (cached_entry && cached_entry.expires_at > now) {
            cached_entry.last_accessed = now;
            return Promise.resolve(cached_entry.data);
        }

        if (cached_entry) {
            delete preview_cache[item_code];
        }
        if (inflight_requests[item_code]) {
            return inflight_requests[item_code];
        }

        prune_cache(now);
        const request = frappe.xcall(ITEM_PREVIEW_METHOD, {item_code: item_code});
        inflight_requests[item_code] = request.then(
            (data) => {
                delete inflight_requests[item_code];
                if (data) {
                    preview_cache[item_code] = {
                        data: data,
                        expires_at: Date.now() + CACHE_TTL_MS,
                        last_accessed: Date.now(),
                    };
                    prune_cache(Date.now());
                }
                return data;
            },
            (error) => {
                delete inflight_requests[item_code];
                throw error;
            }
        );
        return inflight_requests[item_code];
    }

    function has_fresh_item_cache(item_code) {
        const cached_entry = preview_cache[item_code];
        return Boolean(cached_entry && cached_entry.expires_at > Date.now());
    }

    function get_stock_state(data) {
        if (data.disabled) {
            return {css_class: "is-disabled", label: __("Disabled")};
        }
        if (!data.is_stock_item) {
            return {css_class: "is-neutral", label: __("Non-stock item")};
        }
        if (!data.stock_access) {
            return {css_class: "is-neutral", label: __("Stock restricted")};
        }
        if (flt(data.available_qty) > 0) {
            return {css_class: "is-positive", label: __("Available")};
        }
        if (flt(data.available_qty) < 0) {
            return {css_class: "is-negative", label: __("Shortage")};
        }
        if (flt(data.actual_qty) > 0) {
            return {css_class: "is-warning", label: __("Fully reserved")};
        }
        return {css_class: "is-negative", label: __("Out of stock")};
    }

    function get_metric_html(label, value, uom, css_class, title) {
        return `
            <div class="amf-item-preview__metric ${css_class || ""}" title="${escape_html(title)}">
                <span class="amf-item-preview__metric-label">${escape_html(label)}</span>
                <strong>${escape_html(format_qty(value))}</strong>
                <span class="amf-item-preview__uom">${escape_html(uom)}</span>
            </div>
        `;
    }

    function get_item_preview_html(data) {
        const item_link = frappe.utils.get_form_link("Item", data.item_code);
        const bom_link = data.default_bom
            ? frappe.utils.get_form_link("BOM", data.default_bom)
            : null;
        const state = get_stock_state(data);
        const uom = data.stock_uom || "";
        let stock_html = "";

        if (!data.is_stock_item) {
            stock_html = `
                <div class="amf-item-preview__notice">
                    ${escape_html(__("Stock quantities do not apply to this item."))}
                </div>
            `;
        } else if (!data.stock_access) {
            stock_html = `
                <div class="amf-item-preview__notice">
                    ${escape_html(__("No permitted warehouse stock is available."))}
                </div>
            `;
        } else {
            const availability_class = flt(data.available_qty) > 0
                ? "is-positive"
                : (flt(data.actual_qty) > 0 ? "is-warning" : "is-negative");
            const projected_class = flt(data.projected_qty) >= 0 ? "" : "is-negative";
            stock_html = `
                <div class="amf-item-preview__metrics">
                    ${get_metric_html(
                        __("On hand"),
                        data.on_hand_qty,
                        uom,
                        "",
                        __("Physical quantity currently in {0}", [data.on_hand_warehouse])
                    )}
                    ${get_metric_html(
                        __("Available now"),
                        data.available_qty,
                        uom,
                        availability_class,
                        __(
                            "On hand less sales, production and subcontracting reservations in {0}",
                            [data.on_hand_warehouse]
                        )
                    )}
                    ${get_metric_html(
                        __("Projected"),
                        data.projected_qty,
                        uom,
                        projected_class,
                        __(
                            "On hand plus incoming quantities less all reservations in {0}",
                            [data.on_hand_warehouse]
                        )
                    )}
                </div>
                <div class="amf-item-preview__flow">
                    <span>
                        ${escape_html(__("Reserved"))}
                        <strong>${escape_html(format_qty(data.reserved_qty))} ${escape_html(uom)}</strong>
                    </span>
                    <span>
                        ${escape_html(__("Incoming"))}
                        <strong>${escape_html(format_qty(data.incoming_qty))} ${escape_html(uom)}</strong>
                    </span>
                    <span title="${escape_html(data.on_hand_warehouse)}">
                        ${escape_html(__("Warehouse"))}
                        <strong>${escape_html(data.on_hand_warehouse)}</strong>
                    </span>
                </div>
            `;
        }

        return `
            <div class="amf-item-preview">
                <div class="amf-item-preview__header">
                    <div class="amf-item-preview__identity">
                        <a class="amf-item-preview__name" href="${item_link}">
                            ${escape_html(data.item_name)}
                        </a>
                        <a class="amf-item-preview__code" href="${item_link}">
                            ${escape_html(data.item_code)}
                        </a>
                        ${data.item_group
                            ? `<span class="amf-item-preview__group">${escape_html(data.item_group)}</span>`
                            : ""}
                    </div>
                    <span class="amf-item-preview__status ${state.css_class}">
                        ${escape_html(state.label)}
                    </span>
                </div>
                ${stock_html}
                <div class="amf-item-preview__footer">
                    ${bom_link
                        ? `<a href="${bom_link}">
                            <i class="fa fa-sitemap" aria-hidden="true"></i>
                            ${escape_html(__("Default BOM"))}: ${escape_html(data.default_bom)}
                        </a>`
                        : `<span class="text-muted">${escape_html(__("No default BOM"))}</span>`}
                    <a class="amf-item-preview__open" href="${item_link}">
                        ${escape_html(__("Open Item"))}
                        <i class="fa fa-arrow-right" aria-hidden="true"></i>
                    </a>
                </div>
            </div>
        `;
    }

    function patch_link_preview() {
        if (!window.frappe || !frappe.ui || !frappe.ui.LinkPreview) {
            return false;
        }
        if (frappe.ui.LinkPreview.__amf_item_preview_patched) {
            return true;
        }

        const prototype = frappe.ui.LinkPreview.prototype;
        const original_get_preview_data = prototype.get_preview_data;
        const original_get_popover_html = prototype.get_popover_html;
        const original_setup_popover_control = prototype.setup_popover_control;
        const original_create_popover = prototype.create_popover;
        const original_init_preview_popover = prototype.init_preview_popover;

        prototype.get_preview_data = function () {
            if (this.doctype === "Item") {
                return get_item_preview_data(this.name);
            }
            return original_get_preview_data.call(this);
        };

        prototype.get_popover_html = function (preview_data) {
            if (preview_data && preview_data.amf_item_preview) {
                return get_item_preview_html(preview_data);
            }
            return original_get_popover_html.call(this, preview_data);
        };

        prototype.setup_popover_control = function (event) {
            if (this.doctype !== "Item") {
                return original_setup_popover_control.call(this, event);
            }
            if (!(frappe.boot.link_preview_doctypes || []).includes(this.doctype)) {
                return;
            }

            const element = this.element;
            if (this.data_timeout) {
                clearTimeout(this.data_timeout);
            }
            if (this.popover_timeout) {
                clearTimeout(this.popover_timeout);
            }

            if (has_fresh_item_cache(this.name)) {
                this.create_popover(event);
                return;
            }

            this.data_timeout = setTimeout(() => {
                if (
                    element.is(":hover")
                    && this.element
                    && this.element.get(0) === element.get(0)
                ) {
                    this.create_popover(event);
                }
            }, FIRST_HOVER_DELAY_MS);
        };

        prototype.create_popover = function (event) {
            if (this.doctype !== "Item") {
                return original_create_popover.call(this, event);
            }
            if (this.element.is(":focus")) {
                return;
            }

            const element = this.element;
            const item_code = this.name;
            this.get_preview_data().then((preview_data) => {
                const is_current_link = (
                    preview_data
                    && element.is(":hover")
                    && !element.is(":focus")
                    && this.element
                    && this.element.get(0) === element.get(0)
                    && this.name === item_code
                );
                if (!is_current_link) {
                    return;
                }

                this.popover = element.data("bs.popover");
                if (this.popover) {
                    this.popover.options.content = this.get_popover_html(preview_data);
                } else {
                    this.init_preview_popover(preview_data);
                }
                this.show_popover(event);
            });
        };

        prototype.init_preview_popover = function (preview_data) {
            original_init_preview_popover.call(this, preview_data);
            if (preview_data && preview_data.amf_item_preview) {
                this.element
                    .data("bs.popover")
                    .tip()
                    .addClass("amf-item-preview-popover");
            }
        };

        frappe.ui.LinkPreview.__amf_item_preview_patched = true;
        return true;
    }

    let install_attempts = 0;
    function install_when_ready() {
        if (patch_link_preview() || install_attempts >= MAX_INSTALL_ATTEMPTS) {
            return;
        }
        install_attempts += 1;
        setTimeout(install_when_ready, INSTALL_RETRY_MS);
    }

    install_when_ready();
}());
