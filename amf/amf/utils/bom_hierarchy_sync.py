import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


@frappe.whitelist()
def sync_latest_bom_hierarchy(root_item_code, dry_run=0, verbose=1):
	"""
	Run one complete BOM hierarchy synchronization starting from `root_item_code`.

	What this method does:
	1. Find the latest active + submitted BOM for the root item.
	2. Walk down through all child items that themselves have BOMs.
	3. Align the default BOM on each manufactured item to the latest BOM found.
	4. Recompute each BOM bottom-up so parent BOMs consume the refreshed child costs.
	5. Persist BOM totals and Item valuation fields unless `dry_run=1`.

	The `verbose` flag is intentionally enabled by default because this method is
	meant to be executed from the terminal with `bench execute`, and the user wants
	to see every important decision directly in the console output.
	"""
	root_item_code = (root_item_code or "").strip()
	dry_run = cint(dry_run)
	verbose = cint(verbose)

	if not root_item_code:
		frappe.throw(_("root_item_code is required"))

	_trace(
		verbose,
		"Starting hierarchy sync for root item {0} (dry_run={1})".format(
			root_item_code, dry_run
		),
	)

	hierarchy = _collect_latest_bom_hierarchy(root_item_code, verbose=verbose)
	if not hierarchy["root_bom"]:
		frappe.throw(_("No active, submitted BOM found for item {0}").format(root_item_code))

	_trace(
		verbose,
		"Hierarchy discovery complete. Root BOM is {0}. {1} manufactured item(s) and {2} BOM(s) will be processed.".format(
			hierarchy["root_bom"],
			len(hierarchy["item_to_bom"]),
			len(hierarchy["boms_bottom_up"]),
		),
	)

	results = {
		"root_item_code": root_item_code,
		"root_bom": hierarchy["root_bom"],
		"dry_run": bool(dry_run),
		"default_updates": [],
		"bom_updates": [],
	}

	for item_code, latest_bom in hierarchy["item_to_bom"].items():
		default_update = _align_default_bom(
			item_code,
			latest_bom,
			dry_run=bool(dry_run),
			verbose=verbose,
		)
		if default_update:
			results["default_updates"].append(default_update)

	for bom_name in hierarchy["boms_bottom_up"]:
		results["bom_updates"].append(
			_sync_bom_to_latest_children(
				bom_name,
				hierarchy["item_to_bom"],
				dry_run=bool(dry_run),
				verbose=verbose,
			)
		)

	if not dry_run:
		_trace(verbose, "Committing all BOM and Item updates to the database.")
		frappe.db.commit()
	else:
		_trace(verbose, "Dry-run finished. No database changes were committed.")

	_trace(
		verbose,
		"Hierarchy sync finished for root item {0}. Default updates: {1}. BOM recalculations: {2}.".format(
			root_item_code,
			len(results["default_updates"]),
			len(results["bom_updates"]),
		),
	)

	return results


