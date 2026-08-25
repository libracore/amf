# AMF Issue Classification And Process Routing

## Purpose

AMF Issues are classified by the nature of the problem and routed to the process that must prevent recurrence. The process is not necessarily the department that detected the problem.

The model separates three concepts that were previously mixed together:

1. `Input Selection` records where the Issue originated: customer, supplier or internal.
2. `Issue Type` records the precise nature of the problem.
3. `Process` records accountability for investigation, corrective action and process learning.

An outcome such as `No Issue Found` is recorded in `Issue Outcome`; it is not an Issue Type.

## Accountable Processes

| Code | Process | Primary owner | Secondary owner |
|---|---|---|---|
| SMQ | Quality Management System (SMQ) | Maximilien Guerin | — |
| MKT | Marketing | Nathan Favereau-Forestier | — |
| SCS | Sales & Customer Service | Tristan Bolmont | — |
| PUR | Procurement | Alexandre Ringwald | — |
| MFG | Manufacturing | Alexandre Ringwald | — |
| IS | Information System | Alexandre Ringwald | — |
| LOG | Packaging & Shipping | Alexandre Trachsel | — |
| MNT | Maintenance | Alexandre Trachsel | — |
| RND | Research & Development | Matthieu Gevers | Nicolas Craquelin |

The primary owner is accountable for routing and closure quality. The secondary R&D owner shares process visibility and supports investigation; action owners may still be assigned separately on an individual Issue.

## Canonical Issue Types

### Quality Management System (SMQ)

- `Audit Nonconformity`: internal, customer or certification audit finding.
- `QMS / Procedure Nonconformity`: ineffective or uncontrolled procedure, record or management-system control.
- `Regulatory / Compliance Issue`: legal, regulatory, contractual-compliance or certification requirement.
- `Health, Safety & Environment Incident`: actual or potential HSE incident.
- `Continuous Improvement Opportunity`: cross-process weakness that does not belong more clearly to one operational process.

### Marketing

- `Website / Digital Marketing Issue`: website, form, SEO, analytics or marketing-channel problem.
- `Marketing Content / Brand Issue`: incorrect or inconsistent public-facing content or brand material.
- `Campaign / Event / Lead Generation Issue`: campaign, event, lead capture or marketing handover problem.

### Sales & Customer Service

- `Quotation / Pricing Issue`: quotation, selling price, discount, currency or commercial offer.
- `Sales Order / Commercial Terms Issue`: requirement capture, order entry, acknowledgement, scope or commercial commitment.
- `Customer Communication / Service Issue`: response, communication, support coordination or service follow-up.
- `Customer Complaint - Triage Pending`: temporary intake type until the process responsible for recurrence prevention is known.

### Procurement

- `Purchase Order / Purchasing Data Issue`: PO, quantity, price, specification, item or supplier data.
- `Supplier Delivery / Availability Issue`: delay, shortage, availability or delivery quantity.
- `Supplier Quality Nonconformity`: purchased material, component or external service does not conform.
- `Supplier Documentation / Certificate Issue`: missing or incorrect supplier certificate or record.
- `External Processing / Subcontracting Issue`: outsourced-process nonconformity or coordination failure.

### Manufacturing

- `Production Planning / Scheduling Issue`: production plan, capacity, readiness or work-order release.
- `Machining / Dimensional Nonconformity`: machined feature, tolerance, surface or dimension.
- `Assembly / Workmanship Nonconformity`: assembly, wiring, fastening, orientation or workmanship.
- `Electrical / Electronic Manufacturing Nonconformity`: PCB, component, cable or electrical production/workmanship defect.
- `Production Test / Inspection Failure`: production test, control plan, inspection or acceptance record.
- `Manufacturing Material / Traceability Issue`: material, batch, serial, BOM, route or traceability.
- `Production Process / Yield Issue`: instability, scrap, rework, bottleneck or yield loss.

### Information System

- `ERPNext / Business Application Issue`: ERPNext or other internal business application.
- `IT Access / User Account Issue`: role, permission, account, authentication or access.
- `IT Infrastructure / Device Issue`: computer, phone, network, printer, server or IT asset.
- `Data / Master Data Issue`: missing, duplicated, inconsistent or incorrectly governed business data.
- `Information Security / Data Protection Incident`: confidentiality, integrity, availability or personal-data incident.

