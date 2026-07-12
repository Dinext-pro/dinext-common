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

    const dataHint = document.createElement("div");
    dataHint.className = "text-muted";
    dataHint.style.marginTop = "6px";
    dataHint.textContent = __("1–2 merge+eager; 3–4 merge+lazy; 5,10 eager; 7 lazy; pinned summary (Итого + tree) — expand chevron, ~900ms fetch");

    const LAZY_LOAD_DELAY_MS = () => DinextTableTestData.lazyLoadDelayMs || 900;

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
            summaryRows: DinextTableTestData.summaryRows,
            columns: DinextTableTestData.columns,
            gridOptions: DinextTableTestData.gridOptions,
            edit: true,
            selection: { enabled: true },
            clipboard: { enabled: true },
            rowReorder: { enabled: true },
            selectionStatus: { enabled: true },
            toolbar: {
                enabled: true,
                persistKey: "dinext-table-test",
                items: [
                    {
                        id: "refresh-data",
                        label: __("Refresh data"),
                        icon: "icon-refresh",
                        onClick: ({ table }) => {
                            const data = DinextTableTestData.refreshData();
                            table.refresh(data);
                            table.setSummaryRows(DinextTableTestData.summaryRows);
                            setStatus(__("Ready ({0} rows)", [data.length]));
                        }
                    }
                ]
            },
            onSaveCells: async ({ source, range, changes }) => {
                console.log("DinextTable onSaveCells", { source, range, count: changes.length, changes });
            },
            onRowReorder: async ({ source, move }) => {
                console.log("DinextTable onRowReorder", { source, move });
            },
            onExpandRow: async ({ rowId, row, table, section }) => {
                const parentNum = String(row?.id ?? rowId).split(":").pop();
                console.log("DinextTable onExpandRow (lazy)", { rowId, parentNum, row, section });
                await new Promise((resolve) => setTimeout(resolve, LAZY_LOAD_DELAY_MS()));
                table.setRowChildren(rowId, DinextTableTestData.makeLazyChildren(parentNum));
            },
            onReady: (instance) => {
                const topLevel = instance.sourceData?.length ?? 0;
                const displayed = instance.rowData?.length ?? 0;
                setStatus(__("Ready: {0} top-level, {1} displayed", [topLevel, displayed]));
                console.log("DinextTable ready", { topLevel, displayed, instance });
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
            table.setSummaryRows(DinextTableTestData.summaryRows);
            setStatus(__("Ready ({0} rows)", [data.length]));
        });

        controls.appendChild(status);
        page.main.get(0).appendChild(dataHint);
        createTable();
        window.dinextTableTest = { get table() { return table; }, createTable };
    });
};
