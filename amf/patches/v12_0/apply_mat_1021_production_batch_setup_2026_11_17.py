from amf.patches.v12_0.repair_mat_1021_batch_chain_2026_11_17 import execute as repair_batch_chain


def execute():
    """Apply the MAT.1021 setup on production even if earlier site-limited patches ran.

    The shared repair validates the source receipt and stock movements, enables
    Item.has_batch_no, and links both source batches through their later usage.
    Repeated execution reuses existing batches. The patch runner commits the
    complete correction and records this new migration in Patch Log.
    """
    repair_batch_chain()
