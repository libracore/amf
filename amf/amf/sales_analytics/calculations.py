"""Calculation of invoice, booking, fulfillment and billing facts."""

from collections import defaultdict

from .definitions import (
    CHARGE_CODES, CLOSED_ORDER_STATUSES, COMMERCIAL_ORDER_TYPES, HISTORY_START, QUANTITY_TOLERANCE,
    ZERO, day, month_start, number,
)

NONCOMMERCIAL_PURPOSES = {
    "Commercial Sample", "Gift", "Loan", "Loan (temporary export)", "Material for manufacture",
    "Material for manufacture (no sale)", "Replacement under warranty", "Return after Repair",
}
RETURN_MOVEMENT_PURPOSES = {"Return to seller", "Returned Goods"}
COMMERCIAL_SETTLEMENTS = {"Full Product Sale", "Spare Parts Sale"}


def index_by(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def total(rows, field):
    return sum((number(row.get(field)) for row in rows), ZERO)


def issue(source, document, reason, item_code=None):
    return {"source": source, "document": document, "reason": reason, "item_code": item_code}


def header_fact(header, source, date_field):
    return {
        "source": source, "document": header["name"], "date": day(header[date_field]),
        "customer": header.get("customer"), "customer_name": header.get("customer_name"),
        "territory": header.get("territory"), "status": header.get("status"),
    }


def line_fact(header, row):
    return dict(
        header, line=row["name"], item_code=row.get("item_code"), item_name=row.get("item_name"),
        item_group=row.get("item_group"), qty=number(row.get("qty")), uom=row.get("uom"),
        stock_qty=number(row.get("stock_qty")), stock_uom=row.get("stock_uom"),
        item_net=number(row.get("base_net_amount")),
    )


def invoice_facts(headers, lines, charges):
    by_invoice = index_by(charges, "parent")
    facts = {}
    detail = []
    for row in headers:
        fact = header_fact(row, "Sales Invoice", "posting_date")
        fact.update(
            {field: ZERO for field in ("shipping", "card_charges", "vat", "other_charges")},
            item_net=number(row["base_net_total"]), gross=number(row["base_grand_total"]),
            original_invoice=row.get("return_against"), is_return=bool(row["is_return"]),
            currency=row["currency"], fx_rate=number(row["conversion_rate"]),
            legacy_ht=number(row.get("total_ht_company_currency")),
            posted_rounding=number(row.get("base_rounding_adjustment")),
        )
        for charge in by_invoice[row["name"]]:
            code = (charge["account_head"] or "").split(" ", 1)[0]
            field = CHARGE_CODES.get(code, "other_charges")
            value = charge["base_tax_amount_after_discount_amount"]
            fact[field] += number(charge["base_tax_amount"] if value is None else value)
        fact["revenue"] = fact["item_net"] + fact["shipping"] + fact["card_charges"]
        fact["gross_difference"] = fact["gross"] - fact["revenue"] - fact["vat"] - fact["other_charges"]
        facts[row["name"]] = fact
    for line in lines:
        if line["parent"] in facts:
            header = facts[line["parent"]]
            detail.append(line_fact({key: header[key] for key in (
                "source", "document", "date", "customer", "customer_name", "territory", "status",
                "is_return", "original_invoice",
            )}, line))
    return list(facts.values()), detail


def order_facts(headers, lines, submitted, as_of):
    by_id = {row["name"]: row for row in headers}
    by_order = index_by(lines, "parent")
    groups = defaultdict(list)
    exceptions = []
    for name, row in by_id.items():
        ancestor = name
        visited = {name}
        while by_id[ancestor].get("amended_from"):
            parent = by_id[ancestor]["amended_from"]
            if parent in visited or parent not in by_id:
                ancestor = None
                break
            visited.add(parent)
            ancestor = parent
        if ancestor is None:
            if row["docstatus"] == 1:
                exceptions.append(issue("Sales Order", name, "Order amendment chain cannot be verified."))
            continue
        groups[ancestor].append(row)

    active = {row["name"]: row for row in headers if row["docstatus"] == 1}
    bookings = []
    booking_lines = []
    changes = []
    for root, chain in groups.items():
        valid = [row for row in chain if row["docstatus"] == 1]
        if len(valid) > 1:
            for row in valid:
                active.pop(row["name"], None)
                exceptions.append(issue("Sales Order", row["name"], "Multiple submitted orders in one amendment chain."))
            continue
        latest = valid[0] if valid else max(chain, key=lambda row: (submitted.get(row["name"]) or HISTORY_START, row["name"]))
        commercial = latest.get("sales_order_type") in COMMERCIAL_ORDER_TYPES
        booked = submitted.get(root)
        if valid and (not booked or latest["name"] not in submitted):
            exceptions.append(issue("Sales Order", latest["name"], "ERP submission date could not be verified."))
        if commercial and booked and booked <= as_of:
            base = header_fact(latest, "Sales Order", "transaction_date")
            base.update(date=booked, original_order=root, order_type=latest.get("sales_order_type"))
            if len(chain) > 1 or not valid:
                changes.append(dict(base, revisions=len(chain), order_intake=number(latest["base_net_total"]) if valid else ZERO))
            if valid and latest["name"] in submitted:
                postings = [line_fact(base, row) for row in by_order[latest["name"]]]
                booking_lines.extend(dict(line, order_intake=line["item_net"]) for line in postings)
                bookings.append(dict(base, order_intake=number(latest["base_net_total"])))
    return list(active.values()), bookings, booking_lines, changes, exceptions


def delivery_is_commercial(header, order):
    if header.get("loan_order"):
        return header.get("loan_order_settlement_type") in COMMERCIAL_SETTLEMENTS
    if header.get("object") in NONCOMMERCIAL_PURPOSES:
        return False
    if not header["is_return"] and header.get("object") in RETURN_MOVEMENT_PURPOSES:
        return False
    if header.get("issue"):
        return bool(order and order.get("sales_order_type") in COMMERCIAL_ORDER_TYPES)
    return not order or order.get("sales_order_type") in COMMERCIAL_ORDER_TYPES


def delivery_facts(headers, lines, orders, invoice_headers, invoice_lines):
    by_id = {row["name"]: row for row in headers}
    by_order = {row["name"]: row for row in orders}
    by_invoice = {row["name"]: row for row in invoice_headers if row["update_stock"]}
    result = []
    for row in lines:
        header = by_id.get(row["parent"])
        if not header:
            continue
        order = by_order.get(row.get("against_sales_order"))
        original = by_id.get(header.get("return_against")) if header["is_return"] else None
        detail = line_fact(header_fact(header, "Delivery Note", "posting_date"), row)
        detail.update(
            delivered=detail["item_net"], is_return=bool(header["is_return"]),
            commercial=delivery_is_commercial(original or header, order), original_delivery=header.get("return_against"),
            shipment_purpose=header.get("object"),
            territory=order.get("territory") if order else None,
        )
        result.append(detail)
    for row in invoice_lines:
        header = by_invoice.get(row["parent"])
        if header and not row.get("dn_detail") and not row.get("delivery_note"):
            detail = line_fact(header_fact(header, "Sales Invoice", "posting_date"), row)
            detail.update(delivered=detail["item_net"], is_return=bool(header["is_return"]), commercial=True)
            result.append(detail)
    return result


def convertible_quantity(source, target):
    if source["uom"] == target["uom"]:
        return number(source["qty"])
    factor = number(target.get("conversion_factor"))
    if factor > 0 and source.get("stock_uom") and source["stock_uom"] == target["stock_uom"]:
        return number(source["stock_qty"]) / factor
    return None


def consistent_link(source, target, header):
    return bool(target and source["item_code"] == target["item_code"] and (not header or target["parent"] == header))


def reinvoiced_quantity(events):
    """Identify quantities re-invoiced on the same shipment after an exact linked credit."""
    posted = defaultdict(lambda: ZERO)
    pending = ZERO
    repeated = ZERO
    for invoice, qty in sorted(events, key=lambda event: (
        event[0]["posting_date"], str(event[0].get("creation") or ""), event[0]["name"],
    )):
        if invoice["is_return"]:
            original = invoice.get("return_against")
            reversed_qty = min(max(ZERO, -qty), posted[original])
            posted[original] -= reversed_qty
            if not invoice["update_billed_amount_in_sales_order"]:
                pending += reversed_qty
        elif qty > 0:
            posted[invoice["name"]] += qty
            overlap = min(qty, pending)
            pending -= overlap
            repeated += overlap
    return repeated


def match_billing(orders, deliveries, invoices, bill_items):
    order_lines = {line["name"]: line for line in orders}
    delivery_lines = {line["name"]: line for line in deliveries}
    orders_by_parent = index_by(orders, "parent")
    deliveries_by_parent = index_by(deliveries, "parent")
    invoice_headers = {row["name"]: row for row in invoices}
    order_qty = defaultdict(lambda: ZERO)
    order_actual = defaultdict(lambda: ZERO)
    delivery_qty = defaultdict(lambda: ZERO)
    exceptions = []
    blocked_orders = set()
    blocked_deliveries = set()
    shipment_billing = defaultdict(list)
    for row in bill_items:
        header = invoice_headers[row["parent"]]
        order = order_lines.get(row.get("so_detail"))
        delivery = delivery_lines.get(row.get("dn_detail"))
        via_delivery = order_lines.get(delivery.get("so_detail")) if delivery else None
        conflict = (
            (order and not consistent_link(row, order, row.get("sales_order")))
            or (delivery and not consistent_link(row, delivery, row.get("delivery_note")))
            or (via_delivery and row.get("so_detail") and row["so_detail"] != via_delivery["name"])
            or (via_delivery and row.get("sales_order") and row["sales_order"] != via_delivery["parent"])
        )
        if conflict:
            blocked_orders.update(line["name"] for line in (order, via_delivery) if line)
            if delivery:
                blocked_deliveries.add(delivery["name"])
            exceptions.append(issue("Sales Invoice", header["name"], "Conflicting invoice line references.", row["item_code"]))
            continue
        order = order or via_delivery
        if not delivery and (row.get("dn_detail") or row.get("delivery_note")):
            blocked_deliveries.update(line["name"] for line in deliveries_by_parent[row.get("delivery_note")]
                                      if line["item_code"] == row["item_code"])
            exceptions.append(issue("Sales Invoice", header["name"], "Invoice shipment line could not be linked.", row["item_code"]))
        if delivery:
            qty = convertible_quantity(row, delivery)
            if qty is not None and (qty or not number(row["base_net_amount"])):
                delivery_qty[delivery["name"]] += qty
            else:
                blocked_deliveries.add(delivery["name"])
                exceptions.append(issue("Sales Invoice", header["name"], "Shipment billing has an amount or unit that requires review.", row["item_code"]))
        if order:
            order_actual[order["name"]] += number(row["base_net_amount"])
            qty = convertible_quantity(row, order)
            if delivery and via_delivery and qty:
                shipment_billing[(order["name"], delivery["name"])].append((header, qty))
            if not header["is_return"] or header["update_billed_amount_in_sales_order"]:
                if qty is not None and (qty or not number(row["base_net_amount"])):
                    order_qty[order["name"]] += qty
                else:
                    blocked_orders.add(order["name"])
                    exceptions.append(issue("Sales Invoice", header["name"], "Amount-only billing or incompatible units.", row["item_code"]))
        elif row.get("so_detail") or row.get("sales_order"):
            exceptions.append(issue("Sales Invoice", header["name"], "Invoice order line could not be linked.", row["item_code"]))
            # A header-only invoice could apply to any of its matching order lines.
            blocked_orders.update(line["name"] for line in orders_by_parent[row.get("sales_order")]
                                  if line["item_code"] == row["item_code"])
    for (order_name, _), events in shipment_billing.items():
        order_qty[order_name] -= reinvoiced_quantity(events)
    return order_qty, order_actual, delivery_qty, blocked_orders, blocked_deliveries, exceptions


def open_commitments(headers, lines, packed, stock, linked_delivery_ids, billing, as_of, billing_available=True):
    by_order = {row["name"]: row for row in headers}
    bundle_lines = {row["parent_detail_docname"] for row in packed}
    order_qty, order_actual, _, blocked_orders, _, _ = billing
    result = []
    exceptions = []
    for line in lines:
        header = by_order.get(line["parent"])
        if not header or header["status"] in CLOSED_ORDER_STATUSES:
            continue
        if header.get("sales_order_type") not in COMMERCIAL_ORDER_TYPES:
            exceptions.append(issue("Sales Order", header["name"], "Order type is outside commercial commitments.", line["item_code"]))
            continue
        fact = line_fact(header_fact(header, "Sales Order", "transaction_date"), line)
        fact.update(
            order_type=header["sales_order_type"], ordered_qty=fact["qty"],
            delivered_qty=number(line["delivered_qty"]), returned_qty=number(line["returned_qty"]),
            is_on_hold=header["status"] == "On Hold", billed_qty=order_qty[line["name"]],
            billed_actual=order_actual[line["name"]],
        )
        fact["unit_price"] = fact["item_net"] / fact["qty"] if fact["qty"] else None
        qty = max(ZERO, fact["qty"] - fact["delivered_qty"])
        billable = max(ZERO, fact["qty"] - fact["billed_qty"])
        if qty < QUANTITY_TOLERANCE:
            qty = ZERO
        if billable < QUANTITY_TOLERANCE:
            billable = ZERO

        shipped_item = stock.get(line["item_code"]) or line["name"] in bundle_lines or (
            line["name"] in linked_delivery_ids or bool(line["delivered_by_supplier"])
        )
        if qty and not shipped_item and line["item_code"] not in stock:
            exceptions.append(issue("Sales Order", header["name"], "Shipping item classification is unavailable.", line["item_code"]))
        fact["shipping_qty"] = qty if shipped_item else ZERO
        fact["undelivered"] = fact["shipping_qty"] * (fact["unit_price"] or ZERO)
        fact["shipping_date"] = day(line["delivery_date"])
        fact["overdue"] = bool(fact["shipping_date"] and fact["shipping_date"] < as_of and fact["shipping_qty"])
        fact["shipping_month"] = max(month_start(as_of), month_start(fact["shipping_date"])) if fact["shipping_date"] else None
        if fact["shipping_qty"] and not fact["shipping_date"]:
            exceptions.append(issue("Sales Order", header["name"], "A shipping commitment has no ERP shipping date.", line["item_code"]))
        amount_driven = bool(number(line.get("amount_to_bill_now")) or line.get("total_independent_price") or line.get("variable_price"))
        missing_qty = not fact["qty"] and bool(fact["item_net"])
        if billing_available and (amount_driven or missing_qty):
            exceptions.append(issue("Sales Order", header["name"], "Amount-driven billing requires review.", line["item_code"]))
        if fact["delivered_qty"] - fact["qty"] > QUANTITY_TOLERANCE or fact["billed_qty"] - fact["qty"] > QUANTITY_TOLERANCE:
            exceptions.append(issue("Sales Order", header["name"], "Delivered or billed quantity exceeds the order quantity.", line["item_code"]))
        fact["unbilled_qty"] = None if line["name"] in blocked_orders or missing_qty or amount_driven else billable
        fact["unbilled"] = None if fact["unbilled_qty"] is None else fact["unbilled_qty"] * (fact["unit_price"] or ZERO)
        fact["billing_variance"] = fact["billed_actual"] - fact["billed_qty"] * (fact["unit_price"] or ZERO)
        amount_balance = number(line.get("amount")) - number(line.get("billed_amt"))
        if billing_available and fact["qty"] > 0 and fact["unbilled_qty"] == 0 and amount_balance > number(".01"):
            exceptions.append(dict(
                issue("Sales Order", header["name"], "ERP shows an amount balance although the full order quantity was invoiced.", line["item_code"]),
                erp_order_balance=amount_balance, original_currency=header.get("currency"),
            ))
        if fact["shipping_qty"] or fact["unbilled"] or fact["unbilled_qty"] or fact["unbilled"] is None:
            result.append(fact)
    return result, exceptions


def delivered_unbilled(delivery_details, invoice_lines, billing, orders, active, commercial_facts):
    order_qty, _, delivery_qty, blocked_orders, blocked_deliveries, _ = billing
    line_ids = {row["name"]: row for row in orders}
    active_ids = {row["name"] for row in active if row["status"] not in CLOSED_ORDER_STATUSES}
    matched = {row["line"]: row for row in commercial_facts if row["source"] == "Delivery Note" and row["commercial"]}
    invoice_rows = {row["name"]: row for row in invoice_lines}
    direct_order_billing = {row["so_detail"] for row in invoice_lines if row.get("so_detail") and not row.get("dn_detail")}
    original_lines = defaultdict(list)
    returned_quantities = defaultdict(lambda: ZERO)
    uncertain_returns = set()
    exceptions = []
    for line in delivery_details:
        fact = matched.get(line["name"])
        if fact and not fact["is_return"]:
            original_lines[(line["parent"], line["item_code"])].append(line)
    for line in delivery_details:
        fact = matched.get(line["name"])
        if not fact or not fact["is_return"] or not line.get("return_against"):
            continue
        key = (line["return_against"], line["item_code"])
        originals = original_lines[key]
        quantity = convertible_quantity(line, originals[0]) if len(originals) == 1 else None
        if quantity is None:
            uncertain_returns.add(key)
        else:
            returned_quantities[originals[0]["name"]] += quantity
    result = []
    for line in delivery_details:
        fact = matched.get(line["name"])
        if not fact or fact["is_return"] or fact["status"] in {"Closed", "Completed"} or line["name"] in blocked_deliveries:
            continue
        order = line_ids.get(line.get("so_detail"))
        if order and order["parent"] not in active_ids:
            continue
        if line.get("si_detail") and consistent_link(line, invoice_rows.get(line["si_detail"]), line.get("against_sales_invoice")):
            continue
        remainder = number(line["qty"]) + returned_quantities[line["name"]] - delivery_qty[line["name"]]
        if remainder <= QUANTITY_TOLERANCE:
            continue
        if line.get("so_detail") in direct_order_billing:
            if order and order["name"] not in blocked_orders and order_qty[order["name"]] >= number(order["qty"]) - QUANTITY_TOLERANCE:
                continue
            exceptions.append(issue("Delivery Note", line["parent"], "Direct order billing cannot be allocated to this shipment.", line["item_code"]))
            continue
        if (line["parent"], line["item_code"]) in uncertain_returns or line.get("si_detail"):
            exceptions.append(issue("Delivery Note", line["parent"], "Shipment billing or return allocation requires review.", line["item_code"]))
            continue
        if order:
            quantity = convertible_quantity(dict(line, qty=remainder, stock_qty=remainder * number(line["conversion_factor"])), order)
            if quantity is None or not number(order["qty"]):
                exceptions.append(issue("Delivery Note", line["parent"], "Shipment and order quantities cannot be matched.", line["item_code"]))
                continue
            amount = quantity * number(order["base_net_amount"]) / number(order["qty"])
        else:
            quantity = remainder
            amount = remainder * number(line["base_net_amount"]) / number(line["qty"])
        result.append(dict(fact, unbilled_qty=remainder, delivered_unbilled=amount, direct_delivery=not bool(order)))
    return result, exceptions
