"""Install the four NKN tube caps and their default BOMs on the AMF company site.

Stage the supplied PDFs in sites/<site>/private/nkn_tube_cap_drawings/ before
bench migrate to import them as private Item attachments. For a later import,
stage the same files and run bench --site <site> execute
amf.patches.v12_0.create_nkn_tube_caps_2026_11_26.execute.
"""

from collections import namedtuple
from hashlib import sha256
from html import escape
from pathlib import Path

import frappe

from amf.amf.utils.item_code_family import atomic_family_creation


COMPANY = 'Advanced Microfluidics SA'
WAREHOUSE = 'Main Stock - AMF21'
GROUP = 'Fluidic Components'
BAR_LENGTH_M = 0.04
DRAWINGS_DIR = 'nkn_tube_cap_drawings'
Cap = namedtuple('Cap', 'code reference title diameter requested material bar_diameter file_revision drawing_hash')
CAPS = (
    Cap('700070', 'NKN.2024', 'Tube Cap 5mL', 23, 40, 'MAT.1020', 30, '02',
        'c2b2ac63d72597a4faa241252d7a53b6448656d51e1d3484e41e2ca6e06e18e4'),
    Cap('700071', 'NKN.2031', 'Tube Cap 50mL', 36, 5, 'MAT.1010', 40, '01',
        '67921015c42e0de21de2996cf3ca563a840aec02f25ef2ec9e74828596a2b608'),
    Cap('700072', 'NKN.2039', 'Tube Cap 5mL 1mm hole', 23, 30, 'MAT.1020', 30, '01',
        '68b4fe29fa68da181fd511401557c65af914f652be95858398c0ef94e349db38'),
    Cap('700073', 'NKN.2040', 'Tube Cap 50mL 1mm hole', 36, 5, 'MAT.1010', 40, '01',
        '644cec971d69632e86503f0ae0447531b7d404bc59f2f488a94611e3e94a04fb'),
)


def execute():
    result = dict(items=0, boms=0, attachments=0, missing_drawings=[])
    if not frappe.db.exists('Company', COMPANY):
        return result
    frappe.set_user('Administrator')
    _require(frappe.db.get_single_value('Stock Settings', 'item_naming_by') == 'Item Code',
             'NKN tube caps require Item Code naming.')
    _require(frappe.db.exists('Item Group', {'name': GROUP, 'is_group': 0}), f'Missing Item Group {GROUP}.')
    _require(frappe.db.exists('Warehouse', {'name': WAREHOUSE, 'company': COMPANY, 'is_group': 0, 'disabled': 0}),
             f'Missing active Warehouse {WAREHOUSE}.')

    plans = [(cap, *_plan(cap), *_drawing_source(cap)) for cap in CAPS]
    with atomic_family_creation():
        for cap, item, bom, drawing_url, content in plans:
            if item is None:
                item = _new_item(cap).insert()
                result['items'] += 1
            if bom is None:
                bom = _new_bom(cap).insert()
                bom.submit()
                item.reload()
                _validate_bom(cap, item, bom)
                result['boms'] += 1
            if content is not None:
                attachment = frappe.get_doc(dict(doctype='File', file_name=_filename(cap), content=content,
                    is_private=1, attached_to_doctype='Item', attached_to_name=item.name)).insert()
                drawing_url = attachment.file_url
                _require(_matches_drawing(cap, drawing_url), f'Private PDF verification failed for {cap.reference}.')
                result['attachments'] += 1
            if drawing_url:
                _register_drawing(cap, item, drawing_url)
            else:
                result['missing_drawings'].append(_filename(cap))

    if result['missing_drawings']:
        print(f'NKN tube caps: import missing PDFs from the site private/{DRAWINGS_DIR}/ directory '
              f'with {__name__}.execute: ' + ', '.join(result['missing_drawings']))
    return result


def _require(condition, message):
    if not condition:
        raise frappe.ValidationError(message)


def _plan(cap):
    owners = frappe.get_all('Item', filters={'reference_code': cap.reference}, fields=['name'])
    _require(all(row.name == cap.code for row in owners), f'Item reference already in use: {cap.reference}.')

    raw = frappe.get_doc('Item', cap.material)
    _require((raw.item_group, raw.stock_uom, raw.tag_raw_mat) == ('Raw Material', 'Meter', 'PEEK')
             and raw.is_stock_item and raw.is_purchase_item and raw.include_item_in_manufacturing
             and not raw.disabled and not raw.default_bom and f'Ø{cap.bar_diameter}.0mm' in raw.item_name,
             f'Invalid PEEK bar definition for {cap.material}.')

    item = frappe.get_doc('Item', cap.code) if frappe.db.exists('Item', cap.code) else None
    if item is not None:
        _require((item.item_name, item.reference_code, item.item_group, item.item_type, item.stock_uom,
                  item.is_stock_item, item.disabled) == (cap.title, cap.reference, GROUP, 'Component', 'Nos', 1, 0),
                 f'Existing Item {cap.code} differs from {cap.reference}.')

    candidates = frappe.get_all('BOM', filters={'item': cap.code, 'is_active': 1, 'docstatus': ['<', 2]},
                                fields=['name'])
    bom = None
    if candidates:
        _require(len(candidates) == 1 and item is not None and item.default_bom == candidates[0].name,
                 f'Review the active BOMs for {cap.code}.')
        bom = frappe.get_doc('BOM', candidates[0].name)
        _validate_bom(cap, item, bom)
    else:
        _require(item is None or not item.default_bom, f'Unexpected default BOM on {cap.code}.')
    return item, bom


