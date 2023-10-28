// Set navbar to an obvious colour if running on dev machine:
if (window.location.host.indexOf("localhost") >= 0) {
    let link = document.createElement('link');
    link.type = 'text/css';
    link.rel = 'stylesheet';
    link.href = '/assets/amf/amf-dev.css';
    document.querySelector('head').appendChild(link);
}

if (window.location.host.indexOf("amf") >= 0) {
    let link = document.createElement('link');
    link.type = 'text/css';
    link.rel = 'stylesheet';
    link.href = '/assets/amf/amf.css';
    document.querySelector('head').appendChild(link);
}

window.onload = async function () {
    console.log("Welcome to AMF ERP");
    setTimeout(function() {
        var navbars = document.getElementsByClassName("navbar");
        if (navbars.length > 0) {
            if (window.location.hostname.includes("amf")) {
                navbars[0].style.backgroundColor = "#2b47d9";
                navbars[0].style.borderColor = "#2b47d9";
            }
        }
        var navlogo = document.getElementsByClassName("app-logo");
        if (navlogo.length > 0) {
            if (window.location.hostname.includes("amf")) {
                navlogo[0].src = "https://amf.libracore.ch/files/AMF2023.png";
                //navlogo[0].style.width = "45px";  // Change width to 45px
                navlogo[0].style.marginTop = "0";
                navlogo[0].setAttribute('style', 'width: 50px !important');
            }
        }
        var navsearch = document.getElementById("navbar-search");
        navsearch.style.backgroundColor = "#0022ce";
        navsearch.style.borderColor = "#0022ce";
    }, 500);
}

/*  ***********************
 * This file contains common global functions 
 * 
 *  *********************** */

function get_label(doctype, docname, print_format, label_reference) {
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
//amf.utils.get_label = get_label;

function generateZPL(qrCodes) {
    const zplHeader = '^XA^POI^PW800^MNN^LL0000^XZ';
    const zplFooter = '^XZ';
    let zplContent = '';

    qrCodes.forEach((qrCode, index) => {
        zplContent += `^XA^FO50,${50 + (index * 300)}^BQN,2,10^FDLA,${qrCode.serial_number}^FS^XZ`;
    });

    return zplHeader + zplContent + zplFooter;
}
