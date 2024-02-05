/* Global Variables */
const tableId = "myTable";
const planningListURL = 'https://amf.libracore.ch/desk#List/Planning/List';
const amfLogoURL = "https://amf.libracore.ch/files/Logo AMF Tagline WHITE.png";
const drawingBaseURL = 'https://amf.libracore.ch/desk#Form/Work%20Order/';
const driveURL = 'https://drive.google.com/drive/folders/1H6Eorf1nxAfNCES30Gzg5i0KG1r1CxO6?usp=sharing';
const statusColors = {
    'QC': '#b3ecec',
    // ... other statuses ...
    'Planned #5': '#F7DDDB',
};

/* Onload Function for General Display */
window.onload = function () {
    // document.querySelector("nav").style.display = 'none';
    document.querySelector("footer").style.display = 'none';
    document.getElementsByClassName("nav-link")[0].textContent = 'Planification';
    document.getElementsByClassName("nav-link")[0].removeAttribute('href');
    document.getElementsByClassName("dropdown-toggle")[0].removeChild(document.getElementsByClassName("caret")[0]);
    var navlogo = document.getElementsByClassName("navbar-brand");
    if (navlogo.length > 0)
        if (window.location.hostname.includes("amf"))
            navlogo[0].children[0].firstChild.src = "https://amf.libracore.ch/files/AMF2023-Full.png";

    const today = new Date().toISOString().split('T')[0];
    document.getElementById("plannedForInput").setAttribute("min", today);
    document.getElementById("createdOnInput").setAttribute("min", today); // If needed
    document.getElementById("createdOnInput").value = today;
};

function statusBackgroundColor() {
    var table = document.getElementById('myTable');
    var rows = table.getElementsByTagName('tr');

    for (var i = 1; i < rows.length; i++) { // Start from 1 to skip the header row
        var statusCell = rows[i].getElementsByTagName('td')[1]; // Status is in the second cell (index 1)
        var status = statusCell.textContent || statusCell.innerText;

        switch (status) {
            case 'QC':
                rows[i].style.backgroundColor = '#b3ecec'; // Change to desired color
                rows[i].style.color = '#000000';
                break;
            case 'Free':
                rows[i].style.backgroundColor = '#999999'; // Change to desired color
                break;
            case 'Reserved':
                rows[i].style.backgroundColor = '#777777'; // Change to desired color
                break;
            case 'On Hold':
                rows[i].style.backgroundColor = '#555555'; // Change to desired color
                break;
            case 'Cancelled':
                rows[i].style.backgroundColor = ''; // Change to desired color
                break;
            case 'Fab':
                rows[i].style.backgroundColor = '#50C878'; // Change to desired color
                rows[i].style.fontWeight = 'bold';
                break;
            case 'Done':
                rows[i].style.backgroundColor = ''; // Change to desired color
                break;
            case 'Rework':
                rows[i].style.backgroundColor = '#FFA756'; // Change to desired color
                break;
            case 'Planned #1':
                rows[i].style.backgroundColor = '#D9544D'; // Change to desired color
                break;
            case 'Planned #2':
                rows[i].style.backgroundColor = '#E17771'; // Change to desired color
                break;
            case 'Planned #3':
                rows[i].style.backgroundColor = '#E89994'; // Change to desired color
                break;
            case 'Planned #4':
                rows[i].style.backgroundColor = '#F0BBB8'; // Change to desired color
                break;
            case 'Planned #5':
                rows[i].style.backgroundColor = '#F7DDDB'; // Change to desired color
                break;
            default:
                rows[i].style.backgroundColor = ''; // Optional default color
        }
    }
}

function sortTable(columnIndex) {
    var table, rows, switching, i, x, y, shouldSwitch;
    table = document.getElementById("myTable");
    switching = true;
    // Continue looping until no switching has been done:
    while (switching) {
        switching = false;
        rows = table.rows;
        // Loop through all table rows (except the headers):
        for (i = 1; i < (rows.length - 1); i++) {
            shouldSwitch = false;
            // Get the two elements to compare, one from current row and one from the next:
            x = rows[i].getElementsByTagName("TD")[columnIndex];
            y = rows[i + 1].getElementsByTagName("TD")[columnIndex];
            // Check if the two rows should switch place, after converting them to integers:
            if (parseInt(x.innerHTML) > parseInt(y.innerHTML)) {
                shouldSwitch = true;
                break;
            }
        }
        if (shouldSwitch) {
            // If a switch has been marked, make the switch and mark that a switch has been done:
            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
            switching = true;
        }
    }
}

