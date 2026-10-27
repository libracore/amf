# Item Creation specification derived from the catalogue — 27 October 2026

This extends the [initial audit](item_creation_audit_2026-10-27.md) using a broader read-only evaluation of Items, Item Attributes, current BOMs, their material rows, and linked BOMs on `site1.local`.

The user confirmed these requirements after the initial audit:

1. Item code numbering is a priority limitation.
2. Derive the specifications from the existing Items and their relationships.
3. Submit new BOMs automatically when Item Creation is submitted. An existing BOM that disagrees with the intended definition requires a reviewed replacement.
4. Keep six-character identifiers and permit alphanumeric suffixes.
5. The final three characters must reliably identify the same head throughout its chain. Allocate a new suffix only after verifying its availability across every relevant Product, head, sub-assembly, and single component, including `10_ABC` and `20_ABC`.

The shared-suffix allocation contract below incorporates those requirements. Its [implementation record](item_creation_algorithm_implementation_2026-10-27.md) describes the completed local code update, verification and remaining audit scope. Historical business records were not repaired or renamed.

The later [engineering workflow implementation](item_creation_engineering_workflow_2026-10-27.md) adds complete reviewed plans, explicit standard compatibility rules, raw-material BOMs and the guided form. The [improvement tracker](item_creation_improvements.md) contains the current completion/deployment status. Catalogue observations below remain evidence, including historical exceptions and designs outside the supported generator matrix.

## Evidence and its interpretation

The extraction contains **2,649 Items**, **2,443 relevant BOM headers**, **11,967 material rows**, **226 scrap rows**, **144 Item Attribute values**, and the referenced component Items and child BOM headers. Disabled and legacy records are retained as evidence of existing identifiers and historical designs.

There are **591 enabled Products**, of which **582** have an active submitted BOM selected by their own `Item.default_bom` pointer. These 582 products supply the observed compatibility table. This validates the selected header relationship; it does not certify every material row as correct. Across the broader inspected enabled-Item default BOMs, 104 material rows have stock-UOM differences against their current Item master, and 17 consume disabled Items.

The nine enabled Products without an active submitted selected default are `420100`, `430068`, `4D1058`, `4D1062`, `4D1068`, `4D2058`, `4D2062`, `4D2068`, and `CFR.1102`. The six 4D interface BOMs are the explicitly pending records described by the existing migration. Their existence supplies no permission to generate those pending BOMs.

Evidence tables:

- [582 product/BOM relationships](item_creation_catalogue_relationships_2026-10-27.csv), including disabled-component and reference/head discrepancy flags.
- [44 observed prefix/body/syringe combinations](item_creation_observed_combinations_2026-10-27.csv).
- [15 concrete code collision cases](item_creation_numbering_collisions_2026-10-27.csv): 14 existing-head cases and one next-suggested-family case.
- [390 occupied shared suffixes](item_creation_shared_suffix_occupancy_2026-10-27.csv), including disabled and slash-prefixed retired identifiers.

Repeated current patterns support defaults and suggestions. Contradictory records enter review. An unobserved combination needs an explicit recipe definition or a reviewed template; its absence from the table alone does not establish physical incompatibility.

## Numbering: the immediate failure and the underlying rule

The original family allocator's next suffix in this snapshot was **0085**. All five component/head family codes for that suffix were unused. Its proposed head was consequently **300085**.

The current product formula would assign its fast RVM product **420085**. That code already belongs to:

| Field | Existing value |
| --- | --- |
| Product | `420085` |
| Reference | `P201O300033AIR` |
| Body | `521004`, OEM RVMFS-AIR |
| Head | `300033` |
| Default BOM | `BOM-420085-004` |

Thus the first available family suffix can collide with a current Product immediately. The current creation helper would accept the existing product by code without comparing its identity and then attempt to create a new default BOM for it.

Additional examples include generating `420049` for head `300049`, although that Product uses head `300033` and RS485 body `521002`; and generating `420138` for standard body `521000`, although its current recipe uses RS485 body `521002` with the same head `300138`.

Of the 582 products, 581 contain exactly one Valve Head. **37** of those have a three-character product suffix that differs from the actual head suffix. They conflict with the confirmed shared-suffix requirement and belong in the review list. The intended correction must be reviewed against the design and recipe before changing identifiers or replacing BOMs.

The catalogue currently contains these identifier concepts and deviations:

