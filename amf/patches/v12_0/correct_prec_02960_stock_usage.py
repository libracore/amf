from __future__ import unicode_literals

from amf.amf.utils.prec_02960_correction import execute as run_correction


def execute():
	run_correction(dry_run=False, commit=False)
