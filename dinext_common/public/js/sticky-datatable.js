if (typeof HyperList === 'undefined') {
    var HyperList_script = document.createElement('script');
    HyperList_script.setAttribute('type',"module");
    HyperList_script.setAttribute('src','/assets/dinext_common/js/hyperlist.js');
    document.head.appendChild(HyperList_script);
}

if (typeof DataTable === 'undefined') {
    var datatable_script = document.createElement('script');
    datatable_script.setAttribute('type',"module");
    datatable_script.setAttribute('src','/assets/dinext_common/js/frappe-datatable.min.js');
    document.head.appendChild(datatable_script);
}

function BodyRendererDecorator( bodyRenderer ) {
    const original_bodyRenderer_renderows = bodyRenderer.renderRows;

    bodyRenderer.renderRows = function(rows) {
        this.visibleRows = rows;
        this.visibleRowIndices = rows.map(row => row.meta.rowIndex);
        this.instance.noData = false;
        if (rows.length === 0) {
            this.bodyScrollable.innerHTML = this.getNoDataHTML();
            this.instance.noData = true;
            this.footer.innerHTML = '';
            return;
        }

        // Create a temporary set for faster lookups.
        // We can't change this.visibleRowIndices as it would be breaking for users.
        let visibleRowIndicesSet = new Set(this.visibleRowIndices);
        const rowViewOrder = this.datamanager.rowViewOrder.map(index => {
            if (visibleRowIndicesSet.has(index)) {
                return index;
            }
            return null;
        }).filter(index => index !== null);

        const computedStyle = getComputedStyle(this.bodyScrollable);

        let config = {
            width: computedStyle.width,
            height: computedStyle.height,
            instance: this.instance,
            rows: rows.map( r => r.meta.rowIndex ),
            get itemHeight() { 
                if ( this.instance.options.dynamicRowHeight && this.instance.options.getDynamicRowHeight ) {
                    let heights = [];
                    for ( i of this.rows ) {
                        heights.push( this.instance.options.getDynamicRowHeight( this.instance, i ) );
                    }
                    return heights;
                }/**/
                return this?.instance?.options?.cellHeight || 0;
            },
            total: rows.length,
            generate: (index) => {
                //console.log("generate row: " + index);
                const el = document.createElement('div');
                const rowIndex = rowViewOrder[index];
                const row = this.datamanager.getRow(rowIndex);
                const rowHTML = this.rowmanager.getRowHTML(row, row.meta);
                el.innerHTML = rowHTML;
                return el.children[0];
            },
            afterRender: () => {
                this.restoreState();
            }
        };

        if (this.hyperlist) {
            this.hyperlist.destroy();
        }
        
        this.hyperlist = new HyperList(this.bodyScrollable, config);/**/
        this.renderFooter();
    }

    return bodyRenderer;
}

/*/
  Sticky extensions for Frappe DataTable — v2 (integrated, virtualized, perf-optimized)
  ------------------------------------------------------------------------------
  Что внутри:
    - StickyManager: интегрируется с внутренними событиями DataTable (через options.events или public hooks),
      оптимизирован для больших наборов данных.
    - StickyDataTable: удобная обёртка (по-прежнему) для быстрого запуска.
    - injectStickyCSS(): базовые правила + placeholder для динамически сгенерированного stylesheet.
    - Генерация CSS-правил вместо массовой записи inline-style по каждой ячейке — одна запись на колонку.

  Подход к производительности:
    1) Для каждой "липкой" колонки записываем только ОДНО CSS-правило вида
         .dt-sticky-col[data-sticky-index="I"] { left: Xpx }
       — это уменьшает layout thrashing и количество inline-операций.
    2) Добавляем атрибут data-sticky-index к ячейкам и класс dt-sticky-col. Это дешёвая операция (атрибуты),
       и браузер применит единое CSS-правило ко всем соответствующим ячейкам.
    4) Подписываемся на публичные события DataTable (options.events): onRemoveColumn, onSwitchColumn,
       onSortColumn, onResizeColumn-like (если есть) и т.п. — и триггерим пересчёт.
    5) Используем debounced requestAnimationFrame + microtask scheduling для группировки пересчётов.

  Как использовать:
    - new StickyDataTable(container, { stickyColumnsCount: 2 })  — или
    - const sm = new StickyManager(datatable, { stickyColumnsCount: 2 });

  Замечание: код использует публичные свойства DataTable (options, container) и стандартные DOM-структуры.
  При интеграции в проект можно заменить detection-логики (header/rows селекторы) под вашу версию разметки.
*/

