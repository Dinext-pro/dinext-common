const originalRefresh = frappe.views.BaseList.prototype.refresh;  
frappe.views.BaseList.prototype.refresh = function() {  
    return originalRefresh.apply(this, arguments).then(() => {  
        makeResizableListview();        
    });  
};

function makeResizableListview() {
    // Изменение ширины столбцов в List View - тикет ISS-2023-00116
    if (!cur_list) return;
    const resultContainer = cur_list.$result[0];
    if (!resultContainer) return;

    const header = resultContainer.querySelector('header');
    if (!header) return;
    const listHeaderSubject = header.querySelector('.list-header-subject');
    const listRowContainers = resultContainer.querySelectorAll('.list-row-container');
    listHeaderSubject.classList.add("ellipsis");
    
    // Получаем сохраненные ширины столбцов
    const storedWidths = JSON.parse(localStorage.getItem(`column_widths_${cur_list.doctype}`) || '{}');

    // Все заголовки столбцов
    const headers = listHeaderSubject.querySelectorAll('.list-row-col');
    headers.forEach((headerDiv, index) => {
        const fieldnameSpan = headerDiv.querySelector('span');
        const fieldname = fieldnameSpan ? fieldnameSpan.textContent.trim() : null;

        // Если это последний столбец (например, assign_to), не меняем ширину
        if (fieldname === 'Assign To' || !fieldname) return;

        // Устанавливаем сохраненную ширину, если она есть
        if (storedWidths[fieldname]) {
            const newWidth = getWidth( storedWidths[fieldname] );
            headerDiv.style.minWidth = newWidth;
            resize( newWidth, index );
        }

        // Создаем элемент для изменения ширины
        const resizer = document.createElement('div');
        resizer.classList.add('column-resizer');
        resizer.setAttribute("data-index", index)
        resizer.addEventListener('mousedown', initResize);

        headerDiv.style.position = 'relative';
        headerDiv.appendChild(resizer);
    });

    function initResize(e) {
        const headerDiv = e.target.parentElement;
        const startX = e.clientX;
        const startWidth = headerDiv.offsetWidth;
        const index = e.target.getAttribute("data-index");
        
        function doResize(event) {
            const newWidth = getWidth( startWidth + (event.clientX - startX) );
            headerDiv.style.minWidth = newWidth;
            resize( newWidth, index );
        }

        function stopResize() {
            document.removeEventListener('mousemove', doResize);
            document.removeEventListener('mouseup', stopResize);

            const fieldnameSpan = headerDiv.querySelector('span');
            const fieldname = fieldnameSpan ? fieldnameSpan.textContent.trim() : null;

            if (fieldname) {
                storedWidths[fieldname] = headerDiv.offsetWidth;
                localStorage.setItem(`column_widths_${cur_list.doctype}`, JSON.stringify(storedWidths));
            }
        }

        document.addEventListener('mousemove', doResize);
        document.addEventListener('mouseup', stopResize);
    }
    
    // Обновляем ширину в строках данных
    function resize(newWidth, index) {
        listRowContainers.forEach(container => {
            const row = container.querySelector('.list-row');
            if (row) {
                const cells = row.querySelectorAll('.list-row-col');
                if (cells[index]) {
                    cells[index].style.minWidth = newWidth;
                }
            }
        });
    }
    
    function getWidth( width ) {
        return "min( 40vw, " + width + "px)";
    }
}

function applyResizeStyle() {
    // Your CSS as text
    var styles = `
        .column-resizer {
            cursor: col-resize;
            width: 3px;
            position: absolute;
            right: 0;
            top: 0;
            height: 100%;
            z-index: 10;
            background-color: var(--bg-color);
        }
        .list-row-col {
            min-width: 15px;
        }
    `;

    var styleSheet = document.createElement("style");
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);
}

applyResizeStyle();