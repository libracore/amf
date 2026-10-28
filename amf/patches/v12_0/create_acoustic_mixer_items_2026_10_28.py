"""Replay the Acoustic Mixer products and their CHF 2,500 costing BOMs.

Create only missing records. Existing matching products are retained without
repricing them or rewriting their descriptions. Resolve collisions before any
insert; the patch runner owns the transaction, including legacy hook writes.
"""

from contextlib import contextmanager
from decimal import Decimal
from html import escape

import frappe


TARGET = Decimal('2500.0000')
EXPENSE_ACCOUNT = '4400 - Cost of production services/materials (COGS) - AMF21'
SPECS = (
    dict(source='45D040', source_bom='BOM-45D040-011', target='45D040-AM',
         reference='P100O300040S1000P-AM', cost_item='GX.RD-1000'),
    dict(source='46F055', source_bom='BOM-46F055-009', target='46F055-AM',
         reference='P101O300055S5000P-AM', cost_item='GX.RD-1001'),
)


def execute():
    frappe.set_user('Administrator')
    counts = dict(items=0, boms=0)
    if not any(frappe.db.exists('Item', spec['source']) for spec in SPECS):
        return counts  # Sites without these AMF source products are outside scope.
    _require(frappe.db.get_default('item_naming_by') == 'Item Code',
             'Acoustic Mixer products require Item Code naming.')
    plans = [_plan(frappe._dict(spec)) for spec in SPECS]
    with _preserve_transaction_and_revisions(plans):
        for plan in plans:
            if not plan.cost:
                plan.cost = _new_cost_item(plan)
                plan.cost.insert()
                counts['items'] += 1
            if not plan.item:
                plan.item = _copy_item(plan)
                plan.item.insert()
                counts['items'] += 1
            if not plan.existing_bom:
                bom = plan.bom
                bom.insert()
                _require(bom.name == plan.bom_name, 'Unexpected BOM name: ' + bom.name)
                bom.submit()
                item = frappe.get_doc('Item', plan.target)
                item.internal_description = _internal_description(plan, bom)
                item.save()
                bom.update_cost(update_parent=False)
                _check_bom(frappe.get_doc('Item', plan.target),
                           frappe.get_doc('BOM', bom.name), plan)
                counts['boms'] += 1
    return counts


def _require(condition, message):
    if not condition:
        raise frappe.ValidationError(message)


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.0001'))


def _allocation(base_cost):
    rate = TARGET - _money(base_cost)
    _require(rate > 0, 'Acoustic Mixer source cost must be below CHF 2500.00.')
    return rate


def _structure(rows):
    return [(r.item_code, r.qty, r.uom, r.conversion_factor, r.bom_no or '',
             r.include_item_in_manufacturing) for r in rows]


