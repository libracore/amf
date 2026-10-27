"""Install the reviewed Item Creation workflow and alphanumeric form metadata."""


def execute():
    from amf.amf.utils.item_creation_workflow import sync_item_creation_schema
    from amf.amf.utils.work_order_estimated_time import sync_work_order_estimated_time_custom_fields

    # v12 executes patches before model sync. Load the child tables before the
    # parent form, including its full-width configuration section.
    sync_item_creation_schema()
    sync_work_order_estimated_time_custom_fields()