/* Ready Function for General Display w/ Fetch&Display Planning List */
$(document).ready(function () {
    console.log("Getting the doc ready...");

    document.getElementById('planningList').addEventListener('click', function () {
        window.open('https://amf.libracore.ch/desk#List/Planning/List', '_blank');
    });

    if (frappe.session.user != 'Guest') {
        frappe.call('frappe.client.get_value', {
            doctype: 'User',
            filters: {
                name: frappe.session.user
            },
            fieldname: 'email',
        }).then(r => {
            let user_email = r.message.email;
            //document.getElementById('login-button').innerHTML = user_email;
            //document.getElementById('login-button').href = "/desk";
        });
    }
    fetchAndDisplayDocuments();
});

/* General Display Function */
function fetchAndDisplayDocuments() {
    frappe.call({
        method: 'amf.www.planification.planification.get_planning_list',
        args: {},
        callback: function (response) {
            var documents = response.message;
            for (var i = 0; i < documents.length; i++) {
                var document = documents[i];
                addRowToTable(document);
            }
        }
    });
    console.log("Called Fetch & Display Planning DocType");
}

/* General Function Adding Row to Table */
function addRowToTable(doc) {
    const table = document.getElementById("myTable");
    const row = table.insertRow(-1);

    // Add checkbox cell
    const checkboxCell = row.insertCell(0);
    checkboxCell.innerHTML = '<input type="checkbox" class="row-selector">';

    // Define keys and special handling for them
    const keys = [
        { key: 'status', special: false },
        { key: 'work_order', special: true, link: 'https://amf.libracore.ch/desk#Form/Work%20Order/', textKey: 'name' },
        { key: 'qty', special: false },
        { key: 'item', special: false },
        { key: 'project', special: false },
        { key: 'who', special: false },
        { key: 'created_on', special: false },
        { key: 'planned_for', special: false },
        { key: 'end_date', special: false },
        { key: 'delivered_qty', special: false },
        { key: 'material', special: false },
        { key: 'drawing', special: true, link: '', textKey: 'drawing', textStart: 0, textEnd: 20 },
        { key: 'program', special: false },
        { key: 'comments', special: false },
        { key: 'filter', special: true, style: 'display:none;' }
    ];

    // Loop through keys to populate cells
    keys.forEach(({ key, special, link, style, textKey, textStart, textEnd }) => {
        const cell = row.insertCell(-1);
        if (doc[key] || doc[textKey]) {
            if (special) {
                if (link && doc[key]) {
                    cell.innerHTML = `<a href="${link + doc[key]}" class="constrained-link">${doc[textKey] || doc[key]}</a>`;
                } else if (link && doc[textKey]) {
                    cell.innerHTML = doc[textKey];
                } else if (style) {
                    cell.innerHTML = doc[key];
                    cell.style.display = 'none';
                } else {
                    cell.innerHTML = `<a href="${doc[key]}" class="constrained-link">${doc[key].substring(textStart, textEnd)}</a>`;
                }
            } else {
                cell.innerHTML = doc[key];
            }
        } else {
            cell.innerHTML = "";
        }
    });

    statusBackgroundColor();
    sortTable(15);
}

/* General Function to Handle Table Events */
document.getElementById("myTable").addEventListener("click", function (e) {
    console.log("Row clicked...");
    // Check if a checkbox was clicked
    if (e.target.matches('.row-selector')) {
        handleCheckboxClick(e.target);
    } else {
        // Otherwise, handle the row click
        var tr = e.target.closest('tr');
        if (tr) {
            handleRowClick(tr);
        }
    }
});

function openLink() {
    window.open('https://drive.google.com/drive/folders/1H6Eorf1nxAfNCES30Gzg5i0KG1r1CxO6?usp=sharing', '_blank');
}