def _plan(spec):
    source = frappe.get_doc('Item', spec.source)
    source_bom = frappe.get_doc('BOM', spec.source_bom)
    _require(source.item_group == 'Product' and not source.disabled,
             'Invalid Acoustic Mixer source Item: ' + spec.source)
    _require(source_bom.item == source.name and source_bom.docstatus == 1
             and source_bom.is_active and source_bom.quantity == 1
             and source_bom.currency == 'CHF' and source_bom.rm_cost_as_per == 'Valuation Rate',
             'Invalid Acoustic Mixer source BOM: ' + spec.source_bom)
    spec.update(dict(source_item=source, source_bom_doc=source_bom,
                     bom_name='BOM-' + spec.target + '-001',
                     item_name=source.item_name + ' - Acoustic Mixer',
                     item=None, cost=None, existing_bom=False))
    owner = frappe.db.get_value('Item', {'reference_code': spec.reference}, 'name')
    _require(not owner or owner == spec.target, 'Item reference collision: ' + spec.reference)
    if frappe.db.exists('Item', spec.target):
        spec.item = frappe.get_doc('Item', spec.target)
        item = spec.item
        _require((item.item_name, item.reference_code, item.item_group, item.stock_uom,
                  item.is_stock_item, item.disabled) ==
                 (spec.item_name, spec.reference, 'Product', 'Nos', 1, 0),
                 'Existing Item conflicts with Acoustic Mixer product: ' + spec.target)
    if frappe.db.exists('Item', spec.cost_item):
        spec.cost = frappe.get_doc('Item', spec.cost_item)
        cost = spec.cost
        _require((cost.item_name, cost.item_group, cost.stock_uom, cost.is_stock_item,
                  cost.include_item_in_manufacturing, cost.is_sales_item,
                  cost.is_purchase_item, cost.disabled) ==
                 (_cost_name(spec), 'Generic Item', 'Nos', 0, 0, 0, 0, 0),
                 'Existing Item conflicts with Acoustic Mixer allocation: ' + spec.cost_item)
        _require(_money(cost.valuation_rate) > 0,
                 'Acoustic Mixer allocation must have a positive rate: ' + spec.cost_item)
    boms = frappe.get_all('BOM', filters={'item': spec.target, 'docstatus': ['<', 2]},
                          fields=['name'])
    if boms:
        _require(len(boms) == 1 and spec.item and spec.cost
                 and spec.item.default_bom == boms[0].name,
                 'Review existing Acoustic Mixer BOMs for ' + spec.target)
        spec.bom = frappe.get_doc('BOM', boms[0].name)
        spec.existing_bom = True
        _check_bom(spec.item, spec.bom, spec)
        return spec
    _require(not spec.item or not spec.item.default_bom,
             'Unexpected default BOM for ' + spec.target)
    _require(not frappe.db.exists('BOM', spec.bom_name), 'BOM name occupied: ' + spec.bom_name)
    _require(frappe.db.exists('Account', EXPENSE_ACCOUNT),
             'Missing Acoustic Mixer expense account: ' + EXPENSE_ACCOUNT)
    bom = frappe.copy_doc(source_bom)
    bom.item, bom.item_name = spec.target, spec.item_name
    bom.is_active, bom.is_default, bom.route, bom.exploded_items = 1, 1, None, []
    for row in bom.items:
        _require(not frappe.db.get_value('Item', row.item_code, 'disabled'),
                 'Disabled source component: ' + row.item_code)
        rate = bom.get_rm_rate(row.as_dict())
        if rate:
            row.rate = rate
    bom.calculate_cost()
    spec.base_cost, spec.allocation = _money(bom.total_cost), _allocation(bom.total_cost)
    if spec.cost:
        _require(_money(spec.cost.valuation_rate) == spec.allocation,
                 'Existing allocation rate differs; review ' + spec.cost_item)
    bom.append('items', dict(item_code=spec.cost_item, item_name=_cost_name(spec),
        description=_cost_description(spec), qty=1, stock_qty=1, uom='Nos',
        stock_uom='Nos', conversion_factor=1, rate=float(spec.allocation),
        include_item_in_manufacturing=0))
    bom.flags.acoustic_mixer_child_boms = {r.idx: r.bom_no for r in bom.items}
    bom.calculate_cost()
    _require(_money(bom.total_cost) == TARGET, 'Cannot reach exact Acoustic Mixer BOM target.')
    spec.bom = bom
    return spec


def _cost_name(plan):
    return 'Acoustic Mixer R&D cost allocation - ' + plan.target


def _cost_description(plan):
    return ('<div><strong>Acoustic Mixer project - R&amp;D cost allocation</strong></div>'
            '<div>Dedicated costing component for {} (source {}).</div>'
            '<div>One Nos per finished product. CHF {:.4f} per Nos brings the BOM '
            'from CHF {:.4f} to CHF 2500.00 at creation, including source scrap credits.</div>'
            '<div>Non-stock costing component; no physical material transfer. '
            'Review this allocation when underlying BOM costs change.</div>').format(
                plan.target, plan.source, plan.allocation, plan.base_cost)


def _new_cost_item(plan):
    return frappe.get_doc(dict(doctype='Item', item_code=plan.cost_item,
        item_name=_cost_name(plan), item_group='Generic Item', item_type='Other',
        stock_uom='Nos', is_stock_item=0, include_item_in_manufacturing=0,
        is_purchase_item=0, is_sales_item=0, valuation_rate=float(plan.allocation),
        standard_rate=0, description=_cost_description(plan),
        uoms=[dict(uom='Nos', conversion_factor=1)],
        item_defaults=[dict(company=plan.source_bom_doc.company, expense_account=EXPENSE_ACCOUNT)]))


def _copy_item(plan):
    source = plan.source_item
    item = frappe.copy_doc(source)
    item.item_code, item.item_name, item.reference_code = plan.target, plan.item_name, plan.reference
    item.reference_name = plan.target + ': ' + plan.item_name
    item.description = (source.description or '').replace(plan.source, plan.target) + (
        '<div><br></div><div><strong>Special project:</strong> Acoustic Mixer</div>'
        '<div><strong>Based on:</strong> ' + plan.source + '</div>')
    item.internal_description = _internal_description(plan, plan.bom)
    item.default_bom = item.item_default_bom = item.qrcode = item.route = item.real_cost = None
    item.bom_table, item.item_batch_costing = [], []
    for field in ('bom_cost', 'opening_stock', 'standard_rate', 'last_purchase_rate',
                  'average_monthly_outflow', 'annual_outflow', 'total_projected_qty'):
        item.set(field, 0)
    item.valuation_rate = float(TARGET)
    return item