| Pattern | Observed meaning and limits |
| --- | --- |
| `10ssss` / `11ssss` | Numeric machined plug and its sub-assembly. |
| `20ssss` / `21ssss` | Numeric machined seat and its sub-assembly. Special seat identifiers such as `20C001` exist separately. |
| `30ssss` | Numeric Valve Head. Head suffixes currently extend to `0138`. |
| `4fvsss`: `4` + family + variant + shared head suffix | The final three characters must identify the head. Existing mismatches require review; new allocation must preserve this invariant. |
| `4D0xxx`, `4D1xxx`, `4D2xxx` | Mini RVM base, RS485, and CAN namespaces. The third character identifies an interface here. |
| `4D004D`, `4D104D`, `4D204D` | Existing alphanumeric examples using head `300042`. Their `04D` suffix is occupied globally and their head relationship requires review under the confirmed rule. |
| Leading `/`, or extra suffixes such as `-P` | Existing historical/custom identifiers. Preserve their identities and explicit variant meaning. |

There are also **six groups of two enabled Products** sharing the same body/head/syringe tuple but carrying different references/configurations. Examples are `420082` versus `420083`, whose references distinguish I2C address 2 and 3 on the same LPH body/head, and `420041` versus `420086`, whose references distinguish the MTY configuration.

Product configuration requires **body + head + optional syringe + configuration**, including interface/control/customer options where applicable. The final three characters identify the head; the preceding characters distinguish the product family/variant. Different configurations for one head must retain its suffix and use an explicitly defined variant prefix. They cannot take another head's suffix to obtain a free Product code.

## Confirmed numbering contract

Use one shared three-character suffix, `ABC`, for a newly allocated head family. Codes remain six characters. Normal new codes take forms such as:

| Layer | Example code |
| --- | --- |
| Plug component | `100ABC` |
| Plug sub-assembly | `110ABC` |
| Seat component | `200ABC` |
| Seat sub-assembly | `210ABC` |
| Valve Head | `300ABC` |
| RVM product | `420ABC` |
| Pump product | `452ABC` |
| HV pump product | `46EABC` |
| Mini RVM interfaces | `4D0ABC`, `4D1ABC`, `4D2ABC` |

The underscore in the user's `10_ABC`/`20_ABC` notation represents another code character. Occupancy checks must consider all values of that character, so an existing `101ABC` or `20CABC` also blocks allocation of `ABC`. The same applies to every Product family and variant prefix. Searching only `100ABC`, `200ABC`, `300ABC`, or only the selected product checkboxes is insufficient.

1. Collect occupied suffixes from the complete relevant chain: `10…`, `11…`, `20…`, `21…`, `30…`, and Product codes, across all variants. Compare the final three characters of the canonical six-character identifier.
2. Include enabled, disabled, and known retired identifiers. For example, `/48E113` reserves `113`; a legacy variant such as `4D0006-P` reserves the base suffix `006`. Raw-material, stock-body, syringe and general-accessory codes are separate identifier systems and do not allocate a head-family suffix.
3. Reject a candidate if any relevant code uses it. This reserves the whole family even if only a component or one historical Product currently exists. Do not fill another part of an occupied family while claiming to allocate a new family.
4. Search numeric suffixes `001`–`999` first for continuity, then unoccupied uppercase alphanumeric tokens in a deterministic order. Use `0–9` and `A–Z`, retaining leading zeroes. Keep `000` reserved. This gives **46,655 possible head-family suffixes globally**, before existing reservations. This is a defined new allocation order, not a reinterpretation of historical tokens.
5. Reserve the chosen suffix once for the whole source request before creating any Item. Persist ownership and use a unique suffix constraint with transactional locking/retry handling so concurrent requests cannot allocate the same family. Revalidate the complete occupied/reserved set at execution; a displayed suggestion alone is insufficient.
6. Generate every planned family code with that exact suffix. For an existing head, keep its established suffix and validate that it identifies the intended family. If a Product code is occupied by another configuration, require review or a defined free variant prefix for the same head; never choose an unrelated suffix as a fallback.
7. Continuing an existing family is a separate operation from allocating a fresh family. Reusing an existing component/sub-assembly must verify family/head ownership, actual recipe and material identity. A matching material tag alone cannot authorize joining unrelated suffix families.
8. Treat existing suffix/head and cross-layer mismatches as review cases. Keep proposed identifier/recipe corrections explicit; do not use legacy mismatches as templates for newly generated numbering.

### Catalogue result under this rule

