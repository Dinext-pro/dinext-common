(function() {
    function renderTreeLabel(params) {
        const el = document.createElement("span");
        el.textContent = params.data?.a ?? "";
        return el;
    }

    function mergeGroupSpanRows(params) {
        const a = params.nodeA?.data;
        const b = params.nodeB?.data;
        return a?.mergeGroupId && a.mergeGroupId === b?.mergeGroupId;
    }

    const columns = [
        {
            field: "a",
            headerName: "A",
            width: 120,
            render: renderTreeLabel,
            spanRows: mergeGroupSpanRows
        },
        {
            field: "b",
            headerName: "B",
            width: 100
        },
        {
            headerName: "CD",
            children: [
                { field: "c", headerName: "C", width: 90, resizable: false },
                { field: "d", headerName: "D", width: 90, resizable: false }
            ]
        },
        {
            headerName: "EF",
            children: [
                { field: "e", headerName: "E", width: 90, resizable: false },
                { field: "f", headerName: "F", width: 90, resizable: false }
            ]
        }
    ];

    const gridOptions = {
        enableCellSpan: true
    };

    function makeRow(id, label) {
        const text = String(label);
        return {
            id,
            a: text,
            b: `B-${text}`,
            c: `C-${text}`,
            d: `D-${text}`,
            e: `E-${text}`,
            f: `F-${text}`
        };
    }

    function makeChildRows(parentNum) {
        return [1, 2].map((sub) => {
            const label = `${parentNum}.${sub}`;
            return makeRow(label, label);
        });
    }

    /** Simulated API response for onExpandRow (lazy load demo). */
    function makeLazyChildren(parentNum) {
        return makeChildRows(parentNum).map((row) => ({
            ...row,
            a: `${row.a} (lazy)`
        }));
    }

    function generateData() {
        const rows = [];

        const row1 = makeRow(1, 1);
        row1.a = "Merge 1–2 (eager)";
        row1.mergeGroupId = "g-1";
        row1.mergeGroupIndex = 0;
        row1.mergeGroupSize = 2;
        row1.children = makeChildRows(1);

        const row2 = makeRow(2, 2);
        row2.a = "";
        row2.mergeGroupId = "g-1";
        row2.mergeGroupIndex = 1;
        row2.mergeGroupSize = 2;

        rows.push(row1, row2);

        const row3 = makeRow(3, 3);
        row3.a = "Merge 3–4 (lazy)";
        row3.mergeGroupId = "g-2";
        row3.mergeGroupIndex = 0;
        row3.mergeGroupSize = 2;
        row3.hasChildren = true;

        const row4 = makeRow(4, 4);
        row4.a = "";
        row4.mergeGroupId = "g-2";
        row4.mergeGroupIndex = 1;
        row4.mergeGroupSize = 2;

        rows.push(row3, row4);

        for (let i = 5; i <= 10; i += 1) {
            const row = makeRow(i, i);
            if (i === 5 || i === 10) {
                row.a = `${i} (eager)`;
                row.children = makeChildRows(i);
            }
            if (i === 7) {
                row.a = "7 (lazy)";
                row.hasChildren = true;
            }
            rows.push(row);
        }
        return rows;
    }

    function generateSummaryRows() {
        const total = makeRow("total", "Итого");
        total.a = "Итого";
        total.b = "Σ body";
        total.c = "";
        total.d = "";
        total.e = 0;
        total.f = 0;

        const sub = makeRow("sub-a", "Подитог A");
        sub.a = "Подитог A";
        sub.b = "Σ A";
        sub.children = [
            { ...makeRow("sub-a-1", "A.1"), a: "A.1 detail" }
        ];

        return [total, sub];
    }

    window.DinextTableTestData = {
        data: generateData(),
        summaryRows: generateSummaryRows(),
        columns,
        gridOptions,
        lazyLoadDelayMs: 900,
        makeLazyChildren,
        refreshData() {
            this.data = generateData();
            this.summaryRows = generateSummaryRows();
            return this.data;
        }
    };
})();
