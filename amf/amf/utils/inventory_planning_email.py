# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import OrderedDict
from html import escape

from frappe.utils import cstr, flt


REPORT_GROUP_PRIORITY = (
	"Part",
	"Cables",
	"Electronic Boards",
	"Assembly",
	"Plug",
	"Valve Seat",
	"Valve Head",
	"Body",
)
_EXCLUDED_REPORT_GROUPS = {
	"poduct",
	"poducts",
	"product",
	"products",
	"plunger",
	"plungers",
}
_REPORT_GROUP_ALIASES = {
	"part": "Part",
	"parts": "Part",
	"cable": "Cables",
	"cables": "Cables",
	"electronic board": "Electronic Boards",
	"electronic boards": "Electronic Boards",
	"assembly": "Assembly",
	"assemblies": "Assembly",
	"plug": "Plug",
	"plugs": "Plug",
	"seat": "Valve Seat",
	"seats": "Valve Seat",
	"valve seat": "Valve Seat",
	"valve seats": "Valve Seat",
	"valve head": "Valve Head",
	"valve heads": "Valve Head",
	"body": "Body",
	"bodies": "Body",
}


def actionable_report_items(items):
	"""Return replenishment rows grouped by priority and shortage descending."""
	rows = [
		item for item in (items or [])
		if flt(item.get("recommended_qty")) > 0
		and _normalized_group_name(item) not in _EXCLUDED_REPORT_GROUPS
	]
	return sorted(rows, key=_report_item_sort_key)


def group_report_items(items):
	grouped = OrderedDict()
	for item in actionable_report_items(items):
		group_name = cstr(item.get("item_group")).strip() or "Unassigned"
		grouped.setdefault(group_name, []).append(item)
	return grouped


def build_report_summary(items):
	rows = actionable_report_items(items)
	return {
		"item_count": len(rows),
		"group_count": len({cstr(row.get("item_group")) for row in rows}),
		"critical_count": sum(
			1 for row in rows if cstr(row.get("risk")).lower() == "critical"
		),
		"expedite_count": sum(1 for row in rows if row.get("expedite")),
		"shortage_qty": sum(flt(row.get("shortage_qty")) for row in rows),
		"recommended_qty": sum(flt(row.get("recommended_qty")) for row in rows),
	}


def build_weekly_safety_stock_email(
	items,
	company,
	generated_at,
	horizon_days=90,
	report_url=None,
	item_url_builder=None,
):
	"""Render an email-client-friendly weekly inventory shortage report."""
	grouped = group_report_items(items)
	report_button = ""
	if report_url:
		report_button = (
			'<a href="{0}" style="display:inline-block;background:#ffffff;color:#172554;'
			'text-decoration:none;font-size:13px;font-weight:700;padding:10px 16px;'
			'border-radius:7px;">Open Inventory Planning</a>'
		).format(_html(report_url))

	sections = "".join(
		_render_group_section(group_name, rows, item_url_builder)
		for group_name, rows in grouped.items()
	)
	if not sections:
		sections = (
			'<div style="padding:36px 24px;text-align:center;background:#f0fdf4;'
			'border:1px solid #bbf7d0;border-radius:10px;color:#166534;">'
			'<div style="font-size:28px;line-height:1;">&#10003;</div>'
			'<div style="font-size:16px;font-weight:700;margin-top:10px;">'
			'No replenishment action is required</div>'
			'<div style="font-size:13px;margin-top:5px;">No projected safety-stock breach '
			'was found in the planning horizon.</div></div>'
		)

	return (
		'<div style="margin:0;padding:0;background:#f3f6fb;color:#1f2937;'
		'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;">'
		'{styles}'
		'<div style="max-width:1120px;margin:0 auto;padding:24px 12px;">'
		'<div style="background:#172554;border-radius:12px 12px 0 0;padding:26px 28px;">'
		'<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'
		'<tr><td style="vertical-align:top;color:#ffffff;">'
		'<div style="font-size:12px;font-weight:700;letter-spacing:1.4px;'
		'text-transform:uppercase;color:#93c5fd;">Weekly inventory control</div>'
		'<div style="font-size:26px;line-height:1.25;font-weight:750;margin-top:5px;">'
		'Safety Stock Report</div>'
		'<div style="font-size:13px;color:#cbd5e1;margin-top:7px;">{company} &middot; '
		'Firm {horizon}-day stock projection</div></td>'
		'<td style="vertical-align:middle;text-align:right;white-space:nowrap;">{button}</td>'
		'</tr></table></div>'
		'<div style="background:#ffffff;border:1px solid #dbe3ef;border-top:0;'
		'border-radius:0 0 12px 12px;padding:24px;">'
		'<div style="font-size:14px;line-height:1.6;color:#475569;margin-bottom:18px;">'
		'Items requiring replenishment are grouped in this priority: '
		'<strong style="color:#1e293b;">Part, Cables, Electronic Boards, Assembly, '
		'Plug, Seat, Valve Head, and Body</strong>. Within every group, '
		'items are sorted by projected shortage from highest to lowest.</div>'
		'{sections}'
		'<div style="margin-top:22px;padding-top:15px;border-top:1px solid #e2e8f0;'
		'font-size:11px;line-height:1.55;color:#64748b;">'
		'Generated {generated_at}. Shortage is the largest negative balance in the firm '
		'projection. Soft supply from Material Requests and unlinked Plannings does not '
		'hide a shortage. Potential replenish is the earliest outstanding submitted PO '
		"line schedule date; it is not a confirmed receipt date. Quantities are expressed "
		"in each item's stock UOM.</div>"
		'</div></div></div>'
	).format(
		styles=_email_styles(),
		company=_html(company),
		horizon=int(horizon_days or 90),
		button=report_button,
		sections=sections,
		generated_at=_html(generated_at),
	)


