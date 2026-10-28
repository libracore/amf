# Acoustic Mixer migration and audit

Migration: `amf.patches.v12_0.create_acoustic_mixer_items_2026_10_28`, registered at the end of `amf/patches.txt`.

The next `bench --site <site> migrate` runs this patch. It validates existing matching records without rewriting them, or creates missing Product items `45D040-AM` and `46F055-AM`, Generic Item allocations `GX.RD-1000` and `GX.RD-1001`, and submitted active default BOMs with CHF 2,500 unit costs. Partial item creation can be resumed if the existing identities and allocation rates match. Conflicting references, item identities, draft/non-default BOMs, or costs stop the migration before inserts; the patch never overwrites those records.

The reviewed source BOM revisions are pinned to `BOM-45D040-011` and `BOM-46F055-009`, including their child BOM links and scrap recovery. New BOM material rates are refreshed through ERPNext's valuation lookup and the dedicated allocation fills the remaining amount to CHF 2,500. Already-created products are validated against their saved rates instead of being repriced. Sites without either source product are skipped.

Item and BOM document hooks remain active. A process-scoped exception permits only the exact planned project identities through the newer six-character Item code guard. The normal guard is restored afterward. Atomic creation suppresses parent-BOM propagation and legacy hook commits; the Frappe patch runner commits all changes and records completion in Patch Log. No stock or price transactions are created.

The existing Item QR hook requires the runtime's normal `pylibdmtx` native library dependency (`libdmtx`). This migration does not install system packages.

Validation performed on 28 October 2026:

- Eight focused unit tests passed, covering distinct allocations, non-stock costing behavior, identity conflicts, repeat execution, reviewed BOM revisions, scoped code exceptions, and hook failure propagation.
- Two complete replays against the existing production item/BOM records produced no document changes.
- Fresh creation under temporary item and reference codes created four items and two submitted CHF 2,500 BOMs. Repeating the migration created nothing further.
- The integration transaction was rolled back; temporary Items, BOMs, and attachments were removed. Source and real project records remained unchanged.

Run the unit tests from the bench root:

```sh
PYTHONPATH=apps/frappe:apps/erpnext:apps/amf env/bin/python -m unittest amf.patches.v12_0.test_create_acoustic_mixer_items_2026_10_28 -v
```

The following audit records the original creation. Quantities and group counts describe the site before the two new Product variants were added.

## Acoustic Mixer item and BOM audit

Date: 28 October 2026 (Europe/Zurich). Site: `site1.local`. Company: Advanced Microfluidics SA.

## Completed creation

Created the user-confirmed Product codes `45D040-AM` and `46F055-AM`. Each uses a dedicated submitted, active, default BOM, with output quantity 1 Nos, CHF currency, and valuation-based material costing.