// ==================== CSS-injector ====================
function injectStickyCSS( selector ) {
  if (document.getElementById('dt-sticky-css' + selector )) return; // уже добавлено
  const css = `
    /* Base styles for sticky columns (minimal) */
    ${ selector } {
        & .datatable .dt-scrollable {
            overflow: auto !important;
        }
        & .dt-row-header {
            overflow-x: hidden;
        }
        & .dt-row-totalRow {
            overflow-x: hidden;
        }
        & .dt-sticky-col {
          position: sticky !important;
          /* left будет задаваться через динамически сгенерированные правила на основе data-sticky-index */
          z-index: 3 !important;
          will-change: left;
          box-shadow: 1px 0 0 rgba(0,0,0,0.04);
          background-clip: padding-box;
        }
        & .dt-sticky-col.dt-header-cell {
          z-index: 6;
        }
    }
    /* placeholder stylesheet where per-column rules will be injected (#dt-sticky-generated) */
`;
  const style = document.createElement('style');
  style.id = 'dt-sticky-css' + selector;
  style.innerHTML = css;
  document.head.appendChild(style);

  // generated stylesheet for left offsets
  const gen = document.createElement('style');
  gen.id = 'dt-sticky-generated' + selector;
  gen.innerHTML = '/* generated sticky left rules */';
  document.head.appendChild(gen);
}

// ==================== StickyManager (v2) ====================
class StickyManager {
  constructor(datatable, options = {}) {
    this.options = Object.assign({
      stickyColumnsCount: null,
      stickyBackground: null,
      stickySelector: null,
      // минимальный интервал перерендера (мс) при непрерывных событиях
      minRenderInterval: 40
    }, options);

    // получить инстанс datatable
    this.datatable = datatable;
    this.el = datatable.container;
    
    $( this.el ).addClass( "dt-sticky-table" );
    this._selector = this._getElementSelector( this.el );
    
    injectStickyCSS( this._selector );

    // internal state
    this._stickyCount = 0;
    this._lefts = [];
    this._lastRender = 0;

    // reference to generated stylesheet
    this._genSheet = document.getElementById('dt-sticky-generated' + this._selector);

    // bind events / observers
    this._bind();

    // initial apply
    this.scheduleRecalculate(true);
  }

  // ------------------ Event binding ------------------
  _bind() {
    // window resize (debounced)
    this._onWindowResize = this._throttle(() => this.scheduleRecalculate(), this.options.minRenderInterval);
    window.addEventListener('resize', this._onWindowResize);

    // minimal ResizeObserver to re-evaluate container dimension
    try {
      this._ro = new ResizeObserver(() => { 
          this.scheduleRecalculate(); 
           this.datatable.style.onWindowResize();
      });
      this._ro.observe(this.el);
    } catch (e) { /* noop */ }

    // MutationObserver 
    this._mo = new MutationObserver(this._throttle(() => this.scheduleRecalculate(), this.options.minRenderInterval));
    this._mo.observe(this.el, { childList: true, subtree: true });
    
    $(this.datatable.bodyScrollable).on('scroll', (e) => {
        this.scheduleRecalculate( true );
    });
    
        // 1) сохраняем "оригинал" ДО переопределения
    const originalSetWidth = this.datatable.columnmanager.setColumnWidth;
    
    // 2) переопределяем только на ЭКЗЕМПЛЯРЕ
    this.datatable.columnmanager.setColumnWidth = function (...args) {
        let sm = this.instance._sm;
        if ( args[0] < sm._stickyCount ) {
            sm.scheduleRecalculate( );
        }
        // корректно проксируем в оригинальный метод
        return Reflect.apply(originalSetWidth, this, args);
    };

    // hook into datatable public events (options.events)
    this._attachToDataTableEvents();
  }