@frappe.whitelist()
def sync_latest_bom_hierarchy_for_all_items(dry_run=0, verbose=0):
	"""
	Run the hierarchy synchronization for every enabled item that has at least one
	active submitted BOM.

	Important behavior:
	1. Items are collected once from the BOM table, so we only consider
	   manufactured items that currently have a usable BOM.
	2. If an item's latest BOM was already processed while syncing an earlier root
	   hierarchy, that item is skipped to avoid redundant work.
	3. Errors are isolated per root item so one broken hierarchy does not stop the
	   full batch run.
	"""
	dry_run = cint(dry_run)
	verbose = cint(verbose)

	root_items = _get_all_sync_candidate_items(verbose=verbose)
	processed_boms = set()
	results = {
		"dry_run": bool(dry_run),
		"total_candidates": len(root_items),
		"processed_roots": [],
		"skipped_roots": [],
		"errors": [],
	}

	_trace(
		verbose,
		"Starting full-item BOM hierarchy sync for {0} candidate item(s) (dry_run={1}).".format(
			len(root_items), dry_run
		),
	)

	for index, item_code in enumerate(root_items, start=1):
		latest_bom = _get_latest_active_submitted_bom(item_code, verbose=False)
		if not latest_bom:
			results["skipped_roots"].append(
				{
					"item_code": item_code,
					"reason": "no_active_submitted_bom",
				}
			)
			_trace(
				verbose,
				"[{0}/{1}] Skipping item {2}: no active submitted BOM.".format(
					index, len(root_items), item_code
				),
			)
			continue

		if latest_bom in processed_boms:
			results["skipped_roots"].append(
				{
					"item_code": item_code,
					"reason": "already_processed_in_previous_hierarchy",
					"latest_bom": latest_bom,
				}
			)
			_trace(
				verbose,
				"[{0}/{1}] Skipping item {2}: latest BOM {3} was already processed in a previous hierarchy.".format(
					index, len(root_items), item_code, latest_bom
				),
			)
			continue

		_trace(
			verbose,
			"[{0}/{1}] Processing root item {2} with latest BOM {3}.".format(
				index, len(root_items), item_code, latest_bom
			),
		)

		try:
			root_result = sync_latest_bom_hierarchy(
				root_item_code=item_code,
				dry_run=dry_run,
				verbose=verbose,
			)
			results["processed_roots"].append(
				{
					"item_code": item_code,
					"root_bom": root_result.get("root_bom"),
					"bom_count": len(root_result.get("bom_updates", [])),
					"default_update_count": len(root_result.get("default_updates", [])),
				}
			)
			processed_boms.update(
				update.get("bom")
				for update in root_result.get("bom_updates", [])
				if update.get("bom")
			)
			_trace(
				verbose,
				"[{0}/{1}] Root item {2} completed. Hierarchy BOM count={3}.".format(
					index,
					len(root_items),
					item_code,
					len(root_result.get("bom_updates", [])),
				),
			)
		except Exception as exc:
			frappe.db.rollback()
			error_message = str(exc)
			results["errors"].append(
				{
					"item_code": item_code,
					"latest_bom": latest_bom,
					"error": error_message,
				}
			)
			frappe.log_error(
				frappe.get_traceback(),
				"Full BOM Hierarchy Sync Error for {0}".format(item_code),
			)
			_trace(
				verbose,
				"[{0}/{1}] ERROR while processing root item {2}: {3}".format(
					index, len(root_items), item_code, error_message
				),
			)

	_trace(
		verbose,
		(
			"Full-item BOM hierarchy sync finished. processed_roots={0}, "
			"skipped_roots={1}, errors={2}."
		).format(
			len(results["processed_roots"]),
			len(results["skipped_roots"]),
			len(results["errors"]),
		),
	)

	return results


@frappe.whitelist()
def enqueue_sync_latest_bom_hierarchy_for_all_items(dry_run=0, verbose=0):
	"""
	Queue the all-items BOM hierarchy synchronization on the long worker.

	Use this entry point when the batch is too large for a foreground terminal
	run or when you want the worker to handle the full pass asynchronously.
	"""
	dry_run = cint(dry_run)
	verbose = cint(verbose)

	_trace(
		verbose,
		"Queueing full-item BOM hierarchy sync (dry_run={0}, verbose={1}) on the long worker.".format(
			dry_run, verbose
		),
	)
	job = frappe.enqueue(
		"amf.amf.utils.bom_hierarchy_sync.sync_latest_bom_hierarchy_for_all_items",
		queue="long",
		timeout=15000,
		dry_run=dry_run,
		verbose=verbose,
	)

	job_id = None
	if hasattr(job, "id"):
		job_id = job.id
	elif hasattr(job, "name"):
		job_id = job.name

	_trace(
		verbose,
		"Full-item BOM hierarchy sync enqueued successfully. job_id={0}".format(
			job_id or "unknown"
		),
	)
	return {
		"status": "queued",
		"job_id": job_id,
		"dry_run": bool(dry_run),
		"verbose": bool(verbose),
	}