| Product | Based on | Default BOM | Refreshed base cost CHF | Added costing item | Rate CHF / Nos | Final BOM CHF |
|---|---|---|---:|---|---:|---:|
| [45D040-AM](http://site1.local:8000/desk#Form/Item/45D040-AM) | 45D040 | [BOM-45D040-AM-001](http://site1.local:8000/desk#Form/BOM/BOM-45D040-AM-001) | 453.0213 | [GX.RD-1000](http://site1.local:8000/desk#Form/Item/GX.RD-1000) | 2046.9787 | 2,500.0000 |
| [46F055-AM](http://site1.local:8000/desk#Form/Item/46F055-AM) | 46F055 | [BOM-46F055-AM-001](http://site1.local:8000/desk#Form/BOM/BOM-46F055-AM-001) | 457.5114 | [GX.RD-1001](http://site1.local:8000/desk#Form/Item/GX.RD-1001) | 2042.4886 | 2,500.0000 |

Both Product item valuation rates and custom BOM cost snapshots are CHF 2,500.00. The cost items use the existing `Generic Item` group, Nos UOM, and non-stock costing settings. Each has quantity 1 in its dedicated product BOM and is excluded from physical material transfers. Their valuation rates differ because the source product costs differ. The existing generic production-service expense account `4400 - Cost of production services/materials (COGS) - AMF21` is used.

Product names and descriptions identify Acoustic Mixer. Unique reference codes are `P100O300040S1000P-AM` and `P101O300055S5000P-AM`. Internal descriptions document source items/BOMs, current components, scrap recovery, and the cost allocation. New QR attachments were generated for all four items. Historical demand, batch costing, purchase-rate history, and stock snapshots were cleared on the copies; source technical and accounting defaults were retained.

## Product group assessment

| Measure before creation | Value |
|---|---:|
| Total items | 2,142 |
| Enabled / disabled | 592 / 1,550 |
| Finished Good classification | 2,113 |
| Stock UOM Nos / stock items | 2,142 / 2,142 |
| Enabled items with a valid submitted, active, default BOM | 582 |
| Enabled items without a default BOM | 10 |

The predominant pattern is a manufactured, saleable Finished Good with HTML descriptions containing the product reference, body/version, valve configuration, materials, and syringe volume where relevant. Source products use SPM family and SPM STD line, with LV/HV variants. Their company defaults use Main Stock - AMF21, material expense account 4002, and SPM sales account 3002. Existing Product BOMs use no operations; among enabled items, 581 use Valuation Rate and one uses Last Purchase Rate. All linked enabled-item default BOMs are in CHF and belong to the correct item.

## Body group assessment

| Measure before creation | Value |
|---|---:|
| Total items | 46 |
| Enabled / disabled | 45 / 1 |
| Actuator classification / stock items / Nos UOM | 46 / 46 / 46 |
| Items using serial numbers | 25 |
| Enabled items with a valid submitted, active, default BOM | 41 |
| Enabled items without a default BOM | 4 |

Body descriptions commonly record Code, Reference, and Name. Bodies are typically manufactured Actuator assemblies. Serial tracking is common at the OEM body level, while neither source finished product uses serial or batch tracking. Enabled Body default BOMs use no operations; 36 use Valuation Rate and five use Last Purchase Rate. All linked enabled-item default BOMs are active, submitted, default, CHF, and attached to the correct item.

The focused Body items are `551000` (OEM SPM, reference P100-O) and `561000` (OEM SPM+, reference P101-O). Each BOM wraps a non-serialized body assembly (`550000` / `560000`) plus four SPL.3050 feet. Both retain serial tracking at the body level and SPM accounting defaults.

## Focused source item and BOM audit

| Source | Configuration | Current default BOM | Stored cost CHF |
|---|---|---|---:|
| 45D040 | P100-O; 1 mL syringe; V-D-1-12-050-C-P | BOM-45D040-011 | 453.0213 |
| 46F055 | P101-O; 5 mL syringe; V-D-1-12-050-C-P-HV | BOM-46F055-009 | 457.4983 |

Both configurations use a one-stage, 12-port distribution valve, 0.5 mm channels, PCTFE valve material and PTFE rotor material.

`45D040` contains 1 x 551000 Body, 1 x 70D000 syringe, 1 x 300040 valve head, and 2 x SPL.3028 screws. Its BOM recovers 1 x RVM.1204 adaptor as scrap with a CHF 1.00 credit. That recovery and credit were copied. New calculation: CHF 454.0213 materials + CHF 2,046.9787 project allocation - CHF 1.00 scrap = CHF 2,500.00.

`46F055` contains 1 x 561000 Body, 1 x 70F000 syringe, 1 x 300055 valve head, 2 x SPL.3052 screws, and 1 x RVM.1204 adaptor. It has no scrap rows. The current syringe valuation is CHF 46.3360 versus CHF 46.322857 on the source BOM. Refreshing only the new BOM produces a CHF 457.5114 base; adding CHF 2,042.4886 reaches CHF 2,500.00.

All 23 distinct nested source BOMs are active and submitted. Every component BOM link agrees with its Item default BOM. Historical BOM revisions were inspected: 45D040 has 11 revisions; 46F055 has nine, including one canceled revision. The duplication used the current default BOMs.

## Existing exceptions recorded for follow-up

No incorrect, inactive, unsubmitted, or non-default linked default BOMs were found among enabled Product and Body items. Items without a default BOM are listed below; these require business review to establish whether a BOM is expected.

- Product without a default BOM: `420085`, `420100`, `430068`, `4D1058`, `4D1062`, `4D1068`, `4D2058`, `4D2062`, `4D2068`, `CFR.1102`.
- Body without a default BOM: `5D0000`, `5D0001`, `5D0002`, `5D000A`.

Other observations from the focused records:

- The existing `46F055` custom BOM table was empty despite its default BOM link and stored cost. The new variant has a populated, synchronized snapshot.
- Body internal descriptions retain old item-code references: 551000 refers to 510000, and 561000 refers to 510100. The actual linked BOMs reference the correct current item codes.
- SPL.3028 has an Item master valuation of CHF 158.00, while its current inventory-derived valuation is approximately CHF 0.1581735. Standard ERPNext valuation lookup uses the latter at creation.
- The existing 46F055 QR field refers to an older 461055-named attachment. New variant QR files point to the new item records.

These existing records were audited and left unchanged.

## Validation and operational notes

- Passed a standard ERPNext cost refresh on each new submitted BOM; both remained exactly CHF 2,500.0000.
- Verified Product default BOM links, custom snapshots, valuation rates, component quantities, UOMs, child BOM links, technical attributes, and accounting defaults.
- Verified that both GX.RD items appear in their costing/exploded BOMs and are excluded from standard physical material lists.
- Verified no stock movements or item-price records were created for the new items.
- Verified original source Items, all 20 historical source BOMs, audited component Items/default BOMs, and all 23 nested BOM structures and costs remained unchanged.
- A separate read-only connection confirmed the committed records and totals.
- The item hook required libdmtx, which was missing from the execution environment. The official Debian package was downloaded and extracted under /tmp for this creation process; no system packages or application source files were changed.
- Each allocation is fixed at its creation rate. If component valuation costs change later, review the corresponding GX.RD rate to retain a CHF 2,500.00 BOM target.

No Acoustic Mixer Project record was found; no Project or production transaction was created.