The snapshot contains **390 occupied suffixes** across the relevant chain: 389 numeric and one alphanumeric (`04D`). With numeric-first search, the next available suffix is **117**, giving `100117`, `110117`, `200117`, `210117`, `300117`, and Products such as `420117`/`46E117`.

The old component-only candidates `085`, `086`, `087`, `089` and `091` are blocked by existing Products. Suffix `113` is also blocked by both current and retired codes. Suffix `121` remains blocked by retired `/460121`, `/461121`, `/470121`, and `/471121` records. All are rejected before any Item is created.

The first eight available numeric suffixes in this snapshot are `117`, `118`, `119`, `122`, `123`, `125`, `127`, and `128`. Execution must repeat the check against the then-current database and persistent reservations.

## Numbering consumers that must follow the same contract

| Consumer | Current dependency | Required behavior |
| --- | --- | --- |
| Item Creation | Suggests a four-digit component-family gap without checking Product suffix occupancy. | Allocate and reserve the shared final three characters across the complete chain; derive every new code from that suffix. |
| [Quotation product definition](../amf/utils/quotation_product_definition.py) | `make_fallback_item_code()` recreates the same code formula; a matching fallback code can be accepted without checking the requested configuration. `get_base_reference()` also discards body reference details after a dot. | Resolve the full configuration and its actual recipe. Prevent a fallback from returning an unrelated product. Preserve interface/control distinctions. |
| [Pump BOM updating](../amf/utils/bom_updating_for_pump.py) | Reconstructs a head as `300` + product suffix, then attempts reference-based recovery. | Validate the shared suffix against the actual selected head and recipe; flag legacy violations for review instead of silently selecting another head. |
| 4D migration helpers | Existing mappings include `04D` and named interface variants; older migration fallback derives a `420` candidate from a head suffix. | Preserve the reviewed migration mappings and pending records. Historical mappings are compatibility requirements. |
| Product costing/report filters | Some use `^4[0-9]{5}$`; they already exclude alphanumeric families such as `4A`, `4B`, `4C`, and `4D`. | Share a valid alphanumeric Product classification and cover the common suffix with existing/new code regression cases. |
| Machining/batch/drawing consumers | Many explicitly identify numeric six-character `10`/`20` parts. | Support the alphanumeric suffix at component layers too; `100ABC` must retain machining, batch and drawing behavior. Update consumers alongside the allocator. |

Changing only the Item Creation generator would leave Quotation resolution capable of returning the wrong product. The numbering work must include the shared resolver and its callers.

An isolated execution of the current Quotation resolver with catalogue-backed mocked lookups confirmed this behavior: selecting body `521000` with head `300049` returns `420049`, reference `P201O300033RS485`. Selecting the same body with head `300081` returns `420081`, reference `P201O300036I2C1LPH`. Even a reference match needs recipe validation: `420138` has reference `P201O300138` but actually uses RS485 body `521002`.

## Product families and observed combinations

Counts below include enabled Products with selected active submitted default headers; material-row defects remain flagged separately.

| Product family | Body Items observed | Syringes observed | Products |
| --- | --- | --- | ---: |
| `41`, P200-O | `511000` | None | 51 |
| `42`, P201-O and configurations | `521000` through `521006` | None | 82 |
| `43`, P211-O variants | `531000` and `521101` | None | 10 |
| `4D`, P202-O base/RS485/CAN | `5D1000`, `5D1001`, `5D1002` | None | 109 |
| `45`, P100-O | `551000` | 50, 100, 250, 500, 1000 µL PTFE | 91 |
| `47`, P100-L | `571000` | Same five | 20 |
| `49`, P110-O HD | `591000` | Same five | 95 |
| `4B`, P110-L HD | `5B1000` | Same five | 20 |
| `46`, P101-O HV | `561000` | 2500, 5000 µL PTFE | 35 |
| `48`, P101-L HV | `581000` | Same two | 16 |
| `4A`, P111-O HD HV | `5A1000` | Same two | 34 |
| `4C`, P111-L HD HV | `5C1000` | Same two | 16 |
| Other current designs | `S1…`, `UF…`, `4X…` special products | Design-specific | 3 |
| **Total** | | | **582** |

The standard syringe codes are `702000`, `703000`, `705000`, `708000`, `70D000`; their namespace tokens are `2`, `3`, `5`, `8`, `D`. High-volume syringe codes are `70E000` and `70F000`, with tokens `E` and `F`.

