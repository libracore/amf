# DHL Express shipment-draft algorithm

## Validation and creation boundary

MyDHL does not expose a persistent "draft shipment" resource. `POST /shipments`
is the create-shipment operation. The validation action uses
`POST /shipments?validateDataOnly=true`, which does not create an AWB. A separate
operator-confirmed creation action calls `POST /shipments` without that query
parameter only after the exact saved JSON payload has passed validation.

Successful validation stores a SHA-256 fingerprint of the outbound JSON and the
MyDHL environment. Creation rebuilds the payload and requires both the fingerprint
and environment to match. Any changed Shipment, Delivery Note, Sales Order, Sales
Invoice, linked master data, or DHL account setting therefore requires another
validation. A DHL creation response is accepted as successful only when it has the
documented HTTP 201 status and a non-empty `shipmentTrackingNumber`.

The implementation is limited to Delivery Notes whose `carrier` contains the
standalone token `DHL` (case-insensitive). Examples already present in AMF data,
such as `DHL`, `DHL (DAP)` and `EXW (DHL 950...)`, qualify. Values such as UPS,
FedEx and Hand Delivery do not.

## Workflow

1. On a submitted, non-return DHL Delivery Note, choose **Create > DHL Shipment
   Draft**. The mapper opens an unsaved ERPNext `Shipment`.
2. The mapper copies the standard ERPNext shipment parties and Delivery Note
   link. It also copies the exact Carrier, marks the service provider as DHL
   Express, copies the sole Incoterm token from the Delivery Note field labelled
   **Terms** (`tc_name`), copies Packaging Information into one Shipment Parcel,
   and prefills the approved 67-character content description.
3. The operator reviews the mapped parcel, then enters the pickup date/window,
   fetches and explicitly selects a DHL transport product code, enters the
   explicit customs-declarable decision, and any actual DHL
   payer/duties billing account. Product, payer, customs status, or a DHL account
   number is not inferred.
4. **DHL Express > Build DHL Draft** creates a partial JSON request and lists all
   blockers, warnings and source fields. It does not contact DHL and also works
   before the Shipment is saved.
5. On a saved one-package Shipment, **DHL Express > Fetch DHL Transport
   Products** calls MyDHL `GET /products` with the account, lane, parcel,
   planned date and customs status. It creates nothing and displays every
   feasible returned product. The operator must explicitly select one; the
   algorithm never chooses a speed/service commitment. Multi-package product
   discovery requires the separate Rating workflow and is reported explicitly.
6. After saving, **DHL Express > Validate Data with DHL** asks for confirmation,
   rebuilds from the saved documents, stops locally if any blocker exists, then
   sends the request with `validateDataOnly=true`. A successful response means
   only that DHL accepted the data validation; it is not a shipment booking.
7. Only after successful validation of the current payload, **DHL Express > Create
   DHL Shipment / AWB** requires the operator to type `CREATE DHL SHIPMENT`. The
   dialog identifies the Test/Production environment and whether the payload asks
   DHL to book a courier pickup. The server obtains a row lock, rejects prior AWB
   or unresolved attempts, records a unique DHL Message Reference, and commits an
   in-progress marker before sending the irreversible create request.
8. On HTTP 201, ERPNext stores the DHL shipment/AWB number, tracking URL, piece
   tracking IDs, pickup dispatch confirmation when returned, creation environment,
   Message Reference, and payload fingerprint. Returned labels/documents are
   decoded and attached privately to the ERPNext Shipment. Attachment failure is
   reported as a warning and cannot erase an already-created AWB.

If the create request times out, loses its connection, receives a DHL 5xx response,
or receives a 2xx response without the required AWB, its state becomes **Creation
outcome unknown**. ERPNext blocks every automatic retry because DHL may have
created an AWB before the response was lost. The operator must first check the DHL
portal or contact DHL with the stored Message Reference. HTTP 4xx responses become
**Creation failed** and retain the sanitized DHL error response for review.

