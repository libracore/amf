"""Replay the agreed 4D RS485/CAN item creation during the next migration.

Existing records are retained. The six BOMs explicitly left pending on
2026-10-23 stay pending, regardless of subsequent valve-head activation.
The patch runner owns the transaction; this module never commits it.
"""

from contextlib import contextmanager

import frappe
from frappe.utils.html_utils import clean_html, sanitize_html


SOURCE_CODES = (
    '4D0005', '4D0006', '4D0007', '4D0009', '4D0010', '4D0012', '4D0016',
    '4D0019', '4D0021', '4D0029', '4D0031', '4D0033', '4D0034', '4D0035',
    '4D0036', '4D0037', '4D0038', '4D0039', '4D0040', '4D0041', '4D0043',
    '4D0044', '4D0045', '4D0046', '4D004D', '4D0057', '4D0058', '4D0060',
    '4D0061', '4D0062', '4D0063', '4D0064', '4D0067', '4D0068', '4D0071',
    '4D0072', '4D0080',
)
VARIANTS = (('4D1', 'RS485', '5D1001'), ('4D2', 'CAN', '5D1002'))
PENDING_BOM_SOURCES = {
    '4D0058': ('300058',), '4D0062': ('/300062',), '4D0068': ('/300068',),
}
DESCRIPTION_FIELDS = ('description', 'internal_description', 'custom_description', 'web_long_description')
PRICE_KEY_FIELDS = (
    'price_list', 'uom', 'min_qty', 'valid_from', 'valid_upto', 'packing_unit',
    'customer', 'supplier',
)


def execute():
    """Create only missing records, including on a partially migrated site."""
    frappe.set_user('Administrator')
    counts = dict(items=0, boms=0, prices=0, attachments=0)
    sources = [frappe.get_doc('Item', code) for code in SOURCE_CODES
               if frappe.db.exists('Item', code)]
    if not sources:
        return counts
    _require(frappe.db.get_default('item_naming_by') == 'Item Code',
             '4D interface items require Item Code naming.')
    plans = []
    # Resolve all source BOMs and collisions before any insert or submit.
    for source in sources:
        source_bom = frappe.get_doc('BOM', source.default_bom)
        _require(source_bom.item == source.name and source_bom.docstatus == 1
                 and source_bom.is_active, 'Invalid source BOM for ' + source.name)
        _require(sum(r.item_code == '5D1000' for r in source_bom.items) == 1,
                 'Expected exactly one 5D1000 body in ' + source_bom.name)
        prices = [frappe.get_doc('Item Price', p.name) for p in frappe.get_all(
            'Item Price', filters={'item_code': source.name, 'selling': 1}, fields=['name'])]
        files = frappe.get_all('File', filters={'attached_to_doctype': 'Item',
            'attached_to_name': source.name, 'is_folder': 0}, fields=['name', 'file_url'])
        for prefix, interface, body_code in VARIANTS:
            spec = _spec(source, source_bom, prefix, interface, body_code)
            existing = frappe.get_doc('Item', spec.target) if frappe.db.exists('Item', spec.target) else None
            if existing:
                _require(existing.item_name.endswith('/' + interface)
                         and existing.reference_code == spec.reference_code,
                         'Existing Item conflicts with the requested variant: ' + spec.target)
            else:
                _require(not source.opening_stock and not source.standard_rate and not source.barcodes,
                         'Source has opening stock, automatic prices or barcodes: ' + source.name)
                owner = frappe.db.get_value('Item', {'reference_code': spec.reference_code}, 'name')
                _require(not spec.reference_code or not owner,
                         'Reference already belongs to another Item: ' + str(spec.reference_code))
            if not spec.pending:
                if existing and existing.default_bom:
                    _check_existing_bom(existing, spec)
                else:
                    _require(not frappe.db.exists('BOM', {'item': spec.target, 'docstatus': ['<', 2]}),
                             'Review the existing non-default BOM before migrating ' + spec.target)
                    _require(not frappe.db.exists('BOM', spec.target_bom),
                             'BOM name already occupied: ' + spec.target_bom)
                    body = frappe.get_doc('Item', body_code)
                    _require(not body.disabled and body.stock_uom == source.stock_uom,
                             'Variant body is disabled or has a different UOM: ' + body_code)
                    for row in source_bom.items:
                        if row.item_code != '5D1000':
                            _require(not frappe.db.get_value('Item', row.item_code, 'disabled'),
                                     'Source BOM contains a disabled component: ' + row.item_code)
            plans.append((source, source_bom, prices, files, spec))
    with _preserve_transaction_and_revisions():
        for source, source_bom, prices, files, spec in plans:
            if not frappe.db.exists('Item', spec.target):
                _copy_item(source, spec)
                counts['items'] += 1
            item = frappe.get_doc('Item', spec.target)
            if not spec.pending and not item.default_bom:
                _copy_bom(source_bom, item, spec)
                counts['boms'] += 1
            counts['prices'] += _copy_missing_prices(prices, item.name)
            counts['attachments'] += _copy_missing_attachments(source, files, item.name)
    return counts


