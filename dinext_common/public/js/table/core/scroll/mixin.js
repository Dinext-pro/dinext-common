/**
 * Dual horizontal scroll: top bar synced with AG `.ag-body-horizontal-scroll`.
 * Center viewport only — pinned columns use spacers, no extra bar.
 */

export const ScrollMixin = (Base) => class extends Base {
    afterGridCreated() {
        super.afterGridCreated();
        this.mountTopHorizontalScroll();
    }

    destroyFeatures() {
        this.destroyTopHorizontalScroll();
        super.destroyFeatures();
    }

    buildScrollGridOptions() {
        return {
            onBodyScroll: (event) => {
                if (event?.direction === "horizontal") {
                    this.syncTopHorizontalScrollFromBody();
                }
            },
            onGridSizeChanged: () => this.syncTopHorizontalScrollLayout(),
            onColumnResized: () => this.syncTopHorizontalScrollLayout(),
            onDisplayedColumnsChanged: () => this.syncTopHorizontalScrollLayout(),
            onFirstDataRendered: () => this.syncTopHorizontalScrollLayout()
        };
    }

    getBodyHorizontalScrollViewport() {
        return this.container?.querySelector?.(".ag-body-horizontal-scroll-viewport") || null;
    }

    mountTopHorizontalScroll() {
        this.destroyTopHorizontalScroll();
        const root = this.container?.querySelector?.(".ag-root");
        const header = root?.querySelector?.(".ag-header");
        if (!root || !header) {
            return;
        }

        const top = document.createElement("div");
        top.className = "dinext-table-hscroll-top";
        top.setAttribute("aria-hidden", "true");
        top.innerHTML = [
            '<div class="dinext-table-hscroll-top-spacer dinext-table-hscroll-top-spacer--left"></div>',
            '<div class="dinext-table-hscroll-top-viewport">',
            '<div class="dinext-table-hscroll-top-content"></div>',
            "</div>",
            '<div class="dinext-table-hscroll-top-spacer dinext-table-hscroll-top-spacer--right ag-scroller-corner"></div>'
        ].join("");

        header.after(top);
        this._hscrollTopEl = top;
        this._hscrollTopViewport = top.querySelector(".dinext-table-hscroll-top-viewport");
        this._hscrollTopContent = top.querySelector(".dinext-table-hscroll-top-content");
        this._hscrollTopLeft = top.querySelector(".dinext-table-hscroll-top-spacer--left");
        this._hscrollTopRight = top.querySelector(".dinext-table-hscroll-top-spacer--right");
        this._hscrollSyncing = false;

        this._onTopHScroll = () => {
            if (this._hscrollSyncing) {
                return;
            }
            const bodyViewport = this.getBodyHorizontalScrollViewport();
            if (!bodyViewport || !this._hscrollTopViewport) {
                return;
            }
            this._hscrollSyncing = true;
            bodyViewport.scrollLeft = this._hscrollTopViewport.scrollLeft;
            this._hscrollSyncing = false;
        };
        this._hscrollTopViewport.addEventListener("scroll", this._onTopHScroll, { passive: true });

        this.syncTopHorizontalScrollLayout();
        requestAnimationFrame(() => this.syncTopHorizontalScrollLayout());
        if (typeof ResizeObserver === "function") {
            this._hscrollResizeObserver = new ResizeObserver(() => {
                this.syncTopHorizontalScrollLayout();
            });
            // Viewport size often stays put while *content* width changes.
            // Observing the outer scroller missed first layout → bar stayed is-idle
            // until a later reflow (filter row / window resize).
            const observe = [
                ".ag-body-horizontal-scroll-container",
                ".ag-center-cols-container",
                ".ag-center-cols-viewport",
                ".ag-pinned-left-header",
                ".ag-header"
            ];
            for (const sel of observe) {
                const el = this.container.querySelector(sel);
                if (el) {
                    this._hscrollResizeObserver.observe(el);
                }
            }
        }
    }

    syncTopHorizontalScrollLayout() {
        if (!this._hscrollTopEl) {
            return;
        }
        const bodyViewport = this.getBodyHorizontalScrollViewport();
        const bodyContent = this.container?.querySelector?.(".ag-body-horizontal-scroll-container");
        if (!bodyViewport || !bodyContent) {
            return;
        }

        const left = this.container.querySelector(".ag-horizontal-left-spacer");
        const right = this.container.querySelector(".ag-horizontal-right-spacer");
        if (this._hscrollTopLeft) {
            this._hscrollTopLeft.style.width = `${left?.offsetWidth || 0}px`;
        }
        if (this._hscrollTopRight) {
            this._hscrollTopRight.style.width = `${right?.offsetWidth || 0}px`;
        }
        const contentWidth = bodyContent.scrollWidth || bodyContent.offsetWidth || 0;
        if (this._hscrollTopContent) {
            this._hscrollTopContent.style.width = `${contentWidth}px`;
        }

        const overflow = bodyViewport.scrollWidth > bodyViewport.clientWidth + 1;
        this._hscrollTopEl.classList.toggle("is-idle", !overflow);
        this.syncTopHorizontalScrollFromBody();
    }

    syncTopHorizontalScrollFromBody() {
        if (this._hscrollSyncing || !this._hscrollTopViewport) {
            return;
        }
        const bodyViewport = this.getBodyHorizontalScrollViewport();
        if (!bodyViewport) {
            return;
        }
        this._hscrollSyncing = true;
        this._hscrollTopViewport.scrollLeft = bodyViewport.scrollLeft;
        this._hscrollSyncing = false;
    }

    destroyTopHorizontalScroll() {
        this._hscrollResizeObserver?.disconnect();
        this._hscrollResizeObserver = null;
        if (this._hscrollTopViewport && this._onTopHScroll) {
            this._hscrollTopViewport.removeEventListener("scroll", this._onTopHScroll);
        }
        this._onTopHScroll = null;
        this._hscrollTopEl?.remove();
        this._hscrollTopEl = null;
        this._hscrollTopViewport = null;
        this._hscrollTopContent = null;
        this._hscrollTopLeft = null;
        this._hscrollTopRight = null;
    }
};