Syringes `704000` and `709000` are enabled component Items, but each is referenced by 100 disabled Product default recipes and by no enabled Product current default recipe in this extraction. The current wizard blindly includes both in its low-volume cross-product. Their component availability is insufficient evidence to reactivate those product combinations.

The 25 µL, quartz, borosilicate, and UFM syringes also have catalogue records; their presence needs a supported product recipe before generic wizard generation.

### Head and volume compatibility

- **226** low-volume products use **21 distinct heads**, all without an HV marker. One of those observed heads, `300058`, is currently disabled, so it is ineligible for new creation despite the existing product recipes.
- **101** high-volume products use **18 distinct heads**, all explicitly carrying `-HV` in their names.
- Most pump heads are distribution type D. DS designs also occur in selected OEM recipes. A type-only rule would lose geometry and approved-design distinctions.
- The RVM catalogue includes D, DS, O, S, B, DA, SA, SL, T, and special designs. Body/protocol options and head design must be resolved together.
- An enabled `541000` body exists, but the observed catalogue supplies no enabled `44…` product family; it appears in a separate `S1…` design. Do not infer generic `44…` support solely from body availability.

Use the observed combinations for suggestions and template search. Validate the actual head, body, syringe and recipe at submission. New configurations outside the established table should carry a reviewed recipe definition.

## Names and material specifications

The common head format is:

`VALVE HEAD-{type}-{stages}-{ports}-{channel expression}-{seat material}-{plug material}[-HV][customer/design suffix]`

Its usual R&D form starts `V-`. Components normally start `SEAT-` and `PLUG-`; their references can instead be design identifiers such as `DBM.1031-P` and `.ASM` variants. Parse the display name and reference as separate fields.

Stored Item Attributes and current Items establish:

- Plug material `P`: PTFE; `U`: UHMW-PE; `PFG`: PTFE Food Grade.
- Valve/seat material `C`: PCTFE; `P`: PTFE; `K`: PEEK; `A`: PMMA. The stored Valve Material attribute assigns `U` to PEI, while the Plug Material meaning of `U` remains UHMW-PE. A shared global abbreviation map is insufficient.
- Channels include `025`, `050`, `075`, `080`, `100`, `120`, `160`, `200`, `240`, and compound values such as `200+400` and `240+400`. Attributes also use slash-separated channel expressions. Format each channel dimension separately in millimetres.
- Reference/type vocabulary includes additional current design tokens such as `OS`, `SPE`, `SPLIT`, `SPLITS`, and `DSPLIT`; the smaller Item Attribute type list is incomplete for the current catalogue.
- Preserve customer/connection suffixes such as `BR`, `MGA`, `SPARE`, `10/32UNF`, and HV combinations. They can distinguish design/configuration identity.

Names such as `300068` (`DSPLIT` with additional geometry), `300084` (SHV without a normal plug token), `300093` (vacuum special), and `300095` (`12_4`) need a custom-design path. A fixed-position parser must return a reviewable custom definition rather than guess missing geometry.

The catalogue has multiple raw-material rods per tag, differing in diameter, material grade, and supplier. PTFE has seven enabled tagged candidates, PCTFE eight, PEEK three, PMMA one, and UHMW-PE one. Ten further enabled Raw Material Items are untagged. A material tag alone cannot choose the correct manufacturing stock.

## Recipe rules and their exceptions

| Layer | Repeated catalogue evidence | Creation rule |
| --- | --- | --- |
| Machined plug | Typically a raw-material rod with 0.02 Meter input; actual exceptions include different lengths/UOMs. | Suggest from a matching reviewed design/material stock. Validate quantity, BOM output quantity, conversion, and current stock UOM. |
| Machined seat | Typically 0.03 Meter rod input, with diameter/grade-dependent stock choices and custom exceptions. | Same validation; require the correct stock Item rather than choosing the most frequent tag match. |
| Plug sub-assembly | Corresponding component plus `SPL.3013` magnets. Of 62 current recipes with a parseable port count and magnet row, 55 match ports and seven differ. | Ports can suggest a count. Existing reviewed geometry/recipe or an explicit reviewed quantity determines it. |
| Seat sub-assembly | Two `SPL.3039` pins are common, but other pins, four pins, additional adapters, and recipes without a pin row occur. | Use a reviewed recipe/template; the existing fixed two-pin setting is insufficient for all designs. |
| Head | Commonly plug and seat sub-assemblies; direct component use and custom plug designs also occur. | Compare the intended definition against actual component identities and show a replacement diff when they disagree. |
| RVM | Body/head plus design-specific screws and cap. | Prefer an exact compatible recipe/template. Common screw/cap patterns are suggestions. |
| Low-volume pump | Body/head/syringe plus two `SPL.3028`; all 226 observed LV recipes list one `RVM.1204` as scrap. Laboratory recipes also include `C100`, `C101`, and `T100`. | Carry the accessory and scrap structure from the reviewed recipe. The current wizard omits `T100` from new laboratory LV products. |
| High-volume pump | `RVM.1204` is a positive consumed material in all 101 observed HV recipes, with two design-specific screws. Laboratory variants include `C100`/`C101`; a few recipes have other accessories. | Include the adapter and actual screw type/count. Fixing only the screw field name would still leave the adapter missing from the current HV builder. |

