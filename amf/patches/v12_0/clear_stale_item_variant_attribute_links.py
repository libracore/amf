from __future__ import unicode_literals

from amf.amf.utils.item_variant_cleanup import repair_stale_item_variant_attribute_links


def execute():
    repair_stale_item_variant_attribute_links()