def _internal_description(plan, bom):
    parts = [
        '<div><strong>Production configuration - Acoustic Mixer</strong></div>',
        '<div><strong>ERP item:</strong> {} - {}</div>'.format(plan.target, escape(plan.item_name)),
        '<div><strong>R&amp;D reference:</strong> {}</div>'.format(escape(plan.reference)),
        '<div><strong>Project:</strong> Acoustic Mixer</div>',
        '<div><strong>Source item:</strong> {}</div>'.format(plan.source),
        '<div><strong>Source BOM:</strong> {}</div>'.format(plan.source_bom),
        '<div><strong>Production basis:</strong> Default active submitted BOM</div>',
        '<div><strong>BOM:</strong> {}; output quantity 1 Nos</div>'.format(bom.name or plan.bom_name),
        '<div><strong>BOM components:</strong></div><ul>',
    ]
    for row in bom.items:
        parts.append('<li>{:g} x {} - {} {}</li>'.format(
            row.qty, escape(row.item_code), escape(row.item_name), escape(row.uom)))
    parts.append('</ul>')
    for row in bom.scrap_items:
        parts.append('<div><strong>Scrap recovery:</strong> {:g} x {}; credit CHF {:.4f}</div>'.format(
            row.stock_qty, escape(row.item_code), row.amount))
    parts.append('<div><strong>Project cost allocation:</strong> 1 x {}, CHF {:.4f}; '
        'BOM target CHF 2500.00 per Nos at creation. Recalculate the allocation if '
        'component costs change.</div>'.format(plan.cost_item, plan.allocation))
    return ''.join(parts)


def _check_bom(item, bom, plan):
    _require(bom.item == plan.target and bom.docstatus == 1 and bom.is_active
             and bom.is_default and bom.quantity == 1 and bom.currency == 'CHF'
             and bom.company == plan.source_bom_doc.company,
             'Invalid Acoustic Mixer default BOM for ' + plan.target)
    physical = [r for r in bom.items if r.item_code != plan.cost_item]
    allocations = [r for r in bom.items if r.item_code == plan.cost_item]
    _require(_structure(physical) == _structure(plan.source_bom_doc.items)
             and [(r.item_code, r.stock_qty, r.rate) for r in bom.scrap_items]
             == [(r.item_code, r.stock_qty, r.rate) for r in plan.source_bom_doc.scrap_items],
             'Acoustic Mixer BOM differs from approved source structure: ' + bom.name)
    _require(len(allocations) == 1 and allocations[0].qty == 1
             and allocations[0].stock_qty == 1 and allocations[0].conversion_factor == 1
             and allocations[0].uom == 'Nos' and allocations[0].stock_uom == 'Nos'
             and not allocations[0].bom_no
             and not allocations[0].include_item_in_manufacturing
             and _money(allocations[0].rate) == _money(plan.cost.valuation_rate),
             'Invalid Acoustic Mixer allocation row: ' + bom.name)
    _require(_money(bom.total_cost) == TARGET and _money(bom.base_total_cost) == TARGET
             and _money(item.valuation_rate) == TARGET and _money(item.bom_cost) == TARGET
             and item.default_bom == bom.name and item.item_default_bom == bom.name,
             'Acoustic Mixer costs or Item BOM snapshots differ from CHF 2500: ' + plan.target)


@contextmanager
def _preserve_transaction_and_revisions(plans=()):
    from amf.amf.utils import bom_child_bom_resolver, item_code_family
    commit, rollback = frappe.db.commit, frappe.db.rollback
    resolver = bom_child_bom_resolver.apply_item_default_boms_to_rows
    validator = item_code_family.validate_new_item_family
    approved = {p.target: p for p in plans}

    def defer_commit(*args, **kwargs):
        pass

    def reject_rollback(*args, **kwargs):
        # Legacy hooks catch Exception and could swallow an ordinary error.
        raise _HookRollback('Acoustic Mixer creation failed inside a document hook.')

    def preserve_revisions(doc, method=None):
        resolver(doc, method)
        expected = doc.flags.get('acoustic_mixer_child_boms')
        if expected:
            for row in doc.items:
                row.bom_no = expected[row.idx]

    def validate_project_code(doc, method=None):
        # These explicitly approved project copies predate the six-character
        # family guard. Limit the insertion exception to this migration process
        # and the exact planned identities; ordinary Item creation stays guarded.
        plan = approved.get(doc.get('item_code'))
        if plan:
            _require(doc.get('item_group') == 'Product'
                     and doc.get('reference_code') == plan.reference
                     and doc.get('item_name') == plan.item_name,
                     'Unexpected Acoustic Mixer project identity.')
            return
        return validator(doc, method)

    frappe.db.commit, frappe.db.rollback = defer_commit, reject_rollback
    bom_child_bom_resolver.apply_item_default_boms_to_rows = preserve_revisions
    item_code_family.validate_new_item_family = validate_project_code
    try:
        with item_code_family.atomic_family_creation():
            yield
    except _HookRollback as error:
        raise frappe.ValidationError(str(error))
    finally:
        frappe.db.commit, frappe.db.rollback = commit, rollback
        bom_child_bom_resolver.apply_item_default_boms_to_rows = resolver
        item_code_family.validate_new_item_family = validator


class _HookRollback(BaseException):
    pass