def _email_styles():
	return (
		'<style type="text/css">'
		'.ssr-group{margin:0 0 24px;border:1px solid #dbe3ef;border-radius:10px;overflow:hidden}'
		'.ssr-group-head{padding:13px 16px;background:#eaf0ff;border-bottom:1px solid #cbd8f0}'
		'.ssr-group-head table{width:100%;border:0;border-collapse:collapse}'
		'.ssr-group-name{font-size:15px;font-weight:700;color:#172554}'
		'.ssr-group-count{font-size:11px;color:#64748b;margin-left:8px}'
		'.ssr-group-total{text-align:right;font-size:11px;color:#475569;white-space:nowrap}'
		'.ssr-table{width:100%;border:0;border-collapse:collapse;table-layout:fixed}'
		'.ssr-table th{padding:9px 8px;border-bottom:1px solid #e2e8f0;background:#f8fafc;'
		'color:#475569;font-size:10px;line-height:1.2;text-transform:uppercase;'
		'letter-spacing:.35px;font-weight:700;text-align:left}'
		'.ssr-table th.n,.ssr-table td:nth-child(n+2):nth-child(-n+6){text-align:right}'
		'.ssr-table td{padding:10px 8px;border-bottom:1px solid #edf2f7;vertical-align:top;'
		'font-size:10px;line-height:1.35;color:#334155}'
		'.ssr-table tbody tr:nth-child(even){background:#fbfdff}'
		'.ssr-table td:nth-child(n+2):nth-child(-n+6){font-size:11px;white-space:nowrap}'
		'.ssr-table td:nth-child(4){color:#b91c1c;font-weight:700}'
		'.ssr-table td:nth-child(5){color:#1d4ed8;font-weight:700}'
		'.ssr-table .i{font-size:12px;line-height:1.3;color:#1d4ed8}'
		'.ssr-table a.i{text-decoration:none}'
		'.ssr-table i{display:block;font-size:9px;font-style:normal;color:#94a3b8;margin-top:2px}'
		'.ssr-table .x,.ssr-table .r{color:#b91c1c}'
		'.ssr-table .w{color:#c2410c}.ssr-table .v{color:#7c3aed}'
		'</style>'
	)


def _report_item_sort_key(item):
	group_name = cstr(item.get("item_group")).strip() or "Unassigned"
	canonical_group = _REPORT_GROUP_ALIASES.get(group_name.lower())
	if canonical_group in REPORT_GROUP_PRIORITY:
		group_key = (REPORT_GROUP_PRIORITY.index(canonical_group), "")
	else:
		group_key = (len(REPORT_GROUP_PRIORITY), group_name.lower())
	return (
		group_key,
		-flt(item.get("shortage_qty")),
		-flt(item.get("recommended_qty")),
		cstr(item.get("shortage_date") or item.get("safety_breach_date") or "9999-12-31"),
		cstr(item.get("item_code")).lower(),
	)


def _normalized_group_name(item):
	return cstr(item.get("item_group")).strip().lower()


