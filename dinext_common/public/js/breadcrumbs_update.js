const original_method = frappe.breadcrumbs.update;
let stored_workspace;
const stored_views = {};

function view_title(doc_type, doc_view) {
    return doc_view === "Tree" ? __("Tree") : __(doc_type);
}

frappe.breadcrumbs.update = function() {
    const active_route = frappe.get_route();

    // Always update workspace storage when visiting workspace routes
    if (active_route[0] === "Workspaces" /**&& active_route[1]/**/) {
        stored_workspace = active_route[1];
    }
    else {
        const doc_type = active_route[1];
        this.clear();
        
        if ( stored_workspace ) {
            this.append_breadcrumb_element(
                `/app/${frappe.router.slug(stored_workspace)}`,
                __(stored_workspace)
            );
        }
        
        if ( doc_type ) {
            // Handle Form view
            if (active_route[0] === "Form") {    
                const doc_name = active_route[2];
                let document_title;
                const stored = stored_views[doc_type];
                const is_single = !!(
                    frappe.get_meta?.(doc_type)?.issingle ||
                    frappe.get_doc?.("DocType", doc_type)?.issingle
                );

                // Single has no list view — stock Frappe skips this crumb.
                if (!is_single) {
                    this.append_breadcrumb_element(
                        stored?.path || `/app/${frappe.router.slug(doc_type)}`,
                        stored?.title || __(doc_type)
                    );
                }
               
                if (doc_name.startsWith("new-" + doc_type.toLowerCase().replace(/ /g, "-"))) {
                    document_title = __("New {0}", [__(doc_type)]);
                } else {
                    document_title = __(doc_name);
                }
                
                this.append_breadcrumb_element(
                    `/app/${frappe.router.slug(doc_type)}/${encodeURIComponent(doc_name)}`,
                    document_title
                );
                
                let final_crumb = this.$breadcrumbs.find("li").last();
                final_crumb.addClass("disabled").css("cursor", "copy");
                final_crumb.click((event) => {
                    event.stopImmediatePropagation();
                    frappe.utils.copy_to_clipboard(final_crumb.text());
                });
                
            } else {
                const doc_view = ( "Tree" == active_route[0] ) 
                    ? active_route[0] 
                    : ( ( "List" == active_route[0] && "List" != active_route[2])  
                        ? active_route[2] : null );
                const doc_view_variant = active_route[4];
            
                const view_path = `/app/${ ( ["query-report"].includes( active_route[0] ) ? ( active_route[0] + "/") : "" ) 
                    + frappe.router.slug(doc_type)}`
                    + ( doc_view ? "/view/" + doc_view : "" ) 
                    + ( doc_view_variant ? "/" + frappe.router.slug(doc_view_variant) : "" )
                
                stored_views[doc_type] = {
                    path: view_path,
                    title: view_title(doc_type, doc_view),
                };
                
                this.append_breadcrumb_element(
                    stored_views[doc_type].path,
                    stored_views[doc_type].title
                );
            }
            
            this.toggle(true);
            return;
        }
    }
    
    // Fall back to original method if no stored workspace or other routes
    original_method.call(this);
};
