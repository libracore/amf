frappe.ui.form.on("AMF Data Artifact", {
    refresh: function (frm) {
        frm.set_df_property("content", "read_only", !frm.is_new());
        if (!frm.is_new()) {
            frm.add_custom_button(__("Download"), function () {
                window.location.href = "/api/method/amf.amf.utils.data_artifact.download?name=" +
                    encodeURIComponent(frm.doc.name);
            });
        }
    }
});
