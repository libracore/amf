"""Initialize MIC once on sites where AMF was installed before this feature."""


def execute():
    # v12 runs patches before model sync. Reload the feature's DocTypes first;
    # installation does not create checks, send mail, or enable the schedule.
    from amf.amf.utils.monthly_inventory import install_monthly_inventory

    install_monthly_inventory()