  destroy() {
    window.removeEventListener('resize', this._onWindowResize);
    if (this._ro) this._ro.disconnect();
    if (this._mo) this._mo.disconnect();
    this._detachFromDataTableEvents();
  }

  scheduleRecalculate(immediate = false) {
    const now = performance.now();
    if (!immediate && now - this._lastRender < this.options.minRenderInterval) return;
    this._lastRender = now;
    // batch via rAF
    requestAnimationFrame(() => {
      this.recalculate();
    });
  }

  // ------------------ DataTable events integration ------------------
  _attachToDataTableEvents() {
    if (!this.datatable) return;
    // If datatable exposes 'on'/'off' API
    try {
      if (typeof this.datatable.on === 'function') {
        // try binding known high-impact events (best-effort)
        this.datatable.on('rendered', () => this.scheduleRecalculate());
        this.datatable.on('redraw', () => this.scheduleRecalculate());
      }
    } catch (e) {}

    // Wrap options.events callbacks if provided by user — ensure our scheduleRecalculate triggers after they run
    const ev = this.datatable && this.datatable.options && this.datatable.options.events;
    if (ev && typeof ev === 'object') {
      this._wrappedEvents = {};
      const names = ['onRemoveColumn', 'onSwitchColumn', 'onSortColumn', 'onCheckRow', 'onColumnResize', 'onColumnResized'];
      names.forEach(name => {
        if (typeof ev[name] === 'function') {
          this._wrappedEvents[name] = ev[name];
          ev[name] = (...args) => {
            try { this._wrappedEvents[name](...args); } catch (e) {}
            this.scheduleRecalculate();
          };
        }
      });
    }
  }

  _detachFromDataTableEvents() {
    // if we wrapped options.events, we can't easily restore original unless we saved it — we saved to _wrappedEvents
    if (this._wrappedEvents && this.datatable && this.datatable.options && this.datatable.options.events) {
      const ev = this.datatable.options.events;
      for (const k in this._wrappedEvents) {
        ev[k] = this._wrappedEvents[k];
      }
    }
  }/**/
  
    _getElementScrollbarThickness(el) {
        return el.offsetWidth - el.clientWidth;
    }

  // ------------------ Main algorithm ------------------
  recalculate() {
    const columns = this._getColumnDefs();
    const stickyCount = this._resolveStickyCount(columns);
    this._stickyCount = stickyCount;
    const lefts = this._computeLeftOffsets(stickyCount);
    this._lefts = lefts;
    // update generated stylesheet with left rules
    this._updateGeneratedStylesheet(lefts);
    // apply attribute/class to header and to currently rendered rows
    this._applyStickyToAllRows(stickyCount);
    let scrollWidth = this._getElementScrollbarThickness( this.datatable.bodyScrollable );
    let scrollLeft = $( this.el ).find(".dt-scrollable").scrollLeft();
    let header = $( this.el ).find(".dt-row-header");
    let footer = $( this.el ).find(".dt-row-totalRow");
    header.css("padding-right", scrollWidth + "px");
    footer.css("padding-right", scrollWidth + "px");
    header.scrollLeft( scrollLeft );
    footer.scrollLeft( scrollLeft );
  }

    _getColumnDefs() {
        return this.datatable.options.columns;
    }

  _resolveStickyCount(columns) {
    if (typeof this.options.stickyColumnsCount === 'number') return Math.max(0, Math.min(columns.length, this.options.stickyColumnsCount));
    if (columns && columns.length) {
      let byFlag = columns.reduce((acc, c, idx) => { if (c && (c.sticky === true || c.sticky === 'left')) acc.push(idx); return acc; }, []);
      if (byFlag.length) return Math.max(0, Math.max(...byFlag) + 1);
    }
    if (typeof this.options.stickySelector === 'function') {
      let count = 0;
      for (let i = 0; i < columns.length; i++) {
        try { if (this.options.stickySelector(columns[i], i)) count++; } catch(e) {}
      }
      if (count) return count;
    }
    return 0;
  }
  
  _getWidth (element ) {
      const cs = getComputedStyle(element);
      const base = element.getBoundingClientRect().width;
      const mx = parseFloat(cs.marginLeft) + parseFloat(cs.marginRight);
      return base + mx;
  }

