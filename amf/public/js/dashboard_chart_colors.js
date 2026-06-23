(function () {
	"use strict";

	function install_dataset_color_support() {
		if (!window.frappe || !frappe.Chart) {
			return false;
		}

		if (frappe.Chart.__amf_dataset_colors_patched) {
			return true;
		}

		const OriginalChart = frappe.Chart;

		class AMFChart extends OriginalChart {
			constructor(parent, options) {
				let chart_options = options;
				const dataset_colors = options && options.data && options.data.colors;

				if (Array.isArray(dataset_colors) && dataset_colors.length) {
					chart_options = Object.assign({}, options, {
						colors: dataset_colors.slice()
					});
				}

				super(parent, chart_options);
			}
		}

		AMFChart.__amf_dataset_colors_patched = true;
		AMFChart.__amf_original_chart = OriginalChart;
		frappe.Chart = AMFChart;
		return true;
	}

	if (install_dataset_color_support()) {
		return;
	}

	let attempts = 0;
	const install_timer = window.setInterval(function () {
		attempts += 1;
		if (install_dataset_color_support() || attempts >= 100) {
			window.clearInterval(install_timer);
		}
	}, 100);
}());
