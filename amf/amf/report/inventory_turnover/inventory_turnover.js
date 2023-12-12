// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Inventory Turnover"] = {
	"filters": [

	],

	onload: function (report) {
		// Define the HTML content
		var customHtmlContent = `
		<div style="padding-left: 80px; padding-right: 80px;">
			<h2>1. Inventory Turnover Ratio (0.65)</h2>
			<p>This ratio reflects how many times your company's inventory is sold and replaced over a certain period. A ratio of 0.65 indicates that you sold and replaced about 65% of your inventory during the period.</p>
			<h3>Interpretation:</h3>
			<ul>
				<li><strong>Slow Inventory Movement:</strong> Typically, a ratio less than 1 suggests slow inventory movement. It means your inventory isn't being sold as quickly as might be ideal.</li>
				<li><strong>Capital Allocation:</strong> A lower turnover ratio can indicate that a significant amount of your capital is tied up in inventory. This might affect cash flow and could suggest overstocking or issues with demand forecasting.</li>
				<li><strong>Product Strategy:</strong> Certain products might not be selling as expected. It could be beneficial to analyze which items are underperforming and why.</li>
				<li><strong>Seasonality:</strong> In some businesses, a low inventory turnover might be seasonal and expected. However, if this isn’t the case, strategies to increase sales or reduce inventory levels might be needed.</li>
			</ul>
		
			<h2>2. Days Sales of Inventory (DSI) (280.97)</h2>
			<p>DSI indicates the average number of days it takes for your inventory to be sold. A DSI of 280.97 means that, on average, it takes about 281 days to sell your entire inventory.</p>
			<h3>Interpretation:</h3>
			<ul>
				<li><strong>Long Sales Cycle:</strong> The high DSI value suggests a long sales cycle, meaning your inventory is sitting for an extended period before being sold.</li>
				<li><strong>Cash Flow Impact:</strong> A higher DSI can negatively impact cash flow, as capital is tied up in inventory for longer periods.</li>
				<li><strong>Inventory Management:</strong> This might be an indication to reevaluate inventory levels or management practices. Consider whether some inventory items are overstocked or if there are issues with particular product lines.</li>
				<li><strong>Market Demand and Pricing Strategies:</strong> Review market demand and pricing strategies. It might be necessary to adjust pricing, run promotions, or even phase out certain products.</li>
			</ul>
		
			<h3>Combined Interpretation</h3>
			<p>Together, an Inventory Turnover Ratio of 0.65 and a DSI of 280.97 suggest that your inventory is moving slowly. This scenario can have implications for cash flow, storage costs, and overall business efficiency. It’s important to delve deeper into the reasons behind these figures, as they might indicate overstocking, suboptimal inventory management, or issues with product demand.</p>
			<h3>Actionable Steps</h3>
			<ul>
				<li><strong>Inventory Review:</strong> Analyze your inventory to identify slow-moving items. Consider clearance sales, discounts, or other promotional activities to move these items more quickly.</li>
				<li><strong>Demand Forecasting:</strong> Improve demand forecasting to better align inventory levels with actual sales trends.</li>
				<li><strong>Supplier Relations:</strong> Review your ordering and restocking strategies. You may negotiate better terms with suppliers or move to a just-in-time inventory system to reduce holding costs.</li>
				<li><strong>Market Strategy:</strong> Investigate market trends and customer preferences. There might be a need to adjust your product offerings or marketing strategies.</li>
			</ul>
		
			<h3>Conclusion</h3>
			<p>In conclusion, these metrics indicate that your inventory management strategy might need reassessment to optimize turnover and reduce the average time inventory is held. It’s crucial to understand the underlying factors contributing to these figures and take appropriate actions to improve inventory efficiency.</p>
		</div>
	
        `;

		// Append the HTML content after the report is fully loaded
		frappe.after_ajax(function () {
			$(customHtmlContent).appendTo("footer");
		});
	}
};
