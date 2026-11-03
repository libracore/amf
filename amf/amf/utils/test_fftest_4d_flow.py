"""Exercise the copied FFTest flow without connecting to a site or changing stock.

The in-memory ledger uses the installed ERPNext V12 serial validator, including
its native raw-material/finished-good serial carryover rule. Database writes,
automatic source batches, and the legacy Batch hook commit are simulated.
"""

import copy
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe import ValidationError, _dict
from erpnext.stock.doctype.serial_no import serial_no as serial_module
from erpnext.stock.doctype.stock_entry import stock_entry as stock_entry_module

from amf.www import fftest_master_debug_4d as flow


class Document(_dict):
    def set(self, key, value):
        self[key] = value

    def update(self, *args, **kwargs):
        dict.update(self, *args, **kwargs)
        return self

    def __getattribute__(self, name):
        if dict.__contains__(self, name):
            return dict.__getitem__(self, name)
        return super().__getattribute__(name)

    def __deepcopy__(self, memo):
        result = Document()
        memo[id(self)] = result
        for key, value in dict.items(self):
            result[key] = copy.deepcopy(value, memo)
        return result

    def check_permission(self, *args):
        pass


def row(item, qty=1, bom_no=None):
    return _dict(item_code=item, qty=qty, stock_qty=qty, conversion_factor=1, bom_no=bom_no)


class MemoryDatabase:
    def __init__(self):
        self.docs = {doctype: {} for doctype in ("Item", "BOM", "Work Order", "Serial No", "Batch", "Stock Entry")}
        self.stock = {}
        self.locks = []
        self.commits = 0
        self.rollbacks = 0
        self.entries = []
        self.fail_item = None
        self.sequence = 0
        self.snapshot = None
        self.native_unconsumed = False

    def commit(self):
        self.commits += 1

    def begin_snapshot(self):
        self.snapshot = copy.deepcopy((self.docs, self.stock, self.entries))

    def rollback(self):
        self.rollbacks += 1
        if self.snapshot:
            self.docs, self.stock, self.entries = copy.deepcopy(self.snapshot)

    def exists(self, doctype, filters):
        return bool(self.find(doctype, filters))

    def find(self, doctype, filters):
        if doctype == "Work Order Item":
            docs = [_dict(row, parent=order.name) for order in self.docs["Work Order"].values()
                    for row in order.required_items]
            return [doc for doc in docs if all(doc.get(key) == value for key, value in filters.items())]
        if isinstance(filters, str):
            doc = self.docs[doctype].get(filters)
            return [doc] if doc else []
        return [doc for doc in self.docs[doctype].values() if all(
            doc.get(key) in value[1] if isinstance(value, list) and value[0] == "in"
            else doc.get(key) == value for key, value in filters.items()
        )]

    def get_value(self, doctype, filters, fieldname="name", as_dict=False, **kwargs):
        matches = self.find(doctype, filters)
        if not matches:
            return None
        doc = matches[0]
        if isinstance(fieldname, str):
            return doc.get(fieldname)
        result = _dict((field, doc.get(field)) for field in fieldname)
        return result if as_dict else tuple(result.values())

    def sql(self, query, params=(), as_dict=False):
        if "SELECT DISTINCT woi.item_code" in query:
            return [_dict(item_code=row.item_code)
                    for row in self.docs["Work Order"][params[0]].required_items
                    if self.docs["Item"][row.item_code].has_serial_no]
        if "FOR UPDATE" in query:
            doctype = "Serial No" if "tabSerial No" in query else "Work Order"
            self.locks.append((doctype, params[0]))
            doc = self.docs[doctype].get(params[0])
            return [dict(doc)] if doc and not as_dict else [_dict(doc)] if doc else []
        if "SUM(actual_qty)" in query:
            if "IFNULL(is_cancelled, 'No') = 'No'" not in query:
                raise AssertionError("Expected the V12 cancellation predicate")
            item, batch, warehouse = params
            return [[self.stock.get((item, batch, warehouse), 0)]]
        raise AssertionError(query)

    def get_all(self, doctype, filters=None, fields=None, **kwargs):
        if doctype == "BOM Item":
            docs = self.docs["BOM"][filters["parent"]].items
        else:
            docs = self.find(doctype, filters or {})
        return [_dict((field, doc.get(field)) for field in fields) for doc in docs]

    def get_doc(self, doctype, name):
        if doctype == "Stock Entry":
            return self.docs[doctype][name]
        return Document(self.docs[doctype][name])

    def next_name(self, prefix):
        self.sequence += 1
        return "{}-{}".format(prefix, self.sequence)

    def new_doc(self, doctype):
        if doctype == "Stock Entry":
            return Entry(self)
        if doctype == "Batch":
            doc = Document(doctype=doctype)

            def insert(**kwargs):
                self.docs[doctype][doc.name] = _dict(doc)
                self.commit()  # The real AMF Batch barcode hook commits here.

            doc.insert = insert
            return doc
        if doctype == "Work Order":
            doc = Document(doctype=doctype, status="Not Started", produced_qty=0,
                           material_transferred_for_manufacturing=0, wip_step=0,
                           skip_transfer=0, project=None, parent_work_order="", sales_order="",
                           use_multi_level_bom=1,
                           wip_warehouse="Default WIP", fg_warehouse=flow.MAIN_STOCK_WAREHOUSE)
            doc.meta = SimpleNamespace(has_field=lambda name: True)
            doc.set_default_warehouse = lambda: None
            doc.set_work_order_operations = lambda: None

            def insert():
                doc.name = self.next_name("WO")
                bom = self.docs["BOM"][doc.bom_no]
                doc.required_items = [_dict(
                    component, required_qty=component.stock_qty / bom.quantity * doc.qty,
                    consumed_qty=0, transferred_qty=0,
                ) for component in bom.items]
                self.docs[doctype][doc.name] = Document(doc)

            def save():
                self.docs[doctype][doc.name] = Document(doc)

            def submit():
                doc.docstatus = 1
                save()

            doc.insert, doc.save, doc.submit = insert, save, submit
            return doc
        raise AssertionError(doctype)


