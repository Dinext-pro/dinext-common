function sparse_filters(filters) {

    if (Array.isArray(filters)) {

            filters.forEach((filter)=> {
                    if(filter[1].includes('_assign') || filter[1].includes('_liked_by')) {
                            if (filter[2] === '=') {
                                    filter[2] = 'like';
                                    filter[3] = '%'+filter[3]+'%';
                            }
                    }
            })

    } else {

            if (typeof filters === 'object' && filters != null) {
                    Object.keys(filters).forEach((key) => {
                            let filter = filters[key];
                            if (Array.isArray(filter)) {
                                    if (filter[1].includes('_assign') || filter[1].inculdes('_liked_by')){
                                            if (filter[2] === '=') {
                                                    filter[2] = 'like';
                                                    filter[3] = '%'+filter[3]+'%';
                                            }
                                    }
                            }
                    })
            }

    }

    return filters;
}

const originalGetAllFilters = frappe.dashboard_utils.get_all_filters;  

frappe.dashboard_utils.get_all_filters = function() {  
    return sparse_filters( originalGetAllFilters.apply(this, arguments) );
};