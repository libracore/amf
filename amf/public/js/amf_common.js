// Set navbar to an obvious colour if running on dev machine:
if (window.location.host.indexOf("localhost") >= 0) {
    let link = document.createElement('link');
    link.type = 'text/css';
    link.rel = 'stylesheet';
    link.href = '/assets/amf/amf-dev.css';
    document.querySelector('head').appendChild(link);
}

/*  ***********************
 * This file contains common global functions 
 * 
 *  *********************** */

window.get_label = function(doctype, docname, print_format, label_reference) {
    window.open(
        frappe.urllib.get_full_url(
            "/api/method/amf.amf.utils.labels.download_label_for_doc"
            + "?doctype=" + encodeURIComponent(doctype)
            + "&docname=" + encodeURIComponent(docname)
            + "&print_format=" + encodeURIComponent(print_format)
            + "&label_reference=" + encodeURIComponent(label_reference)
        ),
        "_blank"
    );
}

function generateZPL(qrCodes) {
    const zplHeader = '^XA^POI^PW800^MNN^LL0000^XZ';
    const zplFooter = '^XZ';
    let zplContent = '';

    qrCodes.forEach((qrCode, index) => {
        zplContent += `^XA^FO50,${50 + (index * 300)}^BQN,2,10^FDLA,${qrCode.serial_number}^FS^XZ`;
    });

    return zplHeader + zplContent + zplFooter;
}