def _require(condition, message):
    if not condition:
        raise frappe.ValidationError(message)


def _spec(source, source_bom, prefix, interface, body):
    target = prefix + source.name[3:]
    return frappe._dict(target=target, interface=interface, body=body,
        item_name=source.item_name + '/' + interface,
        reference_code=source.reference_code + '/' + interface if source.reference_code else None,
        source_bom=source_bom.name, target_bom='BOM-' + target + '-001',
        pending=source.name in PENDING_BOM_SOURCES)


def _copy_without_new_defaults(source):
    doc = frappe.copy_doc(source, ignore_no_copy=True)
    for field in source.meta.fields:
        if field.default is not None and source.get(field.fieldname) is None:
            doc.set(field.fieldname, '')
    return doc


def _description(source, spec, field):
    value = source.get(field)
    if not value:
        return value
    replacements = [(spec.source_bom, spec.target_bom), (source.item_name, spec.item_name)]
    if source.reference_code:
        replacements.append((source.reference_code, spec.reference_code))
    replacements.extend([(source.name, spec.target), ('5D1000', spec.body),
        ('P202-O — RVM mini', 'P202-O/' + spec.interface + ' — RVM mini ' + spec.interface)])
    for before, after in replacements:
        value = value.replace(before, after)
    if field == 'internal_description' and spec.pending:
        value = value.replace('Default active submitted BOM', 'Variant BOM pending')
        value = value.replace(spec.target_bom, 'Pending (source BOM: ' + spec.source_bom + ')')
        value += '<div><strong>BOM pending:</strong> Source valve head ' + ', '.join(
            PENDING_BOM_SOURCES[source.name]) + (
            ' is disabled. Item and selling prices created; variant BOM not created.</div>')
    value += '<div><strong>Communication interface:</strong> ' + spec.interface + '.</div>'
    if field == 'description' and frappe.db.get_single_value('Stock Settings', 'clean_description_html'):
        value = clean_html(value.replace('<strong>', '<b>').replace('</strong>', '</b>'))
    return sanitize_html(value, linkify=True)


def _copy_item(source, spec):
    item = _copy_without_new_defaults(source)
    item.item_code, item.item_name = spec.target, spec.item_name
    item.naming_series = source.naming_series or ''
    item.reference_code = spec.reference_code
    item.reference_name = spec.target + ': ' + spec.item_name
    for field in DESCRIPTION_FIELDS:
        item.set(field, _description(source, spec, field))
    item.qrcode = item.route = item.default_bom = item.item_default_bom = None
    item.bom_table, item.item_batch_costing, item.bom_cost = [], [], 0
    item.insert()
    _require(item.name == spec.target, 'Unexpected Item name: ' + item.name)
    return item


