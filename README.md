## AMF

ERP applications and tools for AMF

### Monthly Operations AI Insights

The monthly `Operations KPI Report` can enrich its deterministic KPI snapshot
with bilingual, evidence-backed OpenAI insights.

Configuration:

1. Install `requirements.txt` and run `bench --site <site> migrate`.
2. Enter the API key in the Single `Operations KPI Report Settings` DocType.
   AMF encrypts it with the site's encryption key into a Long Text field,
   avoiding Frappe v12's short `__Auth.password` column. The key is never
   displayed again after saving. `OPENAI_API_KEY` remains an optional
   deployment fallback.
3. Enable `AI Insights`, select the model and confidence threshold, and keep
   `Require Human Approval` enabled for controlled distribution. Each report
   has an editable `Generate AI Insights` checkbox, enabled by default.
4. Generate a monthly or semester report. Validated AI output is stored on the report
   for review but is excluded from files and email until approved.

The KPI calculations remain authoritative. The AI receives a bounded snapshot,
external parties and transaction identifiers are aliased by default, API
storage is disabled with `store=False`, Issue root-cause free text is excluded
unless explicitly enabled, and every retained insight must cite a real
leaf-level source path. Evidence values are replaced server-side with the
canonical values from the snapshot before storage.

The read-only investigation methods in
`amf.amf.utils.operations_ai_tools` expose bounded OTIF, shortfall, machining
scrap, shipping issue and procurement exception details. They do not provide
SQL execution, document mutation, email or other outbound actions.

#### License

AGPL
