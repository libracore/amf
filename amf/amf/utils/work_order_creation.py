from __future__ import unicode_literals
from amf.amf.utils.stock_summary import get_stock
from amf.amf.utils.utilities import *
import frappe
import json
import frappe.utils
from frappe import _
from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs
from frappe.utils.data import flt


@frappe.whitelist()
def make_work_orders(items, sales_order, company, project=None):
    '''Make Work Orders against the given Sales Order for the given `items`'''
    items = json.loads(items).get('items')
    out = []

    for i in items:
        if not i.get("bom"):
            frappe.throw(_("Please select BOM against item {0}").format(i.get("item_code")))
        if not i.get("pending_qty"):
            frappe.throw(_("Please select Qty against item {0}").format(i.get("item_code")))
        if not i.get("simple_description"):
            i["simple_description"] = ''

        sales_order_item = frappe.get_doc('Sales Order Item', i['sales_order_item'])
        if not sales_order_item.delivery_date:
            frappe.throw(_("Please set delivery date against item {0} in the Sales Order {1}").format(i['item_code'], sales_order))
        delivery_date = sales_order_item.delivery_date

        # Check if the quantity in items is greater than the sales order quantity
        if i['pending_qty'] > sales_order_item.qty:
            remaining_qty = i['pending_qty'] - sales_order_item.qty

            # Create a work order with sales order quantity
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=sales_order_item.qty,
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

            # Create another work order with the remaining quantity
            work_order_remaining = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=remaining_qty,
                company=company,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order_remaining.set_work_order_operations()
            work_order_remaining.save()
            work_order_remaining.submit()
            out.append(work_order_remaining)

        else:
            # If pending_qty is less than or equal to sales order quantity, create a single work order
            work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=i['item_code'],
                bom_no=i.get('bom'),
                qty=i['pending_qty'],
                company=company,
                sales_order=sales_order,
                sales_order_item=i['sales_order_item'],
                project=project,
                fg_warehouse=i['warehouse'],
                description=i['description'],
                destination=i['destination'],
                simple_description=i['simple_description'],
                p_e_d=delivery_date
            )).insert()
            work_order.set_work_order_operations()
            work_order.save()
            work_order.submit()
            out.append(work_order)

    return [p.name for p in out]

@frappe.whitelist()
def check_and_create_work_orders(work_order, method=None):
    work_order_doc = frappe.get_doc('Work Order', work_order.name)
    print(work_order_doc)
    if work_order_doc.sales_order:
        sales_order = work_order_doc.sales_order
    else:
        sales_order = None
    required_qty_dict = {rqd_item.item_code: rqd_item.required_qty for rqd_item in work_order_doc.required_items}
    bom_items = frappe.get_all('BOM Item', filters={'parent': work_order_doc.bom_no}, fields=['item_code', 'qty'])
    missing_items = []

    for item in bom_items:
        print(item)
        stock_qty = get_stock(item['item_code'])
        total_qty = sum(stock['actual_qty'] for stock in stock_qty)
        print(stock_qty, total_qty)
         # Use the required_qty from the required_items
        required_qty = required_qty_dict.get(item['item_code'], 0)
        if total_qty < required_qty*item['qty']:
            qty_rqd = required_qty*item['qty']-total_qty
            if frappe.db.exists('BOM', {'item': item['item_code'], 'is_active': 1, 'is_default': 1}):
                missing_items.append({'item_code': item['item_code'], 'qty': qty_rqd})
    
    print("missing items:", missing_items)
    if missing_items:
        create_work_orders_for_missing_items(missing_items, sales_order)

    return {'missing_items': missing_items}

@frappe.whitelist()
def create_work_orders_for_missing_items(missing_items, sales_order=None):
    work_orders = []
    for item in missing_items:
        item_code = item['item_code']
        qty = item['qty']
        
        bom = frappe.get_value('BOM', {'item': item_code, 'is_active': 1, 'is_default': 1}, 'name')
        
        if bom:
            wo = make_work_order(item_code, sales_order, qty, bom)
            wo.submit()
            work_orders.append(wo.name)
            commit_database()
    print(work_orders)
    return work_orders

