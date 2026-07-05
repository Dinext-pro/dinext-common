frappe.pages["dinext-table-test"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("DinextTable Test"),
        single_column: true
    });

    const controls = document.createElement("div");
    controls.style.marginBottom = "12px";
    page.main.get(0).appendChild(controls);

    const status = document.createElement("span");
    status.className = "text-muted";
    status.style.marginLeft = "8px";

    const container = document.createElement("div");
    container.style.height = "80vh";
    page.main.get(0).appendChild(container);

    function setStatus(text) {
        status.textContent = text;
    }

    function addButton(label, onClick) {
        const button = document.createElement("button");
        button.className = "btn btn-default btn-sm";
        button.style.marginRight = "8px";
        button.textContent = label;
        button.addEventListener("click", onClick);
        controls.appendChild(button);
        return button;
    }

    let table = null;

    function createTable() {
        setStatus(__("Loading..."));
        return DinextTable.create({
            container,
            data: DinextTableTestData.data,
            columns: DinextTableTestData.columns,
            gridOptions: DinextTableTestData.gridOptions,
            edit: true,
            onExpandRow: async ({ rowId, table }) => {
                const children = await DinextTableTestData.fetchLazyChildren(rowId);
                table.setRowChildren(rowId, children);
            },
            onReady: (instance) => {
                setStatus(__("Ready ({0} rows)", [instance.rowData.length]));
                console.log("DinextTable ready", instance);
            }
        }).then((instance) => {
            table = instance;
            return instance;
        }).catch((err) => {
            setStatus(__("Error"));
            console.error("DinextTable create failed", err);
            throw err;
        });
    }

    frappe.require([
        "dinext-table.bundle.js",
        "/assets/dinext_common/js/table/test-data.js"
    ], () => {
        addButton(__("Recreate"), () => {
            if (table) {
                table.destroy();
                table = null;
            }
            createTable();
        });

        addButton(__("Refresh Data"), () => {
            if (!table) return;
            const data = DinextTableTestData.refreshData();
            table.refresh(data);
            setStatus(__("Ready ({0} rows)", [data.length]));
            console.log("DinextTable refreshed", data.length);
        });

        controls.appendChild(status);
        createTable();
        window.dinextTableTest = { get table() { return table; }, createTable };
    });
};