The result dialog separates local ERPNext checks from DHL's response. A rejection
shows the HTTP status/reason, normalized DHL message, error code and field/path,
plus DHL request identifiers when returned. The complete sanitized MyDHL response
is expanded below the summary, and the outbound validation payload remains
available in a separate section.

## Authoritative source order

| DHL data | ERPNext source | Rule |
| --- | --- | --- |
| Eligibility | Each linked Delivery Note `carrier` | Every Delivery Note must contain the standalone DHL token. |
| Actual lines/quantity/value/customs | Delivery Note Item | Never taken from ordered quantity because a partial delivery may differ. |
| Customer PO | Linked Sales Order `po_no`, plus Delivery Note `po_no` when present | Both explicit values are retained as `PON`; conflicting values are not silently replaced. |
| Sales order | Delivery Note Item `against_sales_order` | Sent as `OID`. Missing links are reported. |
| Delivery note | Linked Delivery Note `name` | Sent as `AAJ`. |
| Receiver address | Shipment `delivery_address_name` | Initially mapped by ERPNext from Delivery Note shipping address, then read from the explicit Shipment value. |
| Receiver contact full name | Delivery Note `contact_person` → Contact `full_name`; DN `contact_display`; linked Sales Order equivalents | DN is authoritative and SO is the fallback. Conflicting contacts within linked DNs or within linked SOs block validation. A company/customer name is never substituted for the required person. |
| Receiver phone/email | The selected DN/SO Contact; Delivery Note phone/email as fallback | DHL-required full name and phone must be present. |
| Shipper address/contact | Shipment pickup Company/Address/Contact/User; AMF DHL Settings fallbacks | No person name is manufactured from the company name. |
| Packages | Each Delivery Note Packaging Information `weight`, `length`, `width`, `height` | The section has one measurement set and no count field, so each linked Delivery Note maps to exactly one physical DHL package and one reviewable Shipment Parcel row. Decimal commas are parsed as decimals, never thousands. |
| Planned tender time | Shipment pickup date/from time and site timezone | Must be in the future and no more than ten days ahead. |
| Pickup request | Shipment `pickup_type` | `Pickup` becomes true; `Self delivery` becomes false. |
| DHL transport product | Shipment `dhl_product_code` | Exactly one shipment-wide global DHL transport service code, returned by MyDHL Product/Rating or confirmed by DHL. It is not a customs tariff/HS code. |
| Customs commodity codes | Each Delivery Note Item `customs_tariff_number_` | Each DN item maps independently to its corresponding DHL export line `commodityCodes: [{typeCode: "outbound", value: ...}]`; spaces are removed and different line-item codes are preserved. |
| Incoterm | Delivery Note `tc_name` (label **Terms**) | It must contain exactly one supported three-letter Incoterm token. Conflicts across linked Delivery Notes block validation. |
| Customs decision | Shipment `dhl_customs_declarable` | Required Yes/No decision; never inferred from country borders. |
| Customs invoice number/date | One submitted, non-return Sales Invoice linked through the Delivery Note items: `name` / `posting_date` (**Invoice Date**); otherwise explicit Shipment DHL Customs Invoice fields | The submitted invoice is authoritative. Multiple submitted invoices require the operator to identify one by an exact number/date pair. A DN posting date, PO date, pickup date, Shipment creation date, or current date is never substituted for the invoice issue date. |
| Shipper account | AMF DHL Settings `shipper_account_number` | Required and exactly nine alphanumeric characters. Free-text Carrier account numbers are deliberately ignored. |
| Receiver EIN/EORI | Organization (`Customer`) `ein` / `tax_id` | Sent as DHL receiver registration number type `EIN` / `EOR`, respectively. EORI issuer code comes from the identifier's required two-letter prefix. |
| Payer/duties accounts | Shipment DHL account fields | Optional explicit DHL Express billing accounts, each exactly nine alphanumeric characters; not inferred from EXW/DDP or EIN/EORI. Leave empty when no separately confirmed DHL account applies. |