/* Sub Function to Handle Table Events Checkbox Click */
function handleCheckboxClick(checkbox) {
    var tr = checkbox.closest('tr');
    if (checkbox.checked) {
        // Add selected class to the row when checked
        tr.classList.add("selected-row");
    } else {
        // Remove selected class when unchecked
        tr.classList.remove("selected-row");
    }
}

/* Sub Function to Handle Table Events Row Click */
function handleRowClick(tr) {
    var checkbox = tr.querySelector('.row-selector');

    // Toggle the class and checkbox state based on the current state
    if (tr.classList.contains("selected-row")) {
        tr.classList.remove("selected-row");
        if (checkbox) {
            checkbox.checked = false;
        }
    } else {
        tr.classList.add("selected-row");
        if (checkbox) {
            checkbox.checked = true;
        }
    }
}

/* General Refresh Function */
function refreshPage() { location.reload(); }

/* Handling of Request Modal */
var startModal = document.getElementById("modalRequest");
var requestModalForm = document.getElementById('requestForm');
var btn = document.getElementById("btnRequest");
var span = document.getElementsByClassName("close")[0];
btn.onclick = function () { console.log("Pressed button Request..."); startModal.style.display = "block"; }; // >> Opening of the modal
span.onclick = function () { startModal.style.display = "none"; }; // >> Closing of the modal
window.onclick = function (event) { if (event.target == startModal) startModal.style.display = "none"; }; // >> Closing of the modal

/* Handling of Terminate Modal */
var terminateModal = document.getElementById("modalTerm");
//span.onclick = function () { terminateModal.style.display = "none"; }; // >> Closing of the modal
//window.onclick = function (event) { if (event.target == terminateModal) terminateModal.style.display = "none"; }; // >> Closing of the modal

/* General Handling of the Request Modal Drawing Input */
document.getElementById('drawingInput').addEventListener('change', function () {
    var drawingInput = document.getElementById('drawingInput');
    var drawingFile = drawingInput.files[0]; // Get the selected file

    if (drawingFile && drawingFile.type === 'application/pdf') {
        var fileName = drawingFile.name;
        var firstEightChars = fileName.substring(0, 8); // Get the first 8 characters
        console.log("Code Name:", firstEightChars);
        // Regular expression to check the pattern: 3 letters, a dot, and 4 numbers
        var pattern = /^[A-Za-z]{3}\.[0-9]{4}$/;
        // Validate firstEightChars here, if necessary.
        // If invalid, make ItemInput editable:
        if (!pattern.test(firstEightChars)) {
            document.getElementById('itemInput').readOnly = false;
            console.log('Non-standard file name format. Please upload a PDF with a name following the pattern XXX.1234');
        } else {
            document.getElementById('itemInput').readOnly = true;
            document.getElementById('itemInput').value = firstEightChars;
        }
    }
});

/* General Handling of the Request Modal Material Input */
var lastAppendedChar = '';  // To keep track of the last character appended
document.getElementById('materialInput').addEventListener('change', function () {
    var selectedMaterial = this.value;  // Get the selected material
    var newChar;  // The character you want to append to the value of itemInput

    if (materialInput) {
        switch (selectedMaterial) {
            case 'optmat':
                newChar = '';  // Default, no character
                break;
            case 'PTFE FL100':
                newChar = '-P';
                break;
            case 'PTFE G400':
                newChar = '-P';
                break;
            case 'Tivar':
                newChar = '-U';
                break;
            case 'PCTFE ∅30mm':
                newChar = '-C';
                break;
            case 'PCTFE ∅40mm':
                newChar = '-C';
                break;
            default:
                newChar = '';  // Default, no character
        }
        // Retrieve the current value of itemInput
        var itemInputElem = document.getElementById('itemInput');
        var currentItemValue = itemInputElem.value;

        // Remove the last appended character if there is one
        if (lastAppendedChar) {
            currentItemValue = currentItemValue.substring(0, currentItemValue.length - lastAppendedChar.length);
        }

        // Append the new character
        itemInputElem.value = currentItemValue + newChar;

        // Update the last appended character
        lastAppendedChar = newChar;
    }
});

