// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

frappe.query_reports["Approval Deadline Discipline"] = {
    filters: [
        {fieldname:"from_date",label:__("From Date"),fieldtype:"Date",default:frappe.datetime.add_days(frappe.datetime.get_today(),-29),reqd:1},
        {fieldname:"to_date",label:__("To Date"),fieldtype:"Date",default:frappe.datetime.get_today(),reqd:1},
        {fieldname:"workflow",label:__("Workflow"),fieldtype:"Link",options:"Workflow"},
        {fieldname:"workflow_state",label:__("State"),fieldtype:"Link",options:"Workflow State"},
        {fieldname:"approver",label:__("Approver"),fieldtype:"Link",options:"User"},
        {fieldname:"reference_doctype",label:__("Document Type"),fieldtype:"Link",options:"DocType"},
        {fieldname:"result",label:__("Result"),fieldtype:"Select",options:[{value:"",label:""},... ["On Time","Completed Late","Overdue","Pending","Error","Unknown"].map(value=>({value,label:__(value)}))]},
        {fieldname:"group_by",label:__("Group By"),fieldtype:"Select",options:[
            {value:"",label:__("Detail")},{value:"approver",label:__("Approver")},
            {value:"user_group",label:__("User Group")},{value:"workflow",label:__("Workflow")},
            {value:"workflow_state",label:__("State")}]},
    ],
};