def _validate_bom(cap, item, bom):
    _require((bom.item, bom.company, bom.quantity, bom.uom) == (cap.code, COMPANY, 1, 'Nos')
             and bom.docstatus == 1 and bom.is_active and bom.is_default and item.default_bom == bom.name,
             f'Invalid default BOM on {cap.code}.')
    materials = [(row.item_code, row.qty, row.stock_qty, row.uom, row.stock_uom, row.conversion_factor,
                  row.include_item_in_manufacturing, bool(row.bom_no)) for row in bom.items]
    _require(materials == [(cap.material, BAR_LENGTH_M, BAR_LENGTH_M, 'Meter', 'Meter', 1, 1, False)],
             f'Existing BOM {bom.name} differs from the NKN tube cap recipe.')


def _new_item(cap):
    drawing_note = f'Drawing: {cap.reference}.01.01.DRWG.'
    if cap.file_revision != '01':
        drawing_note += (' The supplied PDF filename indicates revision 02 and its title block '
                         'indicates revision 01. Confirm the revision before releasing the drawing.')
    return frappe.get_doc(dict(doctype='Item', item_code=cap.code, item_name=cap.title,
        item_group=GROUP, item_type='Component', stock_uom='Nos', tag_raw_mat='PEEK',
        reference_code=cap.reference, reference_name=f'{cap.code}: {cap.title}',
        is_stock_item=1, is_purchase_item=0, is_sales_item=0, include_item_in_manufacturing=1,
        default_material_request_type='Manufacture', custom_item=1,
        item_defaults=[dict(company=COMPANY, default_warehouse=WAREHOUSE)],
        description=_paragraphs(cap.title, f'Machined from virgin PEEK. Finished outside diameter '
            f'Ø{cap.diameter} ±0.05 mm. Nominal finished length 36 mm.'),
        internal_description=_paragraphs(f'Initial lot requested on 26/11/2026: {cap.requested} pcs.',
            f'BOM: virgin PEEK fluteck K300 round bar Ø{cap.bar_diameter} mm ({cap.material}).',
            'Estimated bar consumption: 40 mm/pc, based on 36 mm finished length and 4 mm cutting '
            f'and facing allowance. Initial lot estimate: {cap.requested * BAR_LENGTH_M:.2f} m.', drawing_note)))


def _new_bom(cap):
    return frappe.get_doc(dict(doctype='BOM', item=cap.code, company=COMPANY, currency='CHF',
        quantity=1, uom='Nos', rm_cost_as_per='Valuation Rate', is_active=1, is_default=1, with_operations=0,
        items=[dict(item_code=cap.material, qty=BAR_LENGTH_M, uom='Meter', stock_uom='Meter',
                    conversion_factor=1, include_item_in_manufacturing=1)]))


def _paragraphs(*lines):
    return ''.join(f'<p>{escape(line)}</p>' for line in lines)


def _filename(cap):
    return f'{cap.reference}.01.{cap.file_revision}.DRWG {cap.title}.pdf'


def _drawing_source(cap):
    stem = Path(_filename(cap)).stem
    files = frappe.get_all('File', filters={'attached_to_doctype': 'Item', 'attached_to_name': cap.code,
                           'is_private': 1, 'file_name': ['like', stem + '%.pdf']}, fields=['file_url'])
    for row in files:
        if _matches_drawing(cap, row.file_url):
            return row.file_url, None
    staged = Path(frappe.get_site_path('private', DRAWINGS_DIR, _filename(cap)))
    if not staged.is_file():
        return None, None
    content = staged.read_bytes()
    _require(sha256(content).hexdigest() == cap.drawing_hash, f'Unexpected PDF content: {staged.name}.')
    return None, content


def _matches_drawing(cap, url):
    prefix = '/private/files/'
    if not (url or '').startswith(prefix):
        return False
    path = Path(frappe.get_site_path('private', 'files', url[len(prefix):]))
    return path.is_file() and sha256(path.read_bytes()).hexdigest() == cap.drawing_hash


def _register_drawing(cap, item, url):
    # NKN.2024 has a revision mismatch. Keep its source as a private attachment.
    if cap.file_revision != '01' or any(row.drawing == url for row in item.drawing_item):
        return
    is_default = int(not item.drawing_item)
    item.append('drawing_item', dict(drawing=url, item_code=item.name, item_name=item.item_name,
        reference_code=cap.reference, version='01', revision='01', is_active=is_default, is_default=is_default))
    item.save()
