window.onload = function () {
    document.querySelector("nav").style.display = 'none';
    document.querySelector("footer").style.display = 'none';
};

// Fetch and display the documents after the page has loaded
$(document).ready(function () {
    document.getElementById('open-planning-list').addEventListener('click', function () {
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
            document.getElementById('login-button').innerHTML = user_email;
            document.getElementById('login-button').href = "/desk";
        });
    }
    fetchAndDisplayDocuments();
});

function fetchAndDisplayDocuments() {
    frappe.call({
        method: 'amf.www.planification.get_planning_list',
        args: {},
        callback: function (response) {
            var documents = response.message;
            for (var i = 0; i < documents.length; i++) {
                var document = documents[i];
                addRowToTable(document);
            }
        }
    });
}

// Add an event listener to the table
/*document.getElementById("myTable").addEventListener("click", function(e) {
    // Find the closest row clicked on
    var tr = e.target.closest('tr');
    
    // If a row is found
    if (tr) {
        // Check if this row is already selected
        if (tr.classList.contains("selected-row")) {
            // If it's already selected, simply remove the selected class
            tr.classList.remove("selected-row");
        } else {
            // If it's not selected, first remove the selected class from any other rows
            var rows = document.querySelectorAll("#myTable tr");
            for (var i = 0; i < rows.length; i++) {
                rows[i].classList.remove("selected-row");
            }
            
            // Then add the selected class to the clicked row
            tr.classList.add("selected-row");
        }
    }
});*/