def _collect_latest_bom_hierarchy(root_item_code, verbose=False):
	"""
	Discover the BOM tree from the root item down to the deepest manufactured
	children.

	The output is intentionally prepared in bottom-up order, because parent BOMs
	must only be recalculated after their child BOM costs are already refreshed.
	"""
	item_to_bom = {}
	boms_bottom_up = []
	visiting = set()

	def visit_item(item_code):
		_trace(verbose, "Inspecting item {0} for its latest active submitted BOM.".format(item_code))
		latest_bom = _get_latest_active_submitted_bom(item_code, verbose=verbose)
		if not latest_bom:
			_trace(
				verbose,
				"Item {0} has no active submitted BOM. It will be treated as a purchased/raw-material line.".format(
					item_code
				),
			)
			return None

		existing_bom = item_to_bom.get(item_code)
		if existing_bom:
			_trace(
				verbose,
				"Item {0} was already visited earlier. Reusing discovered BOM {1}.".format(
					item_code, existing_bom
				),
			)
			return existing_bom

		if item_code in visiting:
			frappe.throw(_("BOM recursion detected while processing item {0}").format(item_code))

		# Mark the item as "currently being traversed" so recursive BOM loops can be
		# detected immediately instead of silently corrupting the hierarchy walk.
		visiting.add(item_code)
		item_to_bom[item_code] = latest_bom
		_trace(
			verbose,
			"Item {0} will use BOM {1} as the latest BOM in the hierarchy.".format(
				item_code, latest_bom
			),
		)

		bom_doc = frappe.get_doc("BOM", latest_bom)
		for row in bom_doc.items:
			if row.item_code and row.item_code != bom_doc.item:
				_trace(
					verbose,
					"Following BOM {0} row {1}: item_code={2}, current bom_no={3}".format(
						latest_bom,
						row.idx,
						row.item_code,
						row.bom_no or "",
					),
				)
				visit_item(row.item_code)

		visiting.remove(item_code)
		boms_bottom_up.append(latest_bom)
		_trace(
			verbose,
			"BOM {0} added to bottom-up processing list position {1}.".format(
				latest_bom, len(boms_bottom_up)
			),
		)
		return latest_bom

	root_bom = visit_item(root_item_code)
	return {
		"root_bom": root_bom,
		"item_to_bom": item_to_bom,
		"boms_bottom_up": boms_bottom_up,
	}