class Entry(Document):
    def __init__(self, database):
        super().__init__(name=database.next_name("STE"), items=[])
        object.__setattr__(self, "database", database)

    def set_stock_entry_type(self):
        pass

    def get_items(self):
        bom = self.database.docs["BOM"][self.bom_no]
        self.items = []
        if self.purpose == "Manufacture" and self.database.native_unconsumed:
            # Execute the installed V12 method, including its cumulative-qty bug.
            stock_entry_module.StockEntry.get_unconsumed_raw_materials(self)
        else:
            for component in bom.items:
                quantity = component.stock_qty / bom.quantity * self.fg_completed_qty
                self.items.append(Document(
                    item_code=component.item_code, qty=quantity, transfer_qty=quantity,
                    conversion_factor=1, s_warehouse=self.from_warehouse,
                    t_warehouse=self.to_warehouse if self.purpose != "Manufacture" else None,
                    serial_no=None, batch_no=None,
                    meta=SimpleNamespace(has_field=lambda name: True),
                ))
        if self.purpose == "Manufacture":
            item = self.database.docs["Work Order"][self.work_order].production_item
            self.items.append(Document(item_code=item, qty=self.fg_completed_qty,
                                       transfer_qty=self.fg_completed_qty,
                                       s_warehouse=None, t_warehouse=self.to_warehouse,
                                       serial_no=None, batch_no=None,
                                       meta=SimpleNamespace(has_field=lambda name: True)))

    def add_to_stock_entry_detail(self, items):
        for item, values in items.items():
            self.items.append(Document(
                item_code=item, qty=values["qty"], transfer_qty=values["qty"],
                conversion_factor=1, s_warehouse=values["from_warehouse"],
                t_warehouse=values["to_warehouse"] or None,
                serial_no=None, batch_no=None,
                meta=SimpleNamespace(has_field=lambda name: True),
            ))

    def save(self):
        for component in self.items:
            item = self.database.docs["Item"][component.item_code]
            if component.s_warehouse and item.has_batch_no and not component.batch_no:
                matches = [batch for batch in self.database.docs["Batch"].values()
                           if batch.item == item.name and not batch.disabled and self.database.stock.get(
                               (item.name, batch.name, component.s_warehouse), 0) >= component.transfer_qty]
                if matches:
                    component.batch_no = matches[0].name
        self.database.docs["Stock Entry"][self.name] = self
        return self

    def submit(self):
        database = self.database
        if self.purpose == "Manufacture" and database.docs["Work Order"][self.work_order].production_item == database.fail_item:
            raise ValidationError("Simulated final-stage submit failure")
        for direction in ("s_warehouse", "t_warehouse"):
            for component in self.items:
                warehouse = component.get(direction)
                if not warehouse:
                    continue
                quantity = component.transfer_qty * (-1 if direction == "s_warehouse" else 1)
                sle = _dict(item_code=component.item_code, serial_no=component.serial_no,
                            actual_qty=quantity, warehouse=warehouse, batch_no=component.batch_no,
                            is_cancelled="No", voucher_type="Stock Entry", voucher_no=self.name,
                            company=self.company)
                item = database.docs["Item"][component.item_code]
                serial_module.validate_serial_no(sle, item)
                key = (component.item_code, component.batch_no, warehouse)
                database.stock[key] = database.stock.get(key, 0) + quantity
                if database.stock[key] < 0:
                    raise ValidationError("Insufficient stock")
                if component.serial_no:
                    serial = database.docs["Serial No"].setdefault(component.serial_no,
                        Document(name=component.serial_no, serial_no=component.serial_no))
                    serial.update(item_code=component.item_code, warehouse=warehouse if quantity > 0 else None,
                                  batch_no=component.batch_no, company=self.company)
                    if quantity > 0:
                        serial.update(purchase_document_no=self.name, delivery_document_no=None,
                                      delivery_document_type=None)
                    else:
                        serial.update(delivery_document_no=self.name, delivery_document_type="Stock Entry")
        self.docstatus = 1
        work_order = database.docs["Work Order"][self.work_order]
        if self.purpose == "Manufacture":
            work_order.produced_qty += self.fg_completed_qty
        else:
            work_order.material_transferred_for_manufacturing += self.fg_completed_qty
        for component in self.items:
            if component.s_warehouse:
                field = "consumed_qty" if self.purpose == "Manufacture" else "transferred_qty"
                for requirement in work_order.required_items:
                    if requirement.item_code == component.item_code:
                        requirement[field] += component.transfer_qty
        database.entries.append(self)
        return self


