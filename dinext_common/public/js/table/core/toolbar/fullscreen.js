const FULLSCREEN_DEFAULTS = {
    enabled: true,
    target: "container"
};

function getDocumentFullscreenElement() {
    if (typeof document === "undefined") {
        return null;
    }
    return document.fullscreenElement
        || document.webkitFullscreenElement
        || document.mozFullScreenElement
        || document.msFullscreenElement
        || null;
}

function getElementFullscreenRequest(element) {
    if (!element) {
        return null;
    }
    return element.requestFullscreen
        || element.webkitRequestFullscreen
        || element.mozRequestFullScreen
        || element.msRequestFullscreen
        || null;
}

function getDocumentFullscreenExit() {
    if (typeof document === "undefined") {
        return null;
    }
    return document.exitFullscreen
        || document.webkitExitFullscreen
        || document.mozCancelFullScreen
        || document.msExitFullscreen
        || null;
}

/**
 * Native Fullscreen API for table container or optional shell element.
 */
export const FullscreenMixin = (Base) => class extends Base {
    initFeatures() {
        super.initFeatures();
        this._fullscreenActive = false;
    }

    afterGridCreated() {
        super.afterGridCreated();
        if (this.isFullscreenEnabled()) {
            this.bindFullscreenListeners();
            this.syncFullscreenState();
        }
    }

    destroyFeatures() {
        this.unbindFullscreenListeners();
        if (this._fullscreenActive) {
            void this.exitFullscreen();
        }
        super.destroyFeatures();
    }

    getFullscreenOptions() {
        return { ...FULLSCREEN_DEFAULTS, ...(this.options.fullscreen || {}) };
    }

    isFullscreenEnabled() {
        if (!this.getFullscreenOptions().enabled) {
            return false;
        }
        const el = this.getFullscreenElement();
        return !!getElementFullscreenRequest(el) && !!getDocumentFullscreenExit();
    }

    getFullscreenElement() {
        const { target, shell } = this.getFullscreenOptions();
        if (target === "shell" && shell) {
            return shell;
        }
        return this.container;
    }

    isFullscreen() {
        return this._fullscreenActive;
    }

    syncFullscreenState() {
        const el = this.getFullscreenElement();
        const active = !!el && getDocumentFullscreenElement() === el;
        this._fullscreenActive = active;
        this.container?.classList.toggle("dinext-table--fullscreen", active);
        this.refreshToolbar?.();
    }

    notifyGridLayoutChanged() {
        requestAnimationFrame(() => {
            window.dispatchEvent(new Event("resize"));
        });
    }

    async enterFullscreen() {
        const el = this.getFullscreenElement();
        const request = getElementFullscreenRequest(el);
        if (!el || !request) {
            return false;
        }

        try {
            await request.call(el);
            this.syncFullscreenState();
            this.notifyGridLayoutChanged();
            return this._fullscreenActive;
        } catch (_err) {
            return false;
        }
    }

    async exitFullscreen() {
        const exit = getDocumentFullscreenExit();
        if (!getDocumentFullscreenElement() || !exit) {
            this.syncFullscreenState();
            return false;
        }

        try {
            await exit.call(document);
            this.syncFullscreenState();
            this.notifyGridLayoutChanged();
            return !this._fullscreenActive;
        } catch (_err) {
            return false;
        }
    }

    async toggleFullscreen() {
        if (this.isFullscreen()) {
            return this.exitFullscreen();
        }
        return this.enterFullscreen();
    }

    bindFullscreenListeners() {
        this.unbindFullscreenListeners();
        this._onFullscreenChange = () => {
            const wasActive = this._fullscreenActive;
            this.syncFullscreenState();
            if (wasActive && !this._fullscreenActive) {
                this.notifyGridLayoutChanged();
            }
        };
        document.addEventListener("fullscreenchange", this._onFullscreenChange);
        document.addEventListener("webkitfullscreenchange", this._onFullscreenChange);
    }

    unbindFullscreenListeners() {
        if (!this._onFullscreenChange) {
            return;
        }
        document.removeEventListener("fullscreenchange", this._onFullscreenChange);
        document.removeEventListener("webkitfullscreenchange", this._onFullscreenChange);
        this._onFullscreenChange = null;
    }

    handleSetOption(key, value) {
        if (key === "fullscreen") {
            this.options.fullscreen = value;
            if (this.isFullscreenEnabled()) {
                this.bindFullscreenListeners();
            } else {
                this.unbindFullscreenListeners();
                void this.exitFullscreen();
            }
            this.syncFullscreenState();
            this.refreshToolbar?.();
            return true;
        }
        return super.handleSetOption?.(key, value) ?? false;
    }
};
