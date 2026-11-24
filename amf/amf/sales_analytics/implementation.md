# AMF Sales Analytics

The Desk route is `sales-analytics`. The reporting company is Advanced Microfluidics SA in CHF. Published historical periods start on 1 January 2022. Actuals are based on the current submitted ERP documents. Open commitments use the site date at refresh time.

## Verification

From the AMF checkout, with the bench Python environment:

```sh
PYTHONPATH="$PWD" /path/to/frappe-bench/env/bin/python -B -m unittest amf.amf.sales_analytics.test_sales_analytics
node --check amf/amf/page/sales_analytics/sales_analytics.js
```

Reconcile an unchanged October 2026 cohort of 25 submitted invoices to CHF 158,972.92 of item net, CHF 161,202.54 of billed turnover, and CHF 166,289.64 of gross. A later posting or amendment can change the live cohort. The Invoice reconciliation table gives the invoice amounts, tax and charge bridge, legacy AMF Total HT, and Sales Invoice postings to Income accounts.

## Registration and activation

After placing the reviewed AMF revision in an isolated staging bench, register the versioned Page with the installed v12 metadata reload command:

```sh
bench --site <staging> reload-doc amf page sales_analytics
```

The optional reporting records can be registered on staging when testing approved billing dates or targets:

```sh
bench --site <staging> reload-doc amf doctype sales_analytics_billing
bench --site <staging> reload-doc amf doctype sales_analytics_target
```

An Accounts Manager submits a billing record for a specific order and item row number. The billing quantity is expressed in that order row's sales UOM. Use an expected invoice date supported by the commercial agreement. Amend or cancel a stale plan after an order amendment or a change in remaining billing quantity. Overallocated plans appear as exceptions and their remaining value stays unscheduled.

A target specifies the Revenue or Order intake measure, a complete calendar month, quarter or year, and a positive CHF amount. Submitted targets are used for comparisons. There is no automatic phasing of an annual amount.

The site setting `sales_analytics_enabled` can be set to `0` to disable the reporting endpoints. Use scoped metadata registration in the staged release plan. A full bench migration also executes the app's existing unrelated backfill hooks.

## Reporting scope

Billed turnover uses submitted invoice item net plus the approved shipping and card charge accounts. Product rankings use item net. Account codes outside the approved shipping, card and VAT set are surfaced in reconciliation.

The shipping schedule puts the outstanding portion of a shipment-relevant order line into the current month when its recorded shipping month has passed. An overdue flag continues to use the recorded shipping date. On Hold is reported separately. The original ERP shipping date is displayed on the source row.

Document grants, Company restrictions, shares and field permissions apply to the dashboard, underlying detail and downloads. Complete cross-document billing balances require complete eligible access to Sales Order, Delivery Note and Sales Invoice. Per-user scope may differ.