class TestFFTest4DFlow(unittest.TestCase):
    def setUp(self):
        self.database = MemoryDatabase()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in {
            "db": self.database, "get_doc": self.database.get_doc,
            "get_all": self.database.get_all, "new_doc": self.database.new_doc,
            "has_permission": lambda *args: True,
            "log_error": Mock(), "get_traceback": lambda: "test traceback",
            "session": _dict(user="test@example.com"),
            "throw": self.throw,
        }.items():
            self.stack.enter_context(patch.object(frappe, name, value, create=True))
        self.stack.enter_context(patch.object(flow, "_", lambda message: message))
        self.stack.enter_context(patch.object(serial_module, "_", lambda message: message))
        self.stack.enter_context(patch.object(flow, "_ExecutionLog", lambda *args: SimpleNamespace(
            name="LOG-TEST", add=lambda *args: None, flush=lambda: None)))
        self.stack.enter_context(patch.object(flow, "create_batch_name", lambda *args: self.database.next_name("BATCH")))
        self.stack.enter_context(patch.object(flow, "get_default_bom", self.default_bom))
        self.stack.enter_context(patch.object(stock_entry_module, "get_item_defaults", lambda *args: _dict(
            stock_uom="Nos", expense_account="Test expense", buying_cost_center="Test cost center")))
        for code, serial, batch in (("4D00AB", 0, 0), ("5D10AB", 1, 1), ("5D00AB", 1, 1), ("MAT", 0, 1)):
            self.database.docs["Item"][code] = _dict(
                name=code, has_serial_no=serial, has_batch_no=batch,
                is_stock_item=1, serial_no_series=None,
            )
        for code, components, quantity in (
            ("4D00AB", [row("5D10AB", bom_no="BOM-5D10AB")], 1),
            ("5D10AB", [row("5D00AB", bom_no="BOM-5D00AB")], 1),
            ("5D00AB", [row("MAT", qty=20)], 10),
        ):
            self.database.docs["BOM"]["BOM-" + code] = Document(
                name="BOM-" + code, item=code, company=flow.COMPANY,
                quantity=quantity, items=components, docstatus=1, is_active=1,
            )
            self.database.docs["Work Order"]["WO-" + code] = Document(
                name="WO-" + code, production_item=code, bom_no="BOM-" + code,
                company=flow.COMPANY, docstatus=1, status="Not Started", qty=4,
                produced_qty=0, material_transferred_for_manufacturing=0,
                sales_order="SO-TEST", project=None,
                parent_work_order="WO-4D00AB" if code == "5D10AB" else "WO-5D10AB" if code == "5D00AB" else "",
                wip_step=1 if code.startswith("4D") else 0, skip_transfer=0,
                use_multi_level_bom=0, required_items=[_dict(
                    component, required_qty=component.stock_qty / quantity * 4,
                    consumed_qty=0, transferred_qty=0,
                ) for component in components],
                wip_warehouse="Custom WIP " + code, fg_warehouse=flow.MAIN_STOCK_WAREHOUSE,
            )
        self.database.docs["Batch"]["MAT-BATCH"] = _dict(name="MAT-BATCH", item="MAT", disabled=0)
        self.database.stock[("MAT", "MAT-BATCH", flow.MAIN_STOCK_WAREHOUSE)] = 100
        self.database.begin_snapshot()

    @staticmethod
    def throw(message, exc=ValidationError, **kwargs):
        raise exc(message)

    def default_bom(self, item):
        name = "BOM-" + item
        if name not in self.database.docs["BOM"]:
            raise ValidationError("No manufacturing BOM for " + item)
        return name

    def execute(self, serial="HAND-0070", batches=None):
        return flow.make_stock_entry("WO-4D00AB", serial, batches)

    def seed_serial(self, item, warehouse=None, transferred_for=None):
        warehouse = warehouse or flow.MAIN_STOCK_WAREHOUSE
        batch = "EXISTING-BATCH" if self.database.docs["Item"][item].has_batch_no else None
        if batch:
            self.database.docs["Batch"][batch] = _dict(name=batch, item=item, disabled=0)
        self.database.docs["Serial No"]["HAND-0070"] = Document(
            name="HAND-0070", serial_no="HAND-0070", item_code=item, warehouse=warehouse,
            batch_no=batch, purchase_document_no="EXISTING-TRANSFER", company=flow.COMPANY,
        )
        self.database.stock[(item, batch, warehouse)] = 1
        if transferred_for:
            self.database.docs["Stock Entry"]["EXISTING-TRANSFER"] = Document(
                name="EXISTING-TRANSFER", work_order=transferred_for, company=flow.COMPANY,
                purpose="Material Transfer for Manufacture", docstatus=1,
            )
            self.database.docs["Work Order"][transferred_for].material_transferred_for_manufacturing = 1
        self.database.begin_snapshot()

    def use_purchased_5d0000(self, seed_serial=True):
        """Match purchased 5D0000 -> serialized, non-batched 5D1000 -> 4D."""
        raw = self.database.docs["Item"].pop("5D00AB")
        raw.name = "5D0000"
        self.database.docs["Item"][raw.name] = raw
        body = self.database.docs["Item"].pop("5D10AB")
        body.name = "5D1000"
        body.has_batch_no = 0
        self.database.docs["Item"][body.name] = body
        self.database.docs["BOM"]["BOM-4D00AB"].items[0].item_code = body.name
        self.database.docs["Work Order"]["WO-4D00AB"].required_items[0].item_code = body.name
        body_bom = self.database.docs["BOM"]["BOM-5D10AB"]
        body_bom.item = body.name
        body_bom.items[0].item_code = raw.name
        self.database.docs["Work Order"]["WO-5D10AB"].required_items[0].item_code = raw.name
        body_bom.items[0].bom_no = None
        self.database.docs["Work Order"]["WO-5D10AB"].production_item = body.name
        del self.database.docs["BOM"]["BOM-5D00AB"]
        del self.database.docs["Work Order"]["WO-5D00AB"]
        if seed_serial:
            self.seed_serial(raw.name)
        else:
            self.database.begin_snapshot()

    def test_manufactures_all_three_layers_with_native_same_serial_and_normalized_qty(self):
        result = self.execute(" hand-0070 ")
        self.assertNotIn("error", result)
        manufactured = [entry for entry in self.database.entries if entry.purpose == "Manufacture"]
        self.assertEqual([self.database.docs["Work Order"][entry.work_order].production_item for entry in manufactured],
                         ["5D00AB", "5D10AB", "4D00AB"])
        self.assertEqual([entry.items[-1].get("serial_no") for entry in manufactured], ["HAND-0070", "HAND-0070", None])
        self.assertEqual(result.items[-1].product_serial_no, "HAND-0070")
        self.assertEqual(manufactured[0].items[0].qty, 2)
        self.assertEqual(self.database.stock[("MAT", "MAT-BATCH", flow.MAIN_STOCK_WAREHOUSE)], 98)
        self.assertEqual(self.database.docs["Serial No"]["HAND-0070"].item_code, "5D10AB")
        self.assertIsNone(self.database.docs["Serial No"]["HAND-0070"].warehouse)
        self.assertEqual(self.database.commits, 0)
        self.assertIn(("Serial No", "HAND-0070"), self.database.locks)
        self.assertIn(("Work Order", "WO-4D00AB"), self.database.locks)

    def test_existing_raw_serial_resumes_at_5d1_without_a_raw_bom(self):
        self.seed_serial("5D00AB")
        del self.database.docs["BOM"]["BOM-5D00AB"]
        result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual(len([entry for entry in self.database.entries if entry.purpose == "Manufacture"]), 2)

    def test_existing_body_serial_only_manufactures_final_product(self):
        self.seed_serial("5D10AB")
        result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual(len(self.database.entries), 1)
        self.assertEqual(result.work_order, "WO-4D00AB")

    def test_raw_serial_in_custom_wip_uses_owning_body_order(self):
        self.seed_serial("5D00AB", "Custom WIP 5D10AB", "WO-5D10AB")
        result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual([entry.purpose for entry in self.database.entries], ["Manufacture", "Manufacture"])

    def test_body_serial_in_final_orders_custom_wip_is_consumed_without_transfer(self):
        root = self.database.docs["Work Order"]["WO-4D00AB"]
        root.wip_step = 0
        self.seed_serial("5D10AB", root.wip_warehouse, root.name)
        self.assertNotIn("error", self.execute())
        self.assertEqual(len(self.database.entries), 1)

    def test_orphan_wip_serial_is_rejected(self):
        self.seed_serial("5D00AB", "Custom WIP 5D10AB")
        result = self.execute()
        self.assertIn("error", result)
        self.assertEqual(self.database.entries, [])

    def test_final_failure_rolls_back_earlier_manufacture_batches_and_serial(self):
        self.database.fail_item = "4D00AB"
        result = self.execute()
        self.assertIn("Simulated final-stage", result["error"])
        self.assertEqual(self.database.entries, [])
        self.assertNotIn("HAND-0070", self.database.docs["Serial No"])
        self.assertEqual(set(self.database.docs["Batch"]), {"MAT-BATCH"})
        self.assertEqual(self.database.commits, 0)
        self.assertEqual(self.database.rollbacks, 1)
        self.database.commit()
        self.assertEqual(self.database.commits, 1)

    def test_preview_matches_execution_stages_and_has_no_writes(self):
        report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(self.database.entries, [])
        self.assertEqual(set(self.database.docs["Batch"]), {"MAT-BATCH"})
        expected = [(entry["purpose"], entry["work_order"]) for entry in report["planned_documents"]]
        self.assertNotIn("error", self.execute())
        self.assertEqual(expected, [(entry.purpose, entry.work_order) for entry in self.database.entries])

    def test_direct_main_stock_preview_and_execution_skip_transfers(self):
        for work_order in self.database.docs["Work Order"].values():
            work_order.wip_step = 1
        report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual([doc["purpose"] for doc in report["planned_documents"]], ["Manufacture"] * 3)
        self.assertNotIn("error", self.execute())
        self.assertEqual([entry.purpose for entry in self.database.entries], ["Manufacture"] * 3)

    def test_requested_serial_conflicting_batch_is_rejected(self):
        self.seed_serial("5D00AB")
        self.database.docs["Batch"]["WRONG"] = _dict(name="WRONG", item="5D00AB", disabled=0)
        self.database.stock[("5D00AB", "WRONG", flow.MAIN_STOCK_WAREHOUSE)] = 10
        result = self.execute(batches=[{"batch_no": "WRONG"}])
        self.assertIn("Serial selection requires Batch", result["error"])

    def test_batch_inputs_are_routed_to_the_raw_manufacturing_stage(self):
        result = self.execute(batches=[{"batch_no": "MAT-BATCH"}])
        self.assertNotIn("error", result)
        self.assertEqual(self.database.entries[0].items[0].batch_no, "MAT-BATCH")

    def test_missing_raw_manufacturing_bom_is_reported_without_receiving_stock(self):
        del self.database.docs["BOM"]["BOM-5D00AB"]
        self.database.begin_snapshot()
        result = self.execute()
        self.assertIn("error", result)
        self.assertEqual(self.database.entries, [])
        self.assertEqual(self.database.docs["Serial No"], {})

    def test_missing_component_work_orders_are_created_with_selected_boms_and_parents(self):
        del self.database.docs["Work Order"]["WO-5D10AB"]
        del self.database.docs["Work Order"]["WO-5D00AB"]
        self.assertNotIn("error", self.execute())
        body = next(doc for doc in self.database.docs["Work Order"].values() if doc.production_item == "5D10AB")
        raw = next(doc for doc in self.database.docs["Work Order"].values() if doc.production_item == "5D00AB")
        self.assertEqual(body.parent_work_order, "WO-4D00AB")
        self.assertEqual(raw.parent_work_order, body.name)
        self.assertEqual(raw.bom_no, "BOM-5D00AB")
        self.assertEqual((raw.use_multi_level_bom, body.use_multi_level_bom), (0, 0))

    def test_serialized_final_product_can_carry_the_same_serial_again(self):
        self.database.docs["Item"]["4D00AB"].has_serial_no = 1
        self.assertNotIn("error", self.execute())
        serial = self.database.docs["Serial No"]["HAND-0070"]
        self.assertEqual((serial.item_code, serial.warehouse), ("4D00AB", flow.MAIN_STOCK_WAREHOUSE))

    def test_multiple_serials_and_already_consumed_serial_are_rejected(self):
        self.assertIn("error", self.execute("A,B"))
        self.seed_serial("5D10AB")
        self.database.docs["Serial No"]["HAND-0070"].warehouse = None
        self.assertIn("error", self.execute())

    def test_unrelated_sales_orders_component_work_order_is_not_reused(self):
        body = self.database.docs["Work Order"]["WO-5D10AB"]
        body.parent_work_order = ""
        body.sales_order = "SO-OTHER"
        result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual(body.produced_qty, 0)
        manufactured = [entry for entry in self.database.entries if entry.purpose == "Manufacture"]
        self.assertNotEqual(manufactured[1].work_order, body.name)

    def test_linked_boms_are_used_instead_of_reselecting_defaults(self):
        with patch.object(flow, "get_default_bom", side_effect=AssertionError("Must use linked BOM")):
            self.assertNotIn("error", self.execute())

    def test_preview_includes_all_three_layers_when_component_orders_will_be_created(self):
        del self.database.docs["Work Order"]["WO-5D10AB"]
        del self.database.docs["Work Order"]["WO-5D00AB"]
        report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
        self.assertTrue(report["ok"], report["errors"])
        manufacture = [doc for doc in report["planned_documents"] if doc["purpose"] == "Manufacture"]
        self.assertEqual([doc["produce_item"] for doc in manufacture], ["5D00AB", "5D10AB", "4D00AB"])
        self.assertEqual(len(self.database.docs["Work Order"]), 1)
        self.assertEqual(self.database.entries, [])

    def test_fractional_serialized_component_demand_is_rejected_before_stock_changes(self):
        self.database.docs["BOM"]["BOM-5D10AB"].items[0].stock_qty = 0.5
        self.assertIn("one stock unit", self.execute()["error"])
        self.assertEqual(self.database.entries, [])

    def test_final_serial_allocated_to_another_work_order_is_rejected(self):
        root = self.database.docs["Work Order"]["WO-4D00AB"]
        root.wip_step = 0
        other = Document(root)
        other.name = "WO-OTHER"
        self.database.docs["Work Order"][other.name] = other
        self.seed_serial("5D10AB", root.wip_warehouse, other.name)
        self.assertIn("not WO-4D00AB", self.execute()["error"])
        self.assertEqual(self.database.entries, [])

    def test_preview_checks_full_batch_requirement_and_execution_rolls_back_shortage(self):
        self.database.stock[("MAT", "MAT-BATCH", flow.MAIN_STOCK_WAREHOUSE)] = 1
        self.database.begin_snapshot()
        report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070", [{"batch_no": "MAT-BATCH"}])
        self.assertFalse(report["ok"])
        self.assertIn("2.0 is required", report["errors"][0])
        self.assertIn("error", self.execute(batches=[{"batch_no": "MAT-BATCH"}]))
        self.assertEqual(self.database.entries, [])

    def test_commit_method_is_restored_after_success(self):
        self.assertNotIn("error", self.execute())
        self.database.commit()
        self.assertEqual(self.database.commits, 1)

    def test_non_4d_products_keep_the_legacy_two_manufacturing_stages(self):
        root = self.database.docs["Work Order"]["WO-4D00AB"]
        body = self.database.docs["Work Order"]["WO-5D10AB"]
        root.production_item = "420100"
        body.production_item = "520100"
        self.database.docs["Item"]["420100"] = _dict(self.database.docs["Item"]["4D00AB"], name="420100")
        self.database.docs["Item"]["520100"] = _dict(self.database.docs["Item"]["5D10AB"], name="520100")
        self.database.docs["BOM"][root.bom_no].items = [row("520100")]
        self.database.docs["BOM"][body.bom_no].items = [row("MAT")]
        root.required_items = [_dict(row("520100"), required_qty=4, consumed_qty=0, transferred_qty=0)]
        body.required_items = [_dict(row("MAT"), required_qty=4, consumed_qty=0, transferred_qty=0)]
        with patch.object(flow, "_work_order_uses_p202_body", return_value=False), patch.object(
            flow, "_find_serialized_work_orders", return_value=[{
                "work_order_name": body.name, "production_item": body.production_item}]
        ), patch.object(flow, "_execute_4d_stock_entry_flow") as four_d:
            result = self.execute()
        self.assertNotIn("error", result)
        four_d.assert_not_called()
        manufactured = [entry for entry in self.database.entries if entry.purpose == "Manufacture"]
        self.assertEqual(len(manufactured), 2)

    def test_exploded_root_work_order_is_rejected_before_manufacturing_components(self):
        self.database.docs["Work Order"]["WO-4D00AB"].required_items = [row("MAT")]
        self.assertIn("single-level BOM", self.execute()["error"])
        self.assertEqual(self.database.entries, [])

    def test_spare_final_batch_is_validated_and_used_by_preview_and_execution(self):
        root = self.database.docs["Work Order"]["WO-4D00AB"]
        root.spare_part_production = 1
        root.spare_batch_no = "FINAL-BATCH"
        self.database.docs["Item"][root.production_item].has_batch_no = 1
        self.database.docs["Batch"]["FINAL-BATCH"] = _dict(
            name="FINAL-BATCH", item=root.production_item, disabled=0)
        report = flow.debug_stock_entry_flow(root.name, "HAND-0070")
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["planned_documents"][-1]["output_batch_no"], "FINAL-BATCH")
        result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual(result.items[-1].batch_no, "FINAL-BATCH")

    def test_disabled_source_serial_batch_is_rejected_by_preview(self):
        self.seed_serial("5D10AB")
        self.database.docs["Batch"]["EXISTING-BATCH"].disabled = 1
        report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
        self.assertFalse(report["ok"])
        self.assertIn("invalid Batch", report["errors"][0])

    def test_purchased_5d0000_preview_needs_no_raw_bom_or_work_order(self):
        self.use_purchased_5d0000()
        before = copy.deepcopy(self.database.docs)
        with patch.object(flow, "get_default_bom", side_effect=AssertionError("No raw BOM lookup")):
            report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
        self.assertTrue(report["ok"], report["errors"])
        manufactured = [doc for doc in report["planned_documents"] if doc["purpose"] == "Manufacture"]
        self.assertEqual([doc["produce_item"] for doc in manufactured], ["5D1000", "4D00AB"])
        self.assertEqual(manufactured[0]["consume_item"], "5D0000")
        self.assertEqual(manufactured[0]["consume_serial"], "HAND-0070")
        self.assertEqual(before, self.database.docs)
        self.assertEqual(self.database.entries, [])

    def test_purchased_5d0000_is_consumed_without_manufacturing_or_creating_an_order_for_it(self):
        self.use_purchased_5d0000()
        with patch.object(flow, "get_default_bom", side_effect=AssertionError("No raw BOM lookup")), patch.object(
            flow, "create_new_wo", side_effect=AssertionError("No new Work Orders needed")
        ):
            result = self.execute()
        self.assertNotIn("error", result)
        manufactured = [entry for entry in self.database.entries if entry.purpose == "Manufacture"]
        self.assertEqual([self.database.docs["Work Order"][entry.work_order].production_item for entry in manufactured],
                         ["5D1000", "4D00AB"])
        self.assertEqual(manufactured[0].items[0].serial_no, "HAND-0070")
        self.assertEqual(manufactured[0].items[0].batch_no, "EXISTING-BATCH")
        self.assertEqual(manufactured[0].items[-1].serial_no, "HAND-0070")
        self.assertEqual(self.database.stock[("5D0000", "EXISTING-BATCH", flow.MAIN_STOCK_WAREHOUSE)], 0)
        self.assertEqual(set(self.database.docs["Work Order"]), {"WO-4D00AB", "WO-5D10AB"})

    def test_missing_purchased_serial_is_a_stock_validation_error_in_preview_and_execution(self):
        self.use_purchased_5d0000(seed_serial=False)
        with patch.object(flow, "get_default_bom", side_effect=AssertionError("No raw BOM lookup")), patch.object(
            flow, "create_new_wo", side_effect=AssertionError("No Work Orders may be created")
        ):
            report = flow.debug_stock_entry_flow("WO-4D00AB", "HAND-0070")
            result = self.execute()
        self.assertFalse(report["ok"])
        self.assertIn("must already exist for purchased Item 5D0000", report["errors"][0])
        self.assertIn("Main Stock - AMF21", result["error"])
        self.assertEqual(self.database.entries, [])
        self.assertEqual(self.database.docs["Serial No"], {})

    def test_only_body_work_order_is_created_for_purchased_5d0000(self):
        self.use_purchased_5d0000()
        del self.database.docs["Work Order"]["WO-5D10AB"]
        with patch.object(flow, "create_new_wo", wraps=flow.create_new_wo) as create:
            result = self.execute()
        self.assertNotIn("error", result)
        self.assertEqual([call.kwargs["item_code"] for call in create.call_args_list], ["5D1000"])

    def test_received_5d0000_in_custom_wip_resumes_its_body_order(self):
        self.use_purchased_5d0000(seed_serial=False)
        self.seed_serial("5D0000", "Custom WIP 5D10AB", "WO-5D10AB")
        self.assertNotIn("error", self.execute())
        self.assertEqual([entry.purpose for entry in self.database.entries], ["Manufacture", "Manufacture"])

    def test_purchased_5d0000_in_unrelated_warehouse_is_rejected(self):
        self.use_purchased_5d0000(seed_serial=False)
        self.seed_serial("5D0000", "Other warehouse")
        self.assertIn("error", self.execute())
        self.assertEqual(self.database.entries, [])

    def test_purchased_5d0000_is_restored_if_final_manufacture_fails(self):
        self.use_purchased_5d0000()
        self.database.fail_item = "4D00AB"
        self.assertIn("Simulated final-stage", self.execute()["error"])
        serial = self.database.docs["Serial No"]["HAND-0070"]
        self.assertEqual((serial.item_code, serial.warehouse), ("5D0000", flow.MAIN_STOCK_WAREHOUSE))
        self.assertEqual(self.database.stock[("5D0000", "EXISTING-BATCH", flow.MAIN_STOCK_WAREHOUSE)], 1)
        self.assertEqual(self.database.entries, [])

    def use_42_flow(self):
        """Four-unit 42 -> serialized 521000 -> non-serialized 520000 orders."""
        self.database.docs["Item"] = {
            code: _dict(name=code, has_serial_no=serial, has_batch_no=batch,
                        is_stock_item=1, serial_no_series=None)
            for code, serial, batch in (
                ("420033", 0, 0), ("521000", 1, 0), ("520000", 0, 0), ("MAT", 0, 1))
        }
        self.database.docs["BOM"] = {}
        self.database.docs["Work Order"] = {}
        for code, name, parent, quantity, components in (
            ("420033", "WO-42", "", 2, [row("521000", 2), row("MAT", 4)]),
            ("521000", "WO-521000", "WO-42", 1, [row("520000")]),
            ("520000", "WO-520000", "WO-521000", 2, [row("MAT", 6)]),
        ):
            bom = Document(name="BOM-" + code, item=code, company=flow.COMPANY,
                           quantity=quantity, items=components, docstatus=1, is_active=1)
            self.database.docs["BOM"][bom.name] = bom
            self.database.docs["Work Order"][name] = Document(
                name=name, production_item=code, bom_no=bom.name, company=flow.COMPANY,
                docstatus=1, status="Not Started", qty=4, produced_qty=0,
                material_transferred_for_manufacturing=0, sales_order="SO-TEST",
                parent_work_order=parent, wip_step=int(code.startswith("42")),
                skip_transfer=int(code.startswith("42")), use_multi_level_bom=0,
                wip_warehouse=flow.WIP_WAREHOUSE, fg_warehouse=flow.MAIN_STOCK_WAREHOUSE,
                required_items=[_dict(component, required_qty=component.stock_qty / quantity * 4,
                                      consumed_qty=0, transferred_qty=0) for component in components],
            )
        self.database.stock = {
            ("520000", None, flow.MAIN_STOCK_WAREHOUSE): 4,
            ("MAT", "MAT-BATCH", flow.MAIN_STOCK_WAREHOUSE): 100,
        }
        self.database.native_unconsumed = True
        self.database.begin_snapshot()

    def test_four_unit_42_order_consumes_one_520000_and_produces_one_body_and_product_per_call(self):
        self.use_42_flow()
        for number in range(1, 5):
            start = len(self.database.entries)
            result = flow.make_stock_entry("WO-42", "BODY-{}".format(number))
            self.assertNotIn("error", result)
            entries = self.database.entries[start:]
            manufactured = [entry for entry in entries if entry.purpose == "Manufacture"]
            self.assertEqual([entry.work_order for entry in manufactured], ["WO-521000", "WO-42"])
            self.assertTrue(all(entry.fg_completed_qty == 1 for entry in entries))
            for entry in manufactured:
                self.assertEqual(entry.items[-1].transfer_qty, 1)
                self.assertEqual(entry.items[0].transfer_qty, 1)
            # Other BOM materials retain their correct per-finished-unit amount.
            self.assertEqual(manufactured[-1].items[1].transfer_qty, 2)
            self.assertEqual(self.database.docs["Work Order"]["WO-42"].produced_qty, number)
            self.assertEqual(self.database.docs["Work Order"]["WO-521000"].produced_qty, number)
            self.assertEqual(self.database.stock[("520000", None, flow.MAIN_STOCK_WAREHOUSE)], 4 - number)
            self.database.begin_snapshot()  # Commit this successful request in the in-memory ledger.
        self.assertEqual(len(self.database.docs["Work Order"]), 3)
        self.assertEqual(self.database.docs["Work Order"]["WO-42"].qty, 4)
        self.assertEqual(self.database.docs["Work Order"]["WO-520000"].produced_qty, 0)
        before = copy.deepcopy((self.database.stock, self.database.entries))
        self.assertIn("cannot produce another unit", flow.make_stock_entry("WO-42", "BODY-5")["error"])
        self.assertEqual(before, (self.database.stock, self.database.entries))

    def test_521000_order_alone_manufactures_one_serialized_body_per_call(self):
        self.use_42_flow()
        for number in range(1, 5):
            result = flow.make_stock_entry("WO-521000", "BODY-{}".format(number))
            self.assertNotIn("error", result)
            self.assertEqual(result.fg_completed_qty, 1)
            self.assertEqual(result.items[0].transfer_qty, 1)
            self.assertEqual(result.items[-1].transfer_qty, 1)
            self.assertEqual(self.database.docs["Work Order"]["WO-521000"].produced_qty, number)
            self.database.begin_snapshot()
        self.assertEqual(self.database.docs["Work Order"]["WO-42"].produced_qty, 0)
        self.assertEqual(self.database.stock[("520000", None, flow.MAIN_STOCK_WAREHOUSE)], 0)
        self.assertIn("error", flow.make_stock_entry("WO-521000", "BODY-5"))

    def test_520000_order_alone_manufactures_one_non_serialized_raw_body_per_call(self):
        self.use_42_flow()
        for number in range(1, 5):
            result = flow.make_stock_entry("WO-520000", "RAW-{}".format(number))
            self.assertNotIn("error", result)
            self.assertEqual(result.fg_completed_qty, 1)
            self.assertEqual(result.items[0].transfer_qty, 3)
            self.assertEqual(result.items[-1].transfer_qty, 1)
            self.assertFalse(result.items[-1].serial_no)
            self.assertEqual(self.database.docs["Work Order"]["WO-520000"].produced_qty, number)
            self.database.begin_snapshot()
        self.assertEqual(self.database.stock[("520000", None, flow.MAIN_STOCK_WAREHOUSE)], 8)
        self.assertEqual(self.database.docs["Serial No"], {})
        self.assertIn("error", flow.make_stock_entry("WO-520000", "RAW-5"))

    def test_42_consumed_serial_cannot_advance_the_order_twice(self):
        self.use_42_flow()
        self.assertNotIn("error", flow.make_stock_entry("WO-42", "BODY-1"))
        self.database.begin_snapshot()
        before = copy.deepcopy((self.database.stock, self.database.entries))
        self.assertIn("error", flow.make_stock_entry("WO-42", "BODY-1"))
        self.assertEqual(before, (self.database.stock, self.database.entries))
        self.assertEqual(self.database.docs["Work Order"]["WO-42"].produced_qty, 1)

    def test_42_four_units_already_transferred_to_wip_are_consumed_one_at_a_time(self):
        self.use_42_flow()
        self.database.docs["Work Order"]["WO-521000"].material_transferred_for_manufacturing = 4
        self.database.stock[("520000", None, flow.MAIN_STOCK_WAREHOUSE)] = 0
        self.database.stock[("520000", None, flow.WIP_WAREHOUSE)] = 4
        self.database.begin_snapshot()
        for number in range(1, 5):
            start = len(self.database.entries)
            self.assertNotIn("error", flow.make_stock_entry("WO-42", "BODY-{}".format(number)))
            self.assertEqual([entry.purpose for entry in self.database.entries[start:]],
                             ["Manufacture", "Manufacture"])
            self.assertEqual(self.database.stock[("520000", None, flow.WIP_WAREHOUSE)], 4 - number)
            self.database.begin_snapshot()

    def test_42_failed_second_unit_preserves_the_first_completed_unit(self):
        self.use_42_flow()
        self.assertNotIn("error", flow.make_stock_entry("WO-42", "BODY-1"))
        self.database.begin_snapshot()
        before = copy.deepcopy((self.database.stock, self.database.entries))
        self.database.fail_item = "420033"
        self.assertIn("Simulated final-stage", flow.make_stock_entry("WO-42", "BODY-2")["error"])
        self.assertEqual(before, (self.database.stock, self.database.entries))
        self.assertEqual(self.database.docs["Work Order"]["WO-42"].produced_qty, 1)
        self.assertEqual(self.database.docs["Work Order"]["WO-521000"].produced_qty, 1)
        self.assertNotIn("BODY-2", self.database.docs["Serial No"])

    def test_42_read_only_preview_explicitly_plans_one_unit_per_manufacture(self):
        self.use_42_flow()
        before = copy.deepcopy(self.database.docs)
        report = flow.debug_stock_entry_flow("WO-42", "BODY-1", [{"batch_no": "MAT-BATCH"}])
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(len(report["planned_documents"]), 2)
        self.assertTrue(all(doc["fg_completed_qty"] == 1 for doc in report["planned_documents"]))
        self.assertEqual(self.database.docs, before)
        self.assertEqual(self.database.entries, [])

    def test_four_unit_4d_chain_still_advances_each_stage_once_per_call(self):
        self.database.native_unconsumed = True
        for number in range(1, 5):
            start = len(self.database.entries)
            self.assertNotIn("error", self.execute("HAND-{}".format(number)))
            entries = self.database.entries[start:]
            manufactured = [entry for entry in entries if entry.purpose == "Manufacture"]
            self.assertEqual(len(manufactured), 3)
            self.assertTrue(all(entry.fg_completed_qty == 1 for entry in entries))
            self.assertEqual([entry.items[0].transfer_qty for entry in manufactured], [2, 1, 1])
            for order in self.database.docs["Work Order"].values():
                self.assertEqual(order.produced_qty, number)
            self.database.begin_snapshot()

    def test_unit_material_limit_uses_stock_uom_and_shares_limit_across_rows(self):
        self.use_42_flow()
        order = self.database.docs["Work Order"]["WO-42"]
        entry = Entry(self.database)
        entry.items = [Document(item_code="MAT", qty=2, conversion_factor=0.5,
                                s_warehouse=flow.MAIN_STOCK_WAREHOUSE),
                       Document(item_code="MAT", qty=8, conversion_factor=0.5,
                                s_warehouse=flow.MAIN_STOCK_WAREHOUSE),
                       Document(item_code="MAT", qty=8, conversion_factor=0.5,
                                s_warehouse=flow.MAIN_STOCK_WAREHOUSE),
                       Document(item_code="420033", qty=1, transfer_qty=1, s_warehouse=None)]
        flow._limit_materials_to_one_unit(entry, order)
        self.assertEqual([item.transfer_qty for item in entry.items], [1, 1, 1])
        self.assertEqual([item.qty for item in entry.items], [2, 2, 1])

    def test_unit_limit_preserves_native_credit_for_previously_consumed_material(self):
        self.use_42_flow()
        order = self.database.docs["Work Order"]["WO-42"]
        order.required_items[1].consumed_qty = 1.5  # Two MAT are required per output unit.
        entry = flow._new_stock_entry(order, "Manufacture", flow.MAIN_STOCK_WAREHOUSE,
                                      flow.MAIN_STOCK_WAREHOUSE)
        self.assertEqual(entry.items[1].transfer_qty, 0.5)


if __name__ == "__main__":
    unittest.main()