def make_work_order(item_code, sales_order=None, qty=1, bom_no=None):
    '''Make a single Work Order for the given item'''
    if not bom_no:
        frappe.throw(_("Please select BOM for item {0}").format(item_code))
    if not qty:
        frappe.throw(_("Please select Qty for item {0}").format(item_code))

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',  # Replace with the appropriate warehouse
        simple_description='Auto-generated Work Order from non-available stock'
    )).insert()
   
    work_order.set_work_order_operations()
    work_order.save()

    return work_order

def check_sub_assembly_items(work_order):
    # List to hold all sub-assembly items
    sub_assembly_items = []

    def get_sub_assemblies(bom_no):
        # Fetch all items in the BOM
        bom_items = frappe.get_all('BOM Item', filters={'parent': bom_no}, fields=['item_code'])

        for item in bom_items:
            # Fetch the item_type from the Item doctype
            item_type = frappe.db.get_value('Item', item['item_code'], 'item_type')
            
            # Check if the item type is 'Sub-Assembly'
            if item_type == 'Sub-Assembly' or item_type == 'Actuator':
                # Append to the list
                sub_assembly_items.append(item['item_code'])
                
                # Fetch the default BOM for this item
                default_bom = frappe.db.get_value('BOM', {'item': item['item_code'], 'is_default': 1, 'is_active': 1}, 'name')
                
                # If there is a default BOM, recurse into it
                if default_bom:
                    get_sub_assemblies(default_bom)

    # Get the BOM linked to the work order
    work_order_doc = frappe.get_doc('Work Order', work_order)
    bom_no = work_order_doc.bom_no
    
    # Start the recursion from the main BOM
    get_sub_assemblies(bom_no)

    # Optional: Return the list of sub-assembly items
    return sub_assembly_items

@frappe.whitelist()
def on_submit_work_order(doc_name, method=None):
    sub_assembly_items = check_sub_assembly_items(doc_name) # PUT doc.name when using hooks.py
    print("Sub-Assembly:", sub_assembly_items)
    return sub_assembly_items

@frappe.whitelist()
def create_work_orders(items, qty, parent_work_order, customer=None):
    # Convert the items string to a list
    if isinstance(items, str):
        items = json.loads(items)
    work_order_links = []
    for item in items:
        work_order = frappe.get_doc(dict(
                doctype='Work Order',
                production_item=item,
                bom_no=frappe.db.get_value('BOM', {'item': item, 'is_default': 1, 'is_active': 1}, 'name'),
                qty=int(qty),
                parent_work_order=parent_work_order,
                custo_name = customer,
            )).insert()
        work_order.set_work_order_operations()
        work_order.save()
        work_order.submit()
        work_order_links.append(work_order.name)
    
    commit_database()
    return work_order_links

def should_generate_work_order_for_item(item_code):
    # Logic to determine if a Work Order should be generated for the item
    # This could involve checking stock levels, existing Work Orders, etc.
    return True  # For simplicity, always return True

def get_default_bom(item_code):
    # Logic to fetch the default BOM for the given item
    bom = frappe.db.get_value('BOM', {'item': item_code, 'is_default': 1}, 'name')
    if not bom:
        frappe.throw(f"No default BOM found for item {item_code}")
    return bom

@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None):
    work_order = frappe.get_doc("Work Order", work_order_id)
    if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group") \
            and not work_order.skip_transfer:
        wip_warehouse = work_order.wip_warehouse
    else:
        wip_warehouse = None

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = purpose
    stock_entry.work_order = work_order_id
    stock_entry.company = work_order.company
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order.bom_no
    stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
    stock_entry.fg_completed_qty = qty or (flt(work_order.qty) - flt(work_order.produced_qty))

    if purpose == "Material Transfer for Manufacture":
        stock_entry.to_warehouse = wip_warehouse
        stock_entry.project = work_order.project
    else:
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = work_order.fg_warehouse
        stock_entry.project = work_order.project
        if purpose == "Manufacture":
            additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
            stock_entry.set("additional_costs", additional_costs)

    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    # Save the Stock Entry
    stock_entry.insert()
    stock_entry.submit()

    # Commit the transaction to ensure the Stock Entry is saved
    frappe.db.commit()

    return stock_entry.as_dict()

