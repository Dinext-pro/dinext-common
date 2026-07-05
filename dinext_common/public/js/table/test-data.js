(function() {
    function renderNameCell(params) {
        const data = params.data || {};
        const el = document.createElement("div");
        el.className = "dinext-table-name-cell";

        if (data.showAvatar) {
            const avatar = document.createElement("span");
            avatar.className = "dinext-table-demo-avatar";
            avatar.textContent = ((data.name || "?").charAt(0)).toUpperCase();
            el.appendChild(avatar);
        }

        const label = document.createElement("span");
        label.className = "dinext-table-name-label";
        label.textContent = data.name || "";
        label.title = data.name || "";
        el.appendChild(label);
        return el;
    }

    const columns = [
        {
            field: "name",
            headerName: "Name",
            flex: 1,
            render: renderNameCell
        },
        { field: "id", headerName: "ID", width: 80 },
        { field: "category", headerName: "Category", width: 120, edit: false },
        {
            field: "value",
            headerName: "Value",
            width: 120,
            cellDataType: "number",
            cellClass: "dinext-table-cell--align-right",
            valueFormatter: (params) => {
                if (params.value == null || params.value === "") {
                    return "";
                }
                return `${Number(params.value).toLocaleString("ru-RU")} ₽`;
            },
            cellClassRules: {
                "dinext-table-cell--negative": (params) => Number(params.value) < 0,
                "dinext-table-cell--highlight": (params) => Number(params.value) >= 800
            }
        }
    ];

    const gridOptions = {
        getRowClass: (params) => {
            const level = params.data?._level;
            if (level === 1) {
                return "dinext-table-row--level-1";
            }
            if (level >= 2) {
                return "dinext-table-row--level-2";
            }
            return "";
        }
    };

    /** Simulated API: rowId → children (lazy load demo). */
    const LAZY_CHILDREN = {
        "201": [
            { id: 2011, name: "Lazy — row 1", category: "L", value: 10, showAvatar: true },
            { id: 2012, name: "Lazy — sub-group", category: "L", value: 20, hasChildren: true, showAvatar: true }
        ],
        "201:2012": [
            { id: 20121, name: "Lazy — nested 1", category: "L", value: 5 },
            { id: 20122, name: "Lazy — nested 2", category: "L", value: 7 }
        ]
    };

    function generateData() {
        const flat = [];
        for (let i = 1; i <= 8; i++) {
            flat.push({
                id: i,
                name: `Item ${i}`,
                category: ["A", "B", "C"][i % 3],
                value: Math.floor(Math.random() * 1000)
            });
        }

        const groups = [
            {
                id: 101,
                name: "Group Alpha (eager, 2 levels)",
                category: "A",
                value: 450,
                showAvatar: true,
                children: [
                    { id: 1011, name: "Alpha — row 1", category: "A", value: 150, showAvatar: true },
                    {
                        id: 1012,
                        name: "Alpha — sub-group",
                        category: "A",
                        value: 300,
                        showAvatar: true,
                        children: [
                            { id: 10121, name: "Alpha — nested 1", category: "A", value: -45 },
                            { id: 10122, name: "Alpha — nested 2", category: "A", value: 920 }
                        ]
                    }
                ]
            },
            {
                id: 102,
                name: "Group Beta (eager, 1 level)",
                category: "B",
                value: 220,
                showAvatar: true,
                children: [
                    { id: 1021, name: "Beta — row 1", category: "B", value: 80 },
                    { id: 1022, name: "Beta — row 2", category: "B", value: 140 }
                ]
            },
            {
                id: 201,
                name: "Group Lazy (fetch on expand)",
                category: "L",
                value: 0,
                showAvatar: true,
                hasChildren: true
            }
        ];

        return groups.concat(flat);
    }

    function fetchLazyChildren(rowId) {
        return new Promise(resolve => {
            setTimeout(() => {
                resolve(JSON.parse(JSON.stringify(LAZY_CHILDREN[rowId] || [])));
            }, 2000);
        });
    }

    window.DinextTableTestData = {
        data: generateData(),
        columns,
        gridOptions,
        fetchLazyChildren,
        refreshData() {
            this.data = generateData();
            return this.data;
        }
    };
})();