  _computeLeftOffsets(count) {
    const lefts = [];
    if (count <= 0) return lefts;
    let acc = 0;
    for (let i = 0; i < count; i++) {
        const w = this._getWidth( this.datatable.columnmanager.getHeaderCell$(i) );
        lefts.push( acc );
        acc += ( w );
    }
    return lefts;
  }
  
  _getElementSelector(element) {
    const $el = $(element);
    let selector = $el.prop('tagName').toLowerCase();
    const id = $el.attr('id');
    if (id) {
        selector += '#' + id;
    }
    const classNames = $el.attr('class');
    if (classNames) {
        selector += '.' + classNames.split(' ').join('.');
    }
    return selector;
  }

  // Перезаписываем сгенерированный stylesheet: ОДНО обновление для всех колонок
  _updateGeneratedStylesheet(lefts) {
    if (!this._genSheet) this._genSheet = document.getElementById('dt-sticky-generated'+ this._selector);
    if (!this._genSheet) return;
    let rules = '';
    for (let i = 0; i < lefts.length; i++) {
      // data-sticky-index selector; применится ко всем ячейкам с этим атрибутом
      rules += `${this._selector} .dt-sticky-col[data-sticky-index="${i}"]{ left: ${lefts[i]}px; }`;
    }
    this._genSheet.textContent = rules || '/* no sticky columns */';
  }

  // Для обычной (non-virtualized) таблицы — обходим строки и ставим attribute/class на первые count ячеек
  _applyStickyToAllRows(count) {
    const rowSelectors = ['.dt-row', '.datatable-row', '[data-row-index]'];
    let rows = [];
    for (const s of rowSelectors) {
      const found = Array.from(this.el.querySelectorAll(s));
      if (found && found.length) { rows = found; break; }
    }
    if (!rows.length) {
      // fallback — попробуем найти любыe элементы с data-col-index
      const cols = this.el.querySelectorAll('[data-col-index]');
      cols.forEach(col => {
        const idx = parseInt(col.getAttribute('data-col-index'), 10);
        if (!isNaN(idx) && idx < count) {
          col.classList.add('dt-sticky-col');
          col.setAttribute('data-sticky-index', String(idx));
          if (this.options.stickyBackground) col.style.background = this.options.stickyBackground;
        } else {
          col.classList.remove('dt-sticky-col');
          col.removeAttribute('data-sticky-index');
        }
      });
      return;
    }
    rows.forEach(row => {
      const children = Array.from(row.children || row.querySelectorAll(':scope > *'));
      for (let i = 0; i < children.length; i++) {
        const cell = children[i];
        if (!cell) continue;
        if (i < count) {
          if (!cell.classList.contains('dt-sticky-col')) cell.classList.add('dt-sticky-col');
          cell.setAttribute('data-sticky-index', String(i));
          if (this.options.stickyBackground) cell.style.background = this.options.stickyBackground;
        } else {
          if (cell.classList.contains('dt-sticky-col')) cell.classList.remove('dt-sticky-col');
          cell.removeAttribute('data-sticky-index');
          if (this.options.stickyBackground) cell.style.background = '';
        }
      }
    });
  }

  // ------------------ Utilities ------------------
  _throttle(fn, ms) {
    let last = 0, t = null;
    return (...args) => {
      const now = Date.now();
      const run = () => { last = now; fn(...args); };
      clearTimeout(t);
      if (now - last >= ms) run(); else t = setTimeout(run, ms - (now - last));
    };
  }

  _debounce(fn, ms) {
    let t = null;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }
}

// ==================== StickyDataTable convenience wrapper ====================
class StickyDataTable extends DataTable {
    constructor(container, options ) {
        //changeStyle();
        super( container, options );
        this.bodyRenderer = BodyRendererDecorator( this.bodyRenderer );
        this.style._settingHeaderPosition = true;
        this._sm = new StickyManager(this, options);
        this.sticky = this._sm;
    }
    get container() { return this.wrapper; }
    destroy() { if (this._sm) this._sm.destroy(); super.destroy(); }
}

window.StickyDataTable = StickyDataTable;

