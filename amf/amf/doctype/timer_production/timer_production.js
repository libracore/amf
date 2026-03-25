// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

const TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE = 65;
const SECONDS_PER_HOUR = 3600;
const TIMER_PRODUCTION_ASSEMBLY_COST_SOURCE_FIELDS = [
    'item_code',
    'quantity',
    'total_duration',
];

frappe.ui.form.on('Timer Production', {
	refresh(frm) {
		if (frm.doc.status) {
			if (frm.doc.status === 'IN PROCESS') {
				frm.page.set_indicator(__('In Process'), 'orange');
			} else if (frm.doc.status === 'FINISHED') {
				frm.page.set_indicator(__('Finished'), 'green');
			} else if (frm.doc.status === 'PAUSED') {
				frm.page.set_indicator(__('Paused'), 'blue');
			} else {
				frm.page.set_indicator(__('Unknown'), 'gray');
			}
		}

		syncAssemblyCostsTable(frm);
	},

	work_order(frm) {
		syncAssemblyCostsTable(frm);
	},

	item_code(frm) {
		syncAssemblyCostsTable(frm);
	},

	quantity(frm) {
		syncAssemblyCostsTable(frm);
	},

	total_duration(frm) {
		syncAssemblyCostsTable(frm);
	},
});

frappe.ui.form.on('Work Order Timer Table', {
	start_time(frm) {
		syncAssemblyCostsTable(frm);
	},

	stop_time(frm) {
		syncAssemblyCostsTable(frm);
	},

	duration(frm) {
		syncAssemblyCostsTable(frm);
	},

	sessions_list_add(frm) {
		syncAssemblyCostsTable(frm);
	},

	sessions_list_remove(frm) {
		syncAssemblyCostsTable(frm);
	},
});

function hasTimerProductionAssemblyCostInputs(doc) {
	return TIMER_PRODUCTION_ASSEMBLY_COST_SOURCE_FIELDS.some(fieldname => {
		const value = doc[fieldname];
		return value !== undefined && value !== null && value !== '';
	});
}

function syncAssemblyCostsTable(frm) {
	if (!frm.fields_dict.assembly_costs) {
		return;
	}

	frm.clear_table('assembly_costs');

	if (!hasTimerProductionAssemblyCostInputs(frm.doc)) {
		frm.refresh_field('assembly_costs');
		return;
	}

	const totalDuration = calculateTimerProductionTotalDuration(frm.doc);
	const totalCost = calculateTimerProductionTotalCost(totalDuration);

	frm.add_child('assembly_costs', {
		item_code: frm.doc.item_code || '',
		total_cost: totalCost,
		time_per_part_minutes: calculateTimerProductionTimePerPartMinutes(totalDuration, frm.doc.quantity),
		cost_per_part: calculateTimerProductionCostPerPart(totalCost, frm.doc.quantity),
	});

	frm.refresh_field('assembly_costs');
}

function calculateTimerProductionTotalDuration(doc) {
	const sessionRows = Array.isArray(doc.sessions_list) ? doc.sessions_list : [];

	if (!sessionRows.length) {
		return flt(doc.total_duration);
	}

	return sessionRows.reduce((totalDuration, session) => {
		if (session.start_time && session.stop_time) {
			const startTime = frappe.datetime.str_to_obj(session.start_time);
			const stopTime = frappe.datetime.str_to_obj(session.stop_time);
			if (startTime && stopTime) {
				return totalDuration + ((stopTime - startTime) / 1000);
			}
		}

		return totalDuration + flt(session.duration);
	}, 0);
}

function calculateTimerProductionTotalCost(totalDuration) {
	// Step 1: convert the stored timer duration from seconds into hours,
	// because the assembly shop rate is defined per hour.
	const totalDurationHours = flt(totalDuration) / SECONDS_PER_HOUR;

	// Step 2: apply the fixed assembly rate of 65 CHF/hour once the units match.
	const totalCost = totalDurationHours * TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE;

	// Step 3: round the result to 2 decimals because this value is currency.
	return flt(totalCost, 2);
}

function calculateTimerProductionCostPerPart(totalCost, quantity) {
	const producedQty = flt(quantity);
	if (producedQty <= 0) {
		return 0;
	}

	return flt(flt(totalCost) / producedQty, 2);
}

function calculateTimerProductionTimePerPartMinutes(totalDuration, quantity) {
	// Step 1: distribute the total timer duration across the produced quantity.
	const producedQty = flt(quantity);
	if (producedQty <= 0) {
		return 0;
	}

	// Step 2: the duration is stored in seconds, so convert seconds per part into minutes.
	const timePerPartSeconds = flt(totalDuration) / producedQty;
	return flt(timePerPartSeconds / 60, 2);
}
