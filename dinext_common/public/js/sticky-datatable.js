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

function getHyperListRowKey(node) {
    if (!node || node.nodeType !== 1) return null;

    const rowIndex = node.getAttribute('data-row-index');
    if (rowIndex !== null) return String(rowIndex);

    const match = String(node.className || '').match(/\bdt-row-([^\s]+)/);
    return match ? match[1] : null;
}

function syncHyperListRowShell(existingRow, nextRow, patchToken) {
    Array.from(existingRow.attributes).forEach(attr => {
        if (!nextRow.hasAttribute(attr.name)) {
            existingRow.removeAttribute(attr.name);
        }
    });

    Array.from(nextRow.attributes).forEach(attr => {
        if (existingRow.getAttribute(attr.name) !== attr.value) {
            existingRow.setAttribute(attr.name, attr.value);
        }
    });

    existingRow.__hyperListPatchToken = patchToken;
}

function createHyperListApplyPatch(patchToken) {
    return function applyPatch(element, fragment) {
        const existingRows = new Map();
        Array.from(element.children).forEach(child => {
            const key = getHyperListRowKey(child);
            if (key !== null && child.__hyperListPatchToken === patchToken) {
                existingRows.set(key, child);
            }
        });

        const patchedFragment = document.createDocumentFragment();
        Array.from(fragment.childNodes).forEach(nextChild => {
            const key = getHyperListRowKey(nextChild);
            const existingRow = key !== null ? existingRows.get(key) : null;

            if (existingRow) {
                syncHyperListRowShell(existingRow, nextChild, patchToken);
                patchedFragment.appendChild(existingRow);
            } else {
                if (key !== null) nextChild.__hyperListPatchToken = patchToken;
                patchedFragment.appendChild(nextChild);
            }
        });

        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
        element.appendChild(patchedFragment);

        return true;
    };
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
        const patchToken = (this._hyperListPatchToken || 0) + 1;
        this._hyperListPatchToken = patchToken;

        const itemHeight = (
            this.instance.options.dynamicRowHeight &&
            this.instance.options.getDynamicRowHeight
        )
            ? rows.map(row => this.instance.options.getDynamicRowHeight(this.instance, row.meta.rowIndex))
            : (this.instance.options.cellHeight || 0);

        let config = {
            width: computedStyle.width,
            height: computedStyle.height,
            instance: this.instance,
            rows: rows.map( r => r.meta.rowIndex ),
            itemHeight,
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
                if (this.instance._sm && typeof this.instance._sm.scheduleApplyToRenderedRows === 'function') {
                    this.instance._sm.scheduleApplyToRenderedRows();
                }
            },
            applyPatch: createHyperListApplyPatch(patchToken)
        };

        if (this.instance._sm && typeof this.instance._sm.suspendRecalculate === 'function') {
            this.instance._sm.suspendRecalculate();
        }
        try {
            if (!this.hyperlist) {
                this.hyperlist = new HyperList(this.bodyScrollable, config);
            } else {
                this.hyperlist.refresh(this.bodyScrollable, config);
            }
        } finally {
            if (this.instance._sm && typeof this.instance._sm.resumeRecalculate === 'function') {
                this.instance._sm.resumeRecalculate(false);
            }
        }
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
    - table.setStickyColumnsCount(3) / table.sticky.setStickyColumnsCount(3) для изменения количества
      липких колонок без пересоздания таблицы.

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
    this._destroyed = false;
    this._suspendDepth = 0;
    this._pendingRecalculate = false;
    this._pendingApply = false;
    this._recalculateRaf = null;
    this._recalculateTimer = null;
    this._applyRaf = null;
    this._syncRaf = null;
    this._lastGeneratedRules = '';

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
        if (this._destroyed || !this.datatable || !this.datatable.style) return;
        this.scheduleRecalculate();
        try {
          this.datatable.style.onWindowResize();
        } catch (e) {
          if (!e || !/cssRules/.test(String(e.message || e))) throw e;
        }
      });
      this._ro.observe(this.el);
    } catch (e) { /* noop */ }

    // MutationObserver mostly sees virtualized row replacement, so keep it light.
    this._mo = new MutationObserver(this._throttle(() => this.scheduleApplyToRenderedRows(), this.options.minRenderInterval));
    this._connectMutationObserver();
    
    $(this.datatable.bodyScrollable).on('scroll', (e) => {
        this.scheduleSyncHeaderFooter();
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
        try {
            return Reflect.apply(originalSetWidth, this, args);
        } catch (e) {
            if (!e || !/cssRules/.test(String(e.message || e))) throw e;
        }
    };

    // hook into datatable public events (options.events)
    this._attachToDataTableEvents();
  }

  destroy() {
    this._destroyed = true;
    window.removeEventListener('resize', this._onWindowResize);
    if (this._ro) this._ro.disconnect();
    if (this._mo) this._mo.disconnect();
    if (this._recalculateTimer) clearTimeout(this._recalculateTimer);
    if (this._recalculateRaf) cancelAnimationFrame(this._recalculateRaf);
    if (this._applyRaf) cancelAnimationFrame(this._applyRaf);
    if (this._syncRaf) cancelAnimationFrame(this._syncRaf);
    this._detachFromDataTableEvents();
  }

  suspendRecalculate() {
    if (this._destroyed) return;
    this._suspendDepth += 1;
    if (this._mo) this._mo.disconnect();
  }

  resumeRecalculate(flush = true) {
    if (this._destroyed) return;
    this._suspendDepth = Math.max(0, this._suspendDepth - 1);
    if (this._suspendDepth > 0) return;
    this._connectMutationObserver();

    if (flush && this._pendingRecalculate) {
      this._pendingRecalculate = false;
      this.scheduleRecalculate(true);
      return;
    }

    if (this._pendingApply) {
      this._pendingApply = false;
      this.scheduleApplyToRenderedRows();
    }
  }

  _connectMutationObserver() {
    if (!this._mo || !this.el || this._destroyed || this._suspendDepth > 0) return;
    try {
      this._mo.observe(this.el, { childList: true, subtree: true });
    } catch (e) { /* noop */ }
  }

  scheduleRecalculate(immediate = false) {
    if (this._destroyed) return;
    if (this._suspendDepth > 0) {
      this._pendingRecalculate = true;
      return;
    }
    const now = performance.now();
    const elapsed = now - this._lastRender;
    if (!immediate && elapsed < this.options.minRenderInterval) {
      if (!this._recalculateTimer) {
        this._recalculateTimer = setTimeout(() => {
          this._recalculateTimer = null;
          this.scheduleRecalculate(true);
        }, this.options.minRenderInterval - elapsed);
      }
      return;
    }
    if (this._recalculateRaf) return;
    this._recalculateRaf = requestAnimationFrame(() => {
      this._recalculateRaf = null;
      this._lastRender = performance.now();
      this.recalculate();
    });
  }

  scheduleApplyToRenderedRows() {
    if (this._destroyed) return;
    if (this._suspendDepth > 0) {
      this._pendingApply = true;
      return;
    }
    if (this._applyRaf) return;
    this._applyRaf = requestAnimationFrame(() => {
      this._applyRaf = null;
      this.applyToRenderedRows();
    });
  }

  scheduleSyncHeaderFooter() {
    if (this._destroyed || this._syncRaf) return;
    this._syncRaf = requestAnimationFrame(() => {
      this._syncRaf = null;
      this._syncHeaderFooterScroll();
    });
  }

  setStickyColumnsCount(count) {
    if (this._destroyed) return this._stickyCount || 0;
    const parsedCount = Number.isFinite(Number(count)) ? Math.trunc(Number(count)) : 0;
    const columns = this.datatable ? this._getColumnDefs() : null;
    const maxCount = Array.isArray(columns) ? columns.length : parsedCount;
    const nextCount = Math.max(0, Math.min(maxCount, parsedCount));
    this.options.stickyColumnsCount = nextCount;
    if (this.datatable && this.datatable.options) {
      this.datatable.options.stickyColumnsCount = nextCount;
    }
    if (!this._destroyed && this.datatable && this.el) {
      this.scheduleRecalculate(true);
    }
    return nextCount;
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
    if (this._destroyed || !this.datatable || !this.el) return;
    const columns = this._getColumnDefs();
    const stickyCount = this._resolveStickyCount(columns);
    this._stickyCount = stickyCount;
    const lefts = this._computeLeftOffsets(stickyCount);
    this._lefts = lefts;
    // update generated stylesheet with left rules
    this._updateGeneratedStylesheet(lefts);
    // apply attribute/class to header and to currently rendered rows
    this._applyStickyToAllRows(stickyCount);
    this._syncHeaderFooterScroll();
  }

  applyToRenderedRows() {
    if (this._destroyed || !this.datatable || !this.el) return;
    this._applyStickyToAllRows(this._stickyCount);
    this._syncHeaderFooterScroll();
  }

  _syncHeaderFooterScroll() {
    if (this._destroyed || !this.datatable || !this.datatable.bodyScrollable) return;
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
    if (rules === this._lastGeneratedRules) return;
    this._lastGeneratedRules = rules;
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
      for (let i = 0; i < count && i < children.length; i++) {
        const cell = children[i];
        if (!cell) continue;
        if (!cell.classList.contains('dt-sticky-col')) cell.classList.add('dt-sticky-col');
        if (cell.getAttribute('data-sticky-index') !== String(i)) {
          cell.setAttribute('data-sticky-index', String(i));
        }
        if (this.options.stickyBackground) cell.style.background = this.options.stickyBackground;
      }

      const staleStickyCells = row.querySelectorAll('.dt-sticky-col');
      staleStickyCells.forEach(cell => {
        const idx = parseInt(cell.getAttribute('data-sticky-index'), 10);
        if (isNaN(idx) || idx >= count) {
          if (cell.classList.contains('dt-sticky-col')) cell.classList.remove('dt-sticky-col');
          cell.removeAttribute('data-sticky-index');
          if (this.options.stickyBackground) cell.style.background = '';
        }
      });
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
        options = Object.assign({ dynamicRowHeight: false }, options || {});
        super( container, options );
        this.bodyRenderer = BodyRendererDecorator( this.bodyRenderer );
        this.style._settingHeaderPosition = true;
        this._sm = new StickyManager(this, options);
        this.sticky = this._sm;
        this._stickyRefreshState = {
            dataSnapshot: Array.isArray(options.data) ? options.data.slice() : [],
            dataLength: Array.isArray(options.data) ? options.data.length : 0,
            columnsSignature: this._getColumnsSignature(this.options && this.options.columns)
        };
    }
    get container() { return this.wrapper; }
    refresh(data, columns) {
        const state = this._stickyRefreshState;
        const canAppendOnly = this._canAppendOnlyRefresh(data, columns);

        if (canAppendOnly) {
            const rowsToAppend = data.slice(state.dataLength);
            const result = this._withStickySuspended(() => this.appendRows(rowsToAppend), false);
            if (this.datamanager) this.datamanager.data = data;
            if (this.options) this.options.data = data;
            this._rememberRefreshState(data, columns);
            if (this._sm) this._sm.scheduleApplyToRenderedRows();
            return result;
        }

        const result = this._withStickySuspended(() => super.refresh(data, columns), true);
        this._rememberRefreshState(data || (this.options && this.options.data) || [], columns);
        return result;
    }

    appendRows(rows) {
        const result = this._withStickySuspended(() => super.appendRows(rows), false);
        const currentRows = this.getRows ? this.getRows() : [];
        this._stickyRefreshState = this._stickyRefreshState || {};
        this._stickyRefreshState.dataLength = Array.isArray(currentRows) ? currentRows.length : 0;
        if (this._sm) this._sm.scheduleApplyToRenderedRows();
        return result;
    }

    setStickyColumnsCount(count) {
        if (!this._sm || typeof this._sm.setStickyColumnsCount !== 'function') return 0;
        return this._sm.setStickyColumnsCount(count);
    }
    destroy() { if (this._sm) this._sm.destroy(); super.destroy(); }

    _withStickySuspended(fn, flush = true) {
        if (!this._sm || typeof this._sm.suspendRecalculate !== 'function') {
            return fn();
        }
        this._sm.suspendRecalculate();
        try {
            return fn();
        } finally {
            this._sm.resumeRecalculate(flush);
        }
    }

    _canAppendOnlyRefresh(data, columns) {
        const state = this._stickyRefreshState;
        if (!state || !Array.isArray(data) || state.dataLength <= 0 || data.length <= state.dataLength) {
            return false;
        }
        if (typeof super.appendRows !== 'function' && typeof this.appendRows !== 'function') {
            return false;
        }

        const nextColumnsSignature = this._getColumnsSignature(columns || (this.options && this.options.columns));
        if (state.columnsSignature !== nextColumnsSignature) {
            return false;
        }

        for (let i = 0; i < state.dataLength; i++) {
            if (data[i] !== state.dataSnapshot[i]) {
                return false;
            }
        }

        return true;
    }

    _rememberRefreshState(data, columns) {
        const currentData = Array.isArray(data) ? data : [];
        this._stickyRefreshState = {
            dataSnapshot: currentData.slice(),
            dataLength: currentData.length,
            columnsSignature: this._getColumnsSignature(columns || (this.options && this.options.columns))
        };
    }

    _getColumnsSignature(columns) {
        if (!Array.isArray(columns)) return '';
        return columns.map(column => {
            if (column == null) return '';
            if (typeof column !== 'object') return String(column);
            return [
                column.id,
                column.name,
                column.content,
                column.width,
                column.align,
                column.format ? 'format' : '',
                column.sticky,
                column.editable,
                column.resizable,
                column.focusable,
                column.dropdown
            ].join(':');
        }).join('|');
    }
}

window.StickyDataTable = StickyDataTable;