def _get_all_sync_candidate_items(verbose=False):
	"""
	Return every enabled item that currently has an active submitted BOM.

	Using the BOM table as the starting point ensures the batch job only targets
	items that are relevant for manufacturing/BOM synchronization.
	"""
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT bom.item
		FROM `tabBOM` bom
		INNER JOIN `tabItem` item ON item.name = bom.item
		WHERE bom.is_active = 1
			AND bom.docstatus = 1
			AND item.disabled = 0
		ORDER BY bom.item
		""",
		as_dict=True,
	)
	items = [row.item for row in rows if row.get("item")]
	_trace(
		verbose,
		"Collected {0} enabled item(s) with at least one active submitted BOM.".format(
			len(items)
		),
	)
	return items


def _get_latest_active_submitted_bom(item_code, verbose=False):
	"""
	Return the most recently created active submitted BOM for one item.

	We use creation order here because the pilot requirement is to follow the
	latest BOM version at every hierarchy level, not simply whatever BOM is
	currently marked as default.
	"""
	boms = frappe.get_all(
		"BOM",
		filters={"item": item_code, "is_active": 1, "docstatus": 1},
		fields=["name", "creation", "modified", "is_default", "total_cost"],
		order_by="creation desc, name desc",
		limit_page_length=1,
	)
	if not boms:
		_trace(verbose, "No candidate BOM found for item {0}.".format(item_code))
		return None

	latest_bom = boms[0]
	_trace(
		verbose,
		"Latest BOM for item {0} is {1} (created {2}, modified {3}, is_default={4}, total_cost={5}).".format(
			item_code,
			latest_bom.name,
			latest_bom.creation,
			latest_bom.modified,
			latest_bom.is_default,
			flt(latest_bom.total_cost),
		),
	)
	return latest_bom.name


def _align_default_bom(item_code, latest_bom, dry_run=False, verbose=False):
	"""
	Make sure the Item master and BOM flags point to the latest BOM selected for
	the hierarchy run.

	This step keeps the item master coherent with the BOM version actually used for
	the bottom-up recalculation.
	"""
	current_default = frappe.db.get_value("Item", item_code, "default_bom")
	current_default_flag = cint(frappe.db.get_value("BOM", latest_bom, "is_default") or 0)
	other_defaults = frappe.get_all(
		"BOM",
		filters={"item": item_code, "is_default": 1, "name": ["!=", latest_bom]},
		fields=["name"],
	)

	if current_default == latest_bom and current_default_flag and not other_defaults:
		_trace(
			verbose,
			"Item {0} already points to latest BOM {1}; no default-BOM alignment needed.".format(
				item_code, latest_bom
			),
		)
		return None

	_trace(
		verbose,
		"Aligning Item {0} to latest BOM {1}. Previous Item.default_bom={2}. Other default BOMs to clear: {3}".format(
			item_code,
			latest_bom,
			current_default or "",
			[row.name for row in other_defaults],
		),
	)

	if not dry_run:
		if other_defaults:
			_trace(
				verbose,
				"Clearing stale default flags for item {0}: {1}".format(
					item_code, [row.name for row in other_defaults]
				),
			)
			frappe.db.sql(
				"""
				UPDATE `tabBOM`
				SET `is_default` = 0
				WHERE `item` = %(item)s
					AND `name` != %(latest_bom)s
					AND `is_default` = 1
				""",
				{"item": item_code, "latest_bom": latest_bom},
			)
		_trace(verbose, "Setting BOM {0} as default for item {1}.".format(latest_bom, item_code))
		frappe.db.set_value("BOM", latest_bom, "is_default", 1, update_modified=False)
		item_values = {"default_bom": latest_bom}
		if frappe.db.has_column("Item", "item_default_bom"):
			item_values["item_default_bom"] = latest_bom
		_trace(
			verbose,
			"Updating Item {0} default BOM fields with values {1}.".format(
				item_code, item_values
			),
		)
		frappe.db.set_value("Item", item_code, item_values, update_modified=False)
	else:
		_trace(
			verbose,
			"Dry-run: Item {0} would be aligned to latest BOM {1}.".format(
				item_code, latest_bom
			),
		)

	return {
		"item_code": item_code,
		"from_default_bom": current_default or "",
		"to_default_bom": latest_bom,
		"cleared_other_defaults": [row.name for row in other_defaults],
	}


def _sync_bom_to_latest_children(bom_name, item_to_bom, dry_run=False, verbose=False):
	"""
	Refresh one BOM using the latest child BOM mapping discovered earlier.

	For each BOM row:
	- manufactured child items get their newest BOM in `bom_no`
	- purchased/raw items get `bom_no = None`
	- ERPNext's native `update_cost()` recalculates row rates and total cost

	We then persist the recomputed row values explicitly so the database reflects
	the exact state that was used in the cost rollup.
	"""
	bom_doc = frappe.get_doc("BOM", bom_name)
	before_total_cost = flt(bom_doc.total_cost)
	_trace(
		verbose,
		"Recomputing BOM {0} for item {1}. Starting total_cost={2}.".format(
			bom_doc.name, bom_doc.item, before_total_cost
		),
	)
	before_rows = {
		row.name: {
			"bom_no": row.bom_no or "",
			"rate": flt(row.rate),
			"amount": flt(row.amount),
		}
		for row in bom_doc.items
	}

	for row in bom_doc.items:
		expected_bom = ""
		if row.item_code and row.item_code != bom_doc.item:
			expected_bom = item_to_bom.get(row.item_code) or ""
		_trace(
			verbose,
			"BOM {0} row {1} item {2}: old bom_no={3}, expected latest bom_no={4}".format(
				bom_doc.name,
				row.idx,
				row.item_code,
				row.bom_no or "",
				expected_bom,
			),
		)
		row.bom_no = expected_bom or None

	# Delegate the actual rate calculation to ERPNext's BOM controller so the
	# costing logic stays aligned with the platform rules already used elsewhere.
	_trace(verbose, "Calling ERPNext update_cost() for BOM {0}.".format(bom_doc.name))
	bom_doc.update_cost(update_parent=False, save=False)
	_trace(
		verbose,
		"ERPNext recalculation completed for BOM {0}. New total_cost={1}.".format(
			bom_doc.name, flt(bom_doc.total_cost)
		),
	)

	changed_rows = []
	for row in bom_doc.items:
		before_row = before_rows[row.name]
		after_bom = row.bom_no or ""
		after_rate = flt(row.rate)
		after_amount = flt(row.amount)
		if (
			before_row["bom_no"] != after_bom
			or before_row["rate"] != after_rate
			or before_row["amount"] != after_amount
		):
			changed_rows.append(
				{
					"idx": row.idx,
					"item_code": row.item_code,
					"from_bom_no": before_row["bom_no"],
					"to_bom_no": after_bom,
					"from_rate": before_row["rate"],
					"to_rate": after_rate,
					"from_amount": before_row["amount"],
					"to_amount": after_amount,
					}
				)
			_trace(
				verbose,
				(
					"BOM {0} row {1} changed: item={2}, bom_no {3} -> {4}, "
					"rate {5} -> {6}, amount {7} -> {8}"
				).format(
					bom_doc.name,
					row.idx,
					row.item_code,
					before_row["bom_no"],
					after_bom,
					before_row["rate"],
					after_rate,
					before_row["amount"],
					after_amount,
				),
			)

	if not dry_run:
		_trace(
			verbose,
			"Persisting {0} BOM row(s) and header totals for BOM {1}.".format(
				len(bom_doc.items), bom_doc.name
			),
		)
		for row in bom_doc.items:
			row.db_update()
		bom_doc.db_update()
		_update_item_cost_fields(
			bom_doc.item,
			bom_doc.name,
			bom_doc.total_cost,
			verbose=verbose,
		)
	else:
		_trace(
			verbose,
			"Dry-run: BOM {0} recalculated but not saved to the database.".format(
				bom_doc.name
			),
		)

	return {
		"bom": bom_doc.name,
		"item": bom_doc.item,
		"row_changes": changed_rows,
		"total_cost_before": before_total_cost,
		"total_cost_after": flt(bom_doc.total_cost),
	}


def _update_item_cost_fields(item_code, default_bom, bom_total_cost, verbose=False):
	"""
	Update Item-level fields that mirror BOM cost information.

	This keeps the Item master aligned with the recalculated default BOM so other
	custom AMF processes reading Item valuation or BOM cost fields see the new
	values immediately after the hierarchy sync.
	"""
	values = {
		"default_bom": default_bom,
		"valuation_rate": flt(bom_total_cost),
	}
	if frappe.db.has_column("Item", "item_default_bom"):
		values["item_default_bom"] = default_bom
	if frappe.db.has_column("Item", "bom_cost"):
		values["bom_cost"] = flt(bom_total_cost)

	_trace(
		verbose,
		"Updating Item {0} cost mirror fields with values {1}.".format(
			item_code, values
		),
	)
	frappe.db.set_value("Item", item_code, values, update_modified=False)


def _trace(enabled, message):
	"""Small helper to keep terminal output consistent and easy to scan."""
	if enabled:
		print("[BOM Sync {0}] {1}".format(now_datetime(), message))