def _copy_bom(source, item, spec):
    body = frappe.get_doc('Item', spec.body)
    bom = _copy_without_new_defaults(source)
    bom.item, bom.item_name, bom.description = item.name, item.item_name, item.description
    bom.is_active, bom.is_default, bom.route, bom.exploded_items = 1, 1, None, []
    for row in bom.items:
        if row.item_code == '5D1000':
            row.item_code, row.item_name = body.name, body.item_name
            row.description = '<div>' + body.name + ' — ' + body.item_name + '</div>'
            row.bom_no, row.image, row.stock_uom = body.default_bom, body.image or '', body.stock_uom
            row.include_item_in_manufacturing = body.include_item_in_manufacturing
    bom.flags.interface_variant_child_boms = {r.idx: r.bom_no for r in bom.items}
    # Internal descriptions use this allocated name. Do not silently point them
    # at a different record when a prototype occupies the normal name.
    _require(not frappe.db.exists('BOM', spec.target_bom), 'BOM name already occupied: ' + spec.target_bom)
    bom.insert()
    _require(bom.name == spec.target_bom, 'Unexpected BOM name: ' + bom.name)
    bom.submit()
    _check_existing_bom(frappe.get_doc('Item', item.name), spec)
    return bom


def _check_existing_bom(item, spec):
    bom = frappe.get_doc('BOM', item.default_bom)
    _require(bom.item == item.name and bom.docstatus == 1 and bom.is_active and bom.is_default,
             'Invalid default BOM for ' + item.name)
    _require(sum(r.item_code == spec.body for r in bom.items) == 1
             and all(r.item_code != '5D1000' for r in bom.items),
             'Default BOM has the wrong interface body for ' + item.name)


def _price_key(price):
    # Empty legacy values compare equally with normalized SQL NULLs and dates
    # compare equally whether fetched as strings or datetime.date objects.
    return tuple(str(price.get(field) or '') for field in PRICE_KEY_FIELDS)


def _copy_missing_prices(prices, item_code):
    existing = {_price_key(p) for p in frappe.get_all('Item Price',
        filters={'item_code': item_code}, fields=list(PRICE_KEY_FIELDS))}
    count = 0
    for original in prices:
        key = _price_key(original)
        if key in existing:
            continue
        price = _copy_without_new_defaults(original)
        price.item_code = item_code
        price.insert()
        existing.add(key)
        count += 1
    return count


def _copy_missing_attachments(source, files, item_code):
    count = 0
    for original in files:
        if original.file_url == source.qrcode:
            continue  # Item.after_insert generates the new item's own QR code.
        if frappe.db.exists('File', {'attached_to_doctype': 'Item',
                'attached_to_name': item_code, 'file_url': original.file_url}):
            continue
        attachment = frappe.copy_doc(frappe.get_doc('File', original.name))
        attachment.attached_to_name = item_code
        attachment.insert()
        count += 1
    return count


@contextmanager
def _preserve_transaction_and_revisions():
    """Defer legacy hook commits and retain the copied sub-BOM revisions.

    Only this migration process is affected. An attempted rollback from a
    swallowed hook error must fail the patch so its runner rolls back all work.
    """
    from amf.amf.utils import bom_child_bom_resolver
    commit, rollback = frappe.db.commit, frappe.db.rollback
    resolver = bom_child_bom_resolver.apply_item_default_boms_to_rows

    def defer_commit(*args, **kwargs):
        pass

    def reject_rollback(*args, **kwargs):
        raise _HookRollback('4D variant creation failed inside a document hook.')

    def preserve_revisions(doc, method=None):
        resolver(doc, method)
        expected = doc.flags.get('interface_variant_child_boms')
        if expected:
            for row in doc.items:
                row.bom_no = expected[row.idx]

    frappe.db.commit, frappe.db.rollback = defer_commit, reject_rollback
    bom_child_bom_resolver.apply_item_default_boms_to_rows = preserve_revisions
    try:
        yield
    except _HookRollback as error:
        raise frappe.ValidationError(str(error))
    finally:
        frappe.db.commit, frappe.db.rollback = commit, rollback
        bom_child_bom_resolver.apply_item_default_boms_to_rows = resolver


class _HookRollback(BaseException):
    pass