document.getElementById("myTable").addEventListener("click", function (e) {
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

function handleRowClick(tr) {
    // First, deselect all rows and uncheck their checkboxes
    var rows = document.querySelectorAll("#myTable tr");
    for (var i = 0; i < rows.length; i++) {
        rows[i].classList.remove("selected-row");
        var checkbox = rows[i].querySelector('.row-selector');
        if (checkbox) {
            checkbox.checked = false;
        }
    }

    // Then, select the clicked row and check its checkbox
    tr.classList.add("selected-row");
    var checkbox = tr.querySelector('.row-selector');
    if (checkbox) {
        checkbox.checked = true;
    }
}

function addRowToTable(doc) {
    var table = document.getElementById("myTable");
    var row = table.insertRow(-1);

    var checkboxCell = row.insertCell(0);
    checkboxCell.innerHTML = '<input type="checkbox" class="row-selector">';

    // var idCell = row.insertCell(-1);
    // idCell.innerHTML = doc.name;  // '- 1' because the first row is the header row

    var statusCell = row.insertCell(-1);
    if (doc.status)
        statusCell.innerHTML = '<div class="editableStatus" contenteditable="true">' + doc.status + '</div>';
    else
        statusCell.innerHTML = "";

    var jobCardCell = row.insertCell(-1);
    if (doc.job_card)
        jobCardCell.innerHTML = '<a href="https://amf.libracore.ch/desk#Form/Job%20Card/' + doc.job_card + '" class="constrained-link">' + doc.name + '</a>';
    else
        jobCardCell.innerHTML = doc.name;

    var qtyCell = row.insertCell(-1);
    if (doc.qty)
        qtyCell.innerHTML = doc.qty;
    else
        qtyCell.innerHTML = "";

    var itemCell = row.insertCell(-1);
    if (doc.item)
        itemCell.innerHTML = doc.item;
    else
        itemCell.innerHTML = "";

    var projectCell = row.insertCell(-1);
    if (doc.project)
        projectCell.innerHTML = doc.project;
    else
        projectCell.innerHTML = "";

    var forCell = row.insertCell(-1);
    if (doc.who)
        forCell.innerHTML = doc.who;
    else
        forCell.innerHTML = "";

    var createdOnCell = row.insertCell(-1);
    if (doc.created_on)
        createdOnCell.innerHTML = doc.created_on;
    else
        createdOnCell.innerHTML = "";

    var plannedForCell = row.insertCell(-1);
    if (doc.planned_for)
        plannedForCell.innerHTML = doc.planned_for;
    else
        plannedForCell.innerHTML = "";

    var endDateCell = row.insertCell(-1);
    if (doc.end_date)
        endDateCell.innerHTML = doc.end_date;
    else
        endDateCell.innerHTML = "";

    var deliveredqtyCell = row.insertCell(-1);
    if (doc.delivered_qty)
        deliveredqtyCell.innerHTML = doc.delivered_qty;
    else
        deliveredqtyCell.innerHTML = "";

    var materialCell = row.insertCell(-1);
    if (doc.material)
        materialCell.innerHTML = doc.material;
    else
        materialCell.innerHTML = "";

    var drawingCell = row.insertCell(-1);
    if (doc.drawing)
        drawingCell.innerHTML = '<a href="' + doc.drawing + '" class="constrained-link">' + doc.drawing.substring(24, 45) + '</a>';
    else
        drawingCell.innerHTML = "";

    var programCell = row.insertCell(-1);
    if (doc.program)
        programCell.innerHTML = doc.program;
    else
        programCell.innerHTML = "";

    var commentsCell = row.insertCell(-1);
    if (doc.comments)
        commentsCell.innerHTML = doc.comments;
    else
        commentsCell.innerHTML = "";

    // var filterCell = row.insertCell(-1);
    // filterCell.innerHTML = doc.filter;

    // Add the rest of the cells as needed
}

// Get the modal
var modal = document.getElementById("myModal");

// Get the button that opens the modal
var btn = document.getElementById("myBtn");

// Get the <span> element that closes the modal
var span = document.getElementsByClassName("close")[0];

// When the user clicks the button, open the modal 
btn.onclick = function () {
    modal.style.display = "block";
};

// When the user clicks on <span> (x), close the modal
span.onclick = function () {
    modal.style.display = "none";
};

// When the user clicks anywhere outside of the modal, close it
window.onclick = function (event) {
    if (event.target == modal) {
        modal.style.display = "none";
    }
};

function refreshPage() {

    /*frappe.call({
        method: 'amf.www.planification.update_status',
        args: {
            name: "The Document Name or ID",
            updated_field_value: "The New Value for the Field"
        },
        callback: function (response) {
            if (!response.exc) {
                // success
                console.log(response.message);
                // Maybe refresh the form or perform other UI updates
            }
        }
    });*/

    location.reload();
}

// When the user clicks the Submit button, add a new row and create a new document
document.getElementById("submitBtn").onclick = function () {
    var statusValue = document.getElementById("statusInput").value;
    var jobCardValue = "";
    var qtyValue = document.getElementById("qtyInput").value;
    var itemValue = document.getElementById("itemInput").value;
    var projectValue = document.getElementById("projectInput").value;
    var forValue = document.getElementById("forInput").value;
    var createdOnValue = document.getElementById("createdOnInput").value;
    var plannedForValue = document.getElementById("plannedForInput").value;
    var endDateValue = "";
    var deliveredqtyValue = "";
    var materialValue = document.getElementById("materialInput").value;
    var drawingValue = document.getElementById("drawingInput").value;
    var programValue = document.getElementById("programInput").value;
    var commentsValue = document.getElementById("commentsInput").value;
    var filterValue = "";

    filterValue = assignStatus(statusValue);

    // Create the new document
    frappe.call({
        method: "frappe.client.insert",
        args: {
            doc: {
                doctype: "Planning",
                status: statusValue,
                job_card: jobCardValue,
                qty: qtyValue,
                item: itemValue,
                project: projectValue,
                who: forValue,
                created_on: createdOnValue,
                planned_for: plannedForValue,
                end_date: endDateValue,
                delivered_qty: deliveredqtyValue,
                material: materialValue,
                drawing: drawingValue,
                program: programValue,
                comments: commentsValue,
                filter: filterValue,
                // rest of your data
            },
        },
        callback: function (response) {
            console.log(response.message);
            refreshPage();
        }
    });

    // Clear the input fields
    document.getElementById("statusInput").value = "";
    //document.getElementById("jobCardInput").value = "";
    document.getElementById("qtyInput").value = "";
    document.getElementById("itemInput").value = "";
    document.getElementById("projectInput").value = "";
    document.getElementById("forInput").value = "";
    document.getElementById("createdOnInput").value = "";
    document.getElementById("plannedForInput").value = "";
    //document.getElementById("endDateInput").value = "";
    //document.getElementById("deliveredqtyInput").value = "";
    document.getElementById("materialInput").value = "";
    document.getElementById("drawingInput").value = "";
    document.getElementById("programInput").value = "";
    document.getElementById("commentsInput").value = "";
    //document.getElementById("deliveredqtyInput").value = "";

    // Close the modal
    modal.style.display = "none";

};

function assignStatus(statusVal) {
    var filterValue;
    switch (statusVal) {
        case "QC":
            filterValue = 1;
            break;
        case "Free":
            filterValue = 70;
            break;
        case "Reserved":
            filterValue = 65;
            break;
        case "On Hold":
            filterValue = 60;
            break;
        case "Cancelled":
            filterValue = 75;
            break;
        case "Fab":
            filterValue = 5;
            break;
        case "Done":
            filterValue = 80;
            break;
        case "Rework":
            filterValue = 50;
            break;
        case "Planned #1":
            filterValue = 10;
            break;
        case "Planned #2":
            filterValue = 20;
            break;
        case "Planned #3":
            filterValue = 30;
            break;
        case "Planned #4":
            filterValue = 40;
            break;
        case "Planned #5":
            filterValue = 50;
            break;
    };
    return filterValue;
}

function startRow() {
    // Get the selected row
    var selectedRows = document.querySelectorAll(".selected-row");

    // If no row is selected, simply return
    if (selectedRows.length === 0) {
        alert("Please select a row first!");
        return;
    }

    // Loop through each selected row and print the info
    selectedRows.forEach(function (row) {
        //console.log(row.cells[2].innerText);
        //sendToServer(row.cells[2].innerText);
        var rowData = [];
        Array.from(row.cells).forEach(function (cell, index) {
            rowData.push(cell.innerText);
        });
        //console.log(rowData);
        sendToServer(rowData);
    });
    //refreshPage();
};

function sendToServer(rowData) {
    frappe.call({
        method: "amf.www.planification.create_job_card",
        args: {
            row_data_str: rowData
        },
        callback: function (response) {
            if (!response.exc) {
                console.log(response.message);
                alert('Job card created successfully!');
                //refreshPage();
            } else {
                console.error(response.exc);
                alert('Failed to create job card.');
            }
            refreshPage();
        }
    });
};

function finishRow() {

}
