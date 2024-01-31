frappe.ui.form.on('Spreadsheet Expense Claim', {
    refresh: function(frm) {
      frm.add_custom_button('Import from Spreadsheet', function() {
        frm.trigger('import_from_spreadsheet');
      });
    },
    import_from_spreadsheet: function(frm) {
      // Prompt the user to upload the Excel file
      frappe.prompt({
        label: 'Upload Spreadsheet',
        fieldtype: 'Attach',
        reqd: 1,
        description: 'Upload an Excel spreadsheet with date, time, description, and amount columns.'
      }, function(data) {
        // Read the uploaded file and process its data
        frappe.call({
          method: 'frappe.client.read_uploaded_file',
          args: {
            file_url: data.upload_spreadsheet
          },
          callback: function(r) {
            if (r.message) {
              // Parse the data from the uploaded file
              let data = r.message.split(/\r?\n|\r/);
              let columns = data[0].split(',');
  
              // Process and add the values to the child table
              for (let i = 1; i < data.length; i++) {
                let row = data[i].split(',');
                let date = row[columns.indexOf('date')];
                let time = row[columns.indexOf('time')];
                let description = row[columns.indexOf('description')];
                let amount = row[columns.indexOf('amount')];
  
                frm.add_child('spreadsheet_expense_claims', {
                  date: date,
                  time: time,
                  description: description,
                  amount: amount
                });
              }
  
              // Refresh the child table and save the form
              frm.refresh_field('spreadsheet_expense_claims');
              frm.save();
            }
          }
        });
      }, 'Import from Spreadsheet', 'Import').show();
    }
  });
  