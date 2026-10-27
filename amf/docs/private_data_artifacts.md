# Private CSV and JSON data

CSV/JSON inputs and generated BOM reports now live in **AMF Data Artifact**
database records. Runtime readers and writers do not use `docs`, application
`public`, site `public/files`, or `/assets` for this data. These database records
are included in the normal site database backup.

System Managers can create an artifact in Desk with a bare filename, such as
`selected-items-review-2.csv`, and paste UTF-8 CSV/JSON into Content. Use the
Download button to retrieve it through an authenticated endpoint. Downloads
require the System Manager role and DocType read permission and use attachment,
no-store, and nosniff response headers. The public asset tree remains suitable
for nonsensitive JavaScript, stylesheets and images.

The storage helper is `amf.amf.utils.data_artifact`. `put(name, content)` accepts
UTF-8 bytes or text and preserves the exact representation, including BOMs and
line endings. Names are identifiers of at most 140 characters, never paths or
URLs. Maximum content size is 16 MiB. SHA-256 and byte length are checked after
insertion and on every read. JSON must parse. Records are immutable: identical
imports can be retried, and changed content requires a new named version.

## Next migration

`migrate_private_data_artifacts_2026_10_26` is registered before the existing
selected-BOM repricing patch. It creates the DocType on every site. Only
`site1.local` receives the three reviewed manufacturing inputs from
`amf/patches/data/private_bom_inputs/`, verified against `manifest.json`.
The private seed directory is deployment input for the one-time migration;
it is never mounted into `/assets`. Existing matching database artifacts are
reused; missing, changed or conflicting inputs stop migration. Frappe owns the
transaction and Patch Log entry. The import does not write BOM costs.

The original reviewed proposal SHA-256 remains
`eacfc6fe2caaec05ef28988ea1ca0c902fa05ae7af90461d0983598093e54b26`.
The repricing patch retains its site scope, current-data comparison, paused
cost-writer checks, and explosion verification. A changed calculation still
requires a fresh review; the storage migration does not approve new costs.

Historical CSV/JSON exports already in `docs` are retained as local archives.
They are no longer runtime inputs, and are not imported automatically. New
reports are stored in the database.

## Tool arguments and transactions

The proposal tools return database artifact names instead of filesystem paths.
`selected_refs(name=...)`, `apply_scoped_proposal(proposal_name=...)`, and the
material repricing verification tools accept names of existing database records.
Do not pass `/docs/...` or an absolute path. `write_scoped_proposal()` and
`material_reprice.write_proposal()` generate unique proposal names by default;
an explicit `output_prefix` must be a bare prefix. Audit functions accepting
`output_path` now require a bare artifact filename; audit `namespace` arguments
are bare filename prefixes. Generated CSV values and proposal serialization
retain their existing financial precision.

The storage helpers never commit or roll back the caller's transaction. Normal
POST requests and `bench execute` commit on success. Patch execution commits
the imported inputs with its Patch Log entry. For manual Python console usage,
commit only after all outputs have been generated and checked.

The historical group-rollback tool still reads verified SQL backups for its
restore operation. Configure `amf_bom_original_database_backup` and
`amf_bom_pre_rollback_database_backup` in the site configuration when needed;
host-specific backup paths are no longer embedded in the code. Backup paths
must be outside the public files and asset trees.

## Invoice rate and shipping exports

All three item-rate exporters now return an authenticated database download URL
and require System Manager plus invoice read permission. They query invoice
history once, use a deterministic newest-first order, and keep each currency
separate. The CSV columns are `Item Code`, `Currency`, `Average`, then `Rate 1`,
`Rate 2`, etc. The single-customer variant still considers the full invoice
history when determining whether an Item was sold to exactly one customer.
`company_currency` filters company currency and exports base rates when supplied.
Explicit filenames are immutable artifact names; omit them for a unique name.
No exporter writes a publicly served file or commits unrelated database work.

DHL text attachments are now private File documents, require write permission
on their Delivery Note, and no longer create an intermediate file in `/tmp`.
There were no legacy item-rate CSVs or DHL text exports in the current site's
public files directory at the time of this change.
