from amf.master_crm.feedback_vm import get_vm_previews

no_cache = 1
sitemap = 0


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = False
    context.title = "VM feedback testing | AMF"
    context.previews = get_vm_previews()
    return context
