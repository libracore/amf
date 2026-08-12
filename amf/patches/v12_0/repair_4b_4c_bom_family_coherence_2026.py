from __future__ import unicode_literals

from amf.amf.utils.bom_family_coherence_2026 import repair_bom_family_coherence


def execute():
	repair_bom_family_coherence(dry_run=False, commit=True)