## Declarable-goods rules

Country codes first use the two-letter code on the ERPNext Country record. When
that field is blank or invalid, the algorithm performs an exact normalized-name
match against Frappe's bundled ISO country data and Babel's English ISO territory
names. It uses the fallback only when the match resolves to exactly one alpha-2
code and reports the source as a warning; it never guesses among ambiguous names.

When `DHL Customs Declarable` is **Yes**, each actual Delivery Note row becomes a
separate DHL export line. The builder requires a positive integer quantity, an
approved UOM mapping, a manufacturer-country ISO alpha-2 code, a non-negative
unit net rate, and a deterministic positive net weight. An explicit Kg/Gram
`weight_uom` is authoritative. If that UOM is missing or is not a mass unit, a
positive `total_weight`/`weight_per_unit` can be used only when the corresponding
AMF field label explicitly declares kilograms (currently **Total Weight kg** and
**Unit Weight kg**); the ignored UOM and resolved kilogram value are reported as
a warning. `custom_description` is preferred over item name/description. The
declared value is the sum of each transmitted unit net rate times actual quantity,
in the single Delivery Note currency.

MyDHL also requires `content.exportDeclaration.invoice.date`. When exactly one
submitted, non-return Sales Invoice is linked to the Delivery Note items, its
document name and **Invoice Date** are sent as the customs invoice number/date.
Conflicting manual Shipment values block validation. If no submitted Sales
Invoice exists, the operator must enter the customs invoice issue date explicitly;
the invoice number remains optional. If multiple submitted invoices exist, both
explicit Shipment fields must exactly select one of them.

The customs tariff number is transmitted as the outbound commodity code when
present. Its absence is a warning rather than a fabricated value because the
OpenAPI schema permits omission while individual customs lanes may still require
it.

## Hard blockers

- non-DHL, unsubmitted, or return Delivery Note;
- missing or invalid Delivery Note Packaging Information;
- missing Incoterm in the selected Delivery Note Terms, or a conflict between
  the selected Terms and the rendered Terms and Conditions Details;
- missing/invalid pickup time, address, country code, named contact or phone;
- missing DHL product, Incoterm, customs Yes/No choice, or shipper account;
- any DHL shipper, payer, or duties/taxes billing account that is not exactly
  nine alphanumeric characters;
- linked Delivery Notes with conflicting currencies or contact identifiers;
- missing customs invoice issue date, conflicting manual and submitted-invoice
  data, or multiple submitted Sales Invoices without an exact explicit selection;
- declarable line with fractional/non-positive quantity, unmapped UOM, missing
  origin, or a weight that cannot be resolved from an explicit mass UOM or an
  explicitly kilogram-labelled source field;
- any value beyond a DHL schema length limit (values are never silently truncated).
- creation without a successful validation fingerprint for the exact current
  payload and current Test/Production environment;
- creation when an AWB already exists, another creation is in progress, or a prior
  creation attempt has an unknown outcome.

## Deliberately not implemented

- automatic creation immediately after validation without a separate typed
  operator confirmation;
- automatic retry when the DHL creation outcome is unknown;
- cancellation of a created DHL shipment or pickup;
- later label/commercial-invoice retrieval when DHL did not include the document
  in the creation response;
- selection of a product without a DHL capability/rating response;
- OCR or interpretation of an attached customer PO PDF;
- extraction of account numbers or commercial terms from free-text Carrier data;
- automatic inference of customs status, additional package count or package dimensions,
  duties payer, export reason, insurance, dangerous goods, or paperless trade.

## EIN/EORI is not a DHL billing account

MyDHL `accounts` with type `duties-taxes` requires a DHL Express account number
that DHL is authorised to bill. Organization EIN/EORI values are customs/tax
registrations and are therefore sent under receiver `registrationNumbers`.
They are deliberately never copied into the duties/taxes billing account field.