def _render_group_section(group_name, rows, item_url_builder):
	group_shortage = sum(flt(row.get("shortage_qty")) for row in rows)
	group_replenishment = sum(flt(row.get("recommended_qty")) for row in rows)
	body = "".join(
		_render_item_row(row, index, item_url_builder)
		for index, row in enumerate(rows)
	)
	return (
		'<div class="ssr-group"><div class="ssr-group-head">'
		'<table role="presentation"><tr><td><span class="ssr-group-name">{group}</span>'
		'<span class="ssr-group-count">{count} item{plural}</span></td>'
		'<td class="ssr-group-total">'
		'Shortage <strong style="color:#b91c1c;">{shortage}</strong> &middot; '
		'Replenish <strong style="color:#1d4ed8;">{replenishment}</strong></td></tr>'
		'</table></div>'
		'<table class="ssr-table"><thead><tr>{headers}</tr></thead>'
		'<tbody>{body}</tbody></table></div>'
	).format(
		group=_html(group_name),
		count=len(rows),
		plural="" if len(rows) == 1 else "s",
		shortage=_format_qty(group_shortage),
		replenishment=_format_qty(group_replenishment),
		headers="".join([
			_table_header("Item", "24%"),
			_table_header("On hand", "8%", True),
			_table_header("Min. projected", "11%", True),
			_table_header("Shortage", "9%", True),
			_table_header("Replenish", "10%", True),
			_table_header("Safety / ROP", "12%", True),
			_table_header("Risk date", "13%"),
			_table_header("Potential replenish", "13%"),
		]),
		body=body,
	)


def _table_header(label, width, numeric=False):
	return '<th width="{0}"{1}>{2}</th>'.format(
		width,
		' class="n"' if numeric else "",
		_html(label),
	)


def _render_item_row(item, index, item_url_builder):
	item_code = cstr(item.get("item_code"))
	item_name = cstr(item.get("item_name")) or item_code
	item_code_html = '<b class="i">{0}</b>'.format(_html(item_code))
	if item_url_builder:
		item_code_html = '<a class="i" href="{0}">{1}</a>'.format(
			_html(item_url_builder(item_code)), _html(item_code)
		)
	shortage_qty = flt(item.get("shortage_qty"))
	minimum_qty = flt(item.get("minimum_projected_qty"))
	risk = cstr(item.get("risk")).lower()
	risk_date = item.get("shortage_date") or item.get("safety_breach_date")
	risk_label = "Stockout" if item.get("shortage_date") else "Safety breach"
	risk_class = {"critical": "r", "action": "w"}.get(risk, "v")
	replenish_date = item.get("potential_replenish_date")
	if replenish_date:
		replenish_class = "x" if item.get("potential_replenish_overdue") else ""
		replenish_note = (
			"Overdue PO schedule"
			if item.get("potential_replenish_overdue")
			else "PO schedule date"
		)
		replenish_cell = '<td><b class="{0}">{1}</b><i>{2}</i></td>'.format(
			replenish_class, _html(replenish_date), replenish_note
		)
	else:
		replenish_cell = '<td><span style="color:#94a3b8;">No open PO</span></td>'
	return (
		'<tr><td>{code}<i>{name}</i></td>'
		'{actual}{minimum}{shortage}{recommended}'
		'<td>{safety}<i>ROP {rop}</i></td>'
		'<td><b class="{risk_class}">{risk_label}</b><i>{risk_date}</i></td>'
		'{replenish_cell}'
		'</tr>'
	).format(
		code=item_code_html,
		name=_html(item_name),
		actual=_numeric_cell(item.get("actual_qty")),
		minimum=_numeric_cell(minimum_qty, "x" if minimum_qty < 0 else ""),
		shortage=_numeric_cell(shortage_qty),
		recommended=_numeric_cell(item.get("recommended_qty")),
		safety=_format_qty(item.get("safety_stock")),
		rop=_format_qty(item.get("reorder_level")),
		risk_class=risk_class,
		risk_label=_html(risk_label),
		risk_date=_html(risk_date or "Within horizon"),
		replenish_cell=replenish_cell,
	)


def _numeric_cell(value, tone=""):
	class_attribute = ' class="{0}"'.format(tone) if tone else ""
	return '<td{0}>{1}</td>'.format(class_attribute, _format_qty(value))


def _format_qty(value):
	number = flt(value)
	if abs(number - round(number)) < 0.0001:
		return "{0:,}".format(int(round(number)))
	return "{0:,.2f}".format(number).rstrip("0").rstrip(".")


def _html(value):
	return escape(cstr(value), quote=True)
