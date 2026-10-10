'use strict';

const Shell = imports.gi.Shell;
const AppDisplay = imports.ui.appDisplay;
const Main = imports.ui.main;
const APP_ID = 'vncming.desktop';

class Extension {
    enable() {
        this._original = AppDisplay.AppDisplay.prototype._loadApps;
        const original = this._original;
        this._replacement = function (...args) {
            const icons = original.apply(this, args);
            if (icons.some(icon => icon.id === APP_ID))
                return icons;
            const app = Shell.AppSystem.get_default().lookup_app(APP_ID);
            if (!app || !this._appFavorites.isFavorite(APP_ID))
                return icons;
            const info = app.get_app_info();
            if (!info.should_show() || !this._parentalControlsManager.shouldShowApp(info))
                return icons;
            if (!this._appInfoList.some(item => item.get_id() === APP_ID))
                this._appInfoList.push(info);
            let icon = this._items.get(APP_ID);
            if (!icon) {
                const isDraggable = global.settings.is_writable('favorite-apps') ||
                    global.settings.is_writable('app-picker-layout');
                icon = new AppDisplay.AppIcon(app, { isDraggable });
                icon.connect('notify::pressed', () => {
                    if (icon.pressed)
                        this.updateDragFocus(icon);
                });
            }
            icons.push(icon);
            return icons;
        };
        AppDisplay.AppDisplay.prototype._loadApps = this._replacement;
        this._refresh();
    }

    disable() {
        if (AppDisplay.AppDisplay.prototype._loadApps === this._replacement)
            AppDisplay.AppDisplay.prototype._loadApps = this._original;
        this._refresh();
        this._replacement = null;
        this._original = null;
    }

    _refresh() {
        const display = Main.overview._overview.controls._appDisplay;
        if (display)
            display._redisplay();
    }
}

function init() {
    return new Extension();
}