### Packaging & Shipping

- `Packaging / Product Protection Issue`: packaging method, material or protection.
- `Picking / Quantity / Item Error`: wrong item, accessory, quantity or destination.
- `Labelling / Shipping Documentation Issue`: label, packing list, customs or transport document.
- `Shipment / Carrier / Delivery Issue`: dispatch, carrier, tracking, timing or delivery execution.
- `Transit Damage / Delivery Condition Issue`: damage, loss or unacceptable condition in transport.

### Maintenance

- `Equipment Breakdown`: production or test equipment cannot perform its function.
- `Preventive Maintenance Issue`: preventive maintenance is late, missed, ineffective or recorded incorrectly.
- `Tooling / Fixture Issue`: tool, jig, fixture, gauge or production aid.
- `Facility / Utility Issue`: building, power, compressed air, extraction, climate or facility utility.

### Research & Development

- `Mechanical Design / Product Issue`: mechanical behaviour, interface, fit, strength or design definition.
- `Fluidic / Performance Design Issue`: leakage, pressure, flow, pumping, valve behaviour or product performance.
- `Electrical / Electronic Design Issue`: architecture, PCB, selection, interface or electronic design.
- `Firmware / Embedded Software Issue`: firmware, embedded logic, protocol or device configuration.
- `Product Software / Integration Issue`: product driver, script, API or customer-facing integration.
- `Product Specification / R&D Documentation Issue`: specification, drawing, datasheet or released design record.
- `Product Reliability / Lifetime Issue`: wear, durability, lifetime or recurring field reliability.

## Smart Subject Suggestions

When an `Issue` or `AMF Issue Test` subject contains at least three characters, the form ranks up to three active Issue Types. Both doctypes use the same governed classifier and recommendation interface. A suggestion combines:

1. The governed Issue Type name, definition and AMF-specific vocabulary.
2. English, French and German normalization for common operational terms.
3. Aggregated vocabulary from classifications explicitly selected or applied by a user in either doctype. Imported and automatically migrated records are excluded from learning. Historical vocabulary starts contributing after three confirmed examples for a type, and the learning cache refreshes every 15 minutes.

The panel explains the matching signals and labels the match as `Strong`, `Good` or `Possible`. These labels are ranking guidance, not statistical probabilities. The feature never selects or changes an Issue Type automatically: the creator or process owner must click `Apply` and remains accountable for reviewing the classification. Inactive and legacy types are never suggested.

## Routing Process

1. The creator records the origin, facts and affected records, reviews the subject suggestions, and applies or manually selects the most precise active Issue Type.
2. ERPNext derives the process and its owner(s) from the Issue Type. These fields are read-only on the Issue.
3. If a customer complaint has no known responsible process, use `Customer Complaint - Triage Pending` temporarily.
4. The primary process owner confirms or corrects the type during triage. Product complaints must move from the temporary type to R&D, Manufacturing, Packaging & Shipping, Procurement or another responsible process once evidence identifies it.
5. The process owner makes sure containment, analysis, action ownership and due dates match the calculated priority.
6. The Issue Type may be corrected as evidence develops. Origin must not be changed merely because another process becomes responsible.
7. Closure records the outcome separately. `No Issue Found`, `Unable to Reproduce` and `Duplicate` never replace the problem-nature classification.

## Priority And Closure Expectations

- `P1 - Immediate Containment`: same-day ownership and containment; structured root-cause analysis is normally required.
- `P2 - Controlled Action`: named action owner and due date; root-cause analysis depends on recurrence, customer exposure and process risk.
- `P3 - Routine Follow-Up`: factual correction and normal follow-up; escalate if recurrence or hidden risk appears.

An Issue is ready for closure when the immediate effect is controlled, the actual outcome is recorded, required actions are completed, and the process owner can defend the classification and conclusion during an audit.

## Legacy Data

Legacy Issue Types are retained but marked inactive so closed records remain historically accurate. Open records with an unambiguous legacy mapping are moved to the corresponding canonical type. Retired choices are excluded from new Issue forms. The former `No issue found after analysis` type remains on historical records only and is replaced by the `Issue Outcome` field for new work.
