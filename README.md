# Dinext Common

Common functionality, branding, and shared assets for the Administrator on Frappe. The app provides global desk scripts, Dinext logos and site configuration via fixtures, and supplies external libraries for Gantt charts, datatables, and charts.

## Installation

Install the app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app dinext_common
```

After installation or upgrade, run migration and build assets so fixtures and scripts apply correctly:

```bash
bench --site your-site.local migrate
bench build --app dinext_common
```

## What is configured at install or migrate

- **Logos and branding**  
  The app expects logo assets under `dinext_common/public/images/` (e.g. `DI_SQ_NBG.png`, `DINEXT_2.png`, `DINEXT_FAVICON.ico`). These paths are used in `hooks.py` (`app_logo_url`, `app_icon`, `website_context`) and in fixtures, so logos appear in the desk navbar, website, and login/splash.

- **Navbar Settings**  
  Fixtures apply the single Navbar Settings record: Dinext app logo, Help menu (e.g. Documentation link, About), and Settings menu (e.g. «Мои замещения»). Data is in `dinext_common/fixtures/navbar_settings.json`.

- **Website Settings and homepage**  
  Fixtures apply the single Website Settings record (brand name «Dinext», banner/brand images, splash image, `home_page` route) and the Web Page used as the site homepage for unauthenticated users (route `homepage`, title «Home Page»). Data is in `dinext_common/fixtures/website_settings.json` and `dinext_common/fixtures/web_page.json`. Website Settings references the **Dinext Theme** (`website_theme`: «Dinext Theme»); the theme is defined in the app as a standard Website Theme doc (e.g. under `dinext_common/website_theme/dinext_theme/`), not exported via fixtures.

## Common functionality provided by the app

Scripts are loaded globally in the desk via `app_include_js` in `hooks.py`, unless noted otherwise.

- **Breadcrumbs** (`breadcrumbs_update.js`)  
  Custom breadcrumb behaviour: keeps the current workspace in the trail, shows DocType and document name, and allows copying the document name from the last crumb.

- **List View column width** (`listview_resize.js`)  
  Resizable columns in all List Views; widths are stored per doctype in `localStorage` and restored on refresh.

- **Sticky DataTable and virtualized body** (`sticky-datatable.js`)  
  Used for the **Project** doctype via `doctype_js` in `hooks.py`. Provides a DataTable with sticky columns and a `BodyRendererDecorator` that uses HyperList for virtualized rendering of large datasets. Loads `frappe-datatable.min.js` and `hyperlist.js` from the app assets when the script runs.

- **About dialog** (`dinext-desk.js`)  
  Replaces the standard Help → About dialog with a «Administrator» dialog that shows installed app versions and supports copying version info to the clipboard.

- **Dashboard card filters** (`dashboard_filters_fix.js`)  
  Adjusts dashboard filters so **Assigned To** (`_assign`) and **Liked By** (`_liked_by`) work with dynamic filtering (e.g. using `like` with wildcards where appropriate).

## External libraries

The app ships the following in `dinext_common/public/js/` (and `dinext_common/public/css/` where noted):

- **Used by the app**  
  - `frappe-datatable.min.js` — used by `sticky-datatable.js` for the Project DataTable.  
  - `hyperlist.js` — used by `sticky-datatable.js` for virtualized row rendering (BodyRendererDecorator).

- **Supplied for use by other code**  
  - `frappe-gantt.umd.js` and `frappe-gantt.css` — for Gantt charts (e.g. task trees). Not loaded in `hooks.py`; load dynamically where needed (e.g. `frappe.require()`).  
  - `echarts.min.js` — for charts. Not loaded in `hooks.py`; load dynamically where needed.

## Compatibility

The app is intended to be used alongside other Frappe/ERPNext apps. It injects global desk scripts and applies single-doctype fixtures (Navbar Settings, Website Settings, Web Page). Using it with other apps that also customize navbar, website, or the same scripts may require coordination of configuration.

## Contributing

This app uses `pre-commit` for code formatting and linting. Install [pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/dinext_common
pre-commit install
```

Pre-commit is configured to use:

- ruff  
- eslint  
- prettier  
- pyupgrade  

## License

MIT