/* General Handling of the Request Modal Submit Button */
document.getElementById("submitBtnRequest").onclick = async function () {
    console.log("Submit Request Button Pressed...")
    // Prevent the default form submission
    event.preventDefault();

    var formIsValid = true; // Initialize a flag for form validity
    var formElements = document.querySelectorAll("#requestForm [required]");

    formElements.forEach(function (element) {
        if (!element.checkValidity()) {
            formIsValid = false;
            element.reportValidity();
        }
    });

    // If the form is valid, you can proceed with whatever should happen on submission
    if (formIsValid) {
        const fieldMapping = {
            "statusInput": "status",
            "qtyInput": "qty",
            "itemInput": "item",
            "projectInput": "project",
            "forInput": "who",
            "createdOnInput": "created_on",
            "plannedForInput": "planned_for",
            "materialInput": "material",
            "drawingInput": "drawing",
            "programInput": "program",
            "commentsInput": "comments"
        };

        // Create an empty document object
        const doc = { doctype: "Planning" };

        // Populate the document object and clear the input fields
        for (const [inputId, doctypeField] of Object.entries(fieldMapping)) {
            const element = document.getElementById(inputId);
            doc[doctypeField] = element.value;
            element.value = ""; // Clear the input fields
        }

        // Frappe Call Planning DocType Creation
        const response = await frappe.call({
            method: "frappe.client.insert",
            args: { doc },
        });
        console.log(response.message);
        refreshPage();

        // Closing the Request Modal
        startModal.style.display = "none";
    } else {
        console.log("The form is invalid. Please fill out all required fields.");
    }
    console.log("End RequestForm method");
};

/* General Handling of the Terminate Modal Submit Button */
document.getElementById("submitTerm").onclick = async function () {
    console.log("Submit Terminate Button Pressed...")
    const selectedRows = document.querySelectorAll(".selected-row");
    console.log("Selected Row: ", selectedRows[0].cells[2].innerText);
    const fields = ["progTime", "met", "finalQty"];
    const doc = { doctype: "Planning", name: selectedRows[0].cells[2].innerText }; // Create an empty document object

    // Populate the document object and clear the input fields
    fields.forEach(field => {
        const element = document.getElementById(field);
        doc[field] = element.value;
        element.value = ""; // Clear the input fields
    });
    console.log(doc);
    // Frappe Call Planning DocType Creation
    const response = await frappe.call({
        method: "amf.www.planification.planification.terminate_planning",
        args: { doc },
    });
    console.log(response.message);
    refreshPage();

    /*
    // Log arguments for verification
    console.log(`Arguments - progTime: ${progTime}, met: ${met}, finalQty: ${finalQty}`);

    // Loop through each selected row and perform the Frappe call
    selectedRows.forEach(function (row) {
        const nameValue = row.cells[2].innerText;
        console.log(`Row name value: ${nameValue}`);

        frappe.call({
            method: "amf.www.planification.terminate_planning",
            args: {
                name: nameValue,
                progTime: progTime,
                met: met,
                finalQty: finalQty
            },
            callback: function (response) {
                if (response.exc) {
                    // handle the exception
                    console.error('Server-side exception:', response.exc);
                    return;
                }
                console.log('Frappe response:', response.message);
                refreshPage();
            }
        })
    });

    const response = await frappe.call({
        method: "amf.www.planification.terminate_planning",
        args: { doc },
    });
    console.log(response.message);
    refreshPage();
    */
    terminateModal.style.display = "none";
    console.log("EoF Terminate js method");
};

/* General Handling of the Start Function Button */
async function startRow() {
    console.log("Start Button pressed...");
    var selectedRows = document.querySelectorAll(".selected-row");
    if (selectedRows.length !== 1) {
        alert("Please select a row first!");
        return; // If no row is selected or more than 1, simply return
    }
    console.log("Starting the following Planning:", selectedRows[0].cells[2].innerText);
    const response = await frappe.call({
        method: "amf.www.planification.planification.start_planning",
        args: { name: selectedRows[0].cells[2].innerText },
    });
    console.log(response.message);
    refreshPage();
    console.log("EoF Start js method");
};

/* General Handling of the Terminate Button */
document.getElementById("terminateBtn").addEventListener("click", async function () {
    console.log("Terminate Button pressed...");
    var selectedRows = document.querySelectorAll(".selected-row");
    if (selectedRows.length !== 1) {
        alert("Please select a row first!");
        return; // If no row is selected or more than 1, simply return
    }
    terminateModal.style.display = "block";
});