Magnet-count exceptions include `110005` (two ports/four magnets), `110024` (eight ports/four magnets), `110060` (two ports/six magnets), and `110134` (20 ports/ten magnets). These differences must remain visible during recipe review.

Some disabled historical HV products carry the adapter with negative stock quantity/conversion, for example `46E040`. They are historical credit representations and must not be mistaken for the current enabled HV consumption rule. The broader extraction supersedes the initial audit's limited observation of that one disabled product.

### Concrete reviewed-replacement case: head 300135

Current head `300135` is `VALVE HEAD-SPE-1-4-160-P-P`, reference `DBM.1032`, default `BOM-300135-002`.

- It uses plug sub-assembly `110060`, named `PLUG-V-2-2-160-P`, with six magnets in its own BOM.
- Neither `100135` nor `110135` exists. A generated replacement cannot simply point to a supposedly matching suffix.
- Its seat sub-assembly `210135` is named `SEAT-SPE-1-4-160-P`, while the underlying `200135` component is named `SEAT-SPE-2-5-160-P`, reference `DBM.1031-P`.

This requires a concrete reviewed component/design selection. Deriving another plug from the head name alone would invent the engineering decision. The replacement view should show the existing definition, proposed Items/materials/accessories, missing records, and downstream parent impact before the source request is submitted.

Five additional Product references mention head `300063` while their current BOM uses `300052`: `410063`, `420063`, `4D0063`, `4D1063`, and `4D2063`. These are discrepancy candidates for review; the audit does not establish which side is the intended design.

## Lifecycle required by the user's decisions

1. Generate a read-only plan with proposed codes, explicit configuration, complete recipes and any existing-BOM diff.
2. A disagreement or ambiguous/custom definition requires a recorded review of the proposed replacement. The plan must identify the exact existing BOM version being reviewed.
3. Revalidate the reviewed definition, dependencies, existing BOM version and code allocation when submitting Item Creation. If they changed, return the request for review.
4. Submission automatically creates and submits the reviewed new BOMs, in dependency order and within the owning transaction.
5. Existing submitted BOMs remain as historical revisions. Parent BOM propagation requires an explicit reviewed plan; saving a draft replacement must not rewrite parents.
6. Record created/reused Item/BOM identifiers and review provenance. Retrying must return the existing outcome for the same source request.

Existing System Manager access can be retained while the workflow is implemented; the audit does not propose granting new roles. Existing valuation fields, paused cost controls, retired Items, and the six explicitly pending 4D BOMs remain outside automatic repair.

## Implementation readiness

The catalogue and the user's clarifications now specify a global shared three-character suffix, fixed six-character alphanumeric codes, automatic new-BOM submission, and reviewed replacements for existing disagreements. The evidence also establishes the observed family/variant matrix, ordinary name grammar, material contexts, and review boundaries.

The implemented numbering work covers complete family planning before writes, the blocked `085` case, the currently free `117` case, reservations/concurrency, Quotation configuration validation, and alphanumeric suffix handling across the affected component/production consumers. Existing disagreements block creation pending reviewed replacement. The broader engineering review/template interface and compatibility rules remain separate audit work. Historical inconsistencies require explicit review and must not weaken the invariant for new creation.

Reproduction inputs/tools are `/tmp/item_creation_catalogue_readonly.py`, `/tmp/item_creation_catalogue_2026-10-27.json`, and `/tmp/item_creation_catalogue_analysis.py`. All database work used a database-enforced read-only transaction followed by rollback. Generated CSV counts reconcile to the extracted current product relationships.
