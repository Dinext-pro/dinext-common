# GitHub validation

Checks run on pull requests and maintained branches using the public Dinext validation support, or the private owning repository for Docs and Control Center. App unit tests use a disposable bench with local MariaDB and Redis. CI receives no production credentials.

Imported upstream workflows are retained under `imported-workflows-disabled` for review. Deployment, publishing, live production smoke checks, paid agents and external notifications remain disabled. The private migration archive retains source settings and CI records.

For app tests, the Actions log records the source and support revisions. The portable select-control wheel retains its existing package checks; CRM retains its frontend unit tests.

## External fork reference namespace

Company-maintained external fork branches use exactly one `dinext/` prefix, including `dinext/main/<line>`, `dinext/vendor/<line>` and `dinext/feature/<task>`. Trusted admission permits only the exact integration lines in `development-repositories.json`. During migration, exact legacy targets are accepted only while GitHub reports an unprefixed default branch; renaming the default ends that repository's legacy allowance. External contributors may use their own branch names, including `patch-1`; compatibility and Cypress evidence must still succeed for the current revision.

Future fork release preparation accepts `dinext/<upstream-tag>` or `dinext/<upstream-tag>-dinext.N`. The prefix is part of the Git ref, not the application version or upstream version. `historical-tag-aliases.json` is a separate exact object allowlist for existing release aliases; it cannot authorize a new version. Preparation remains read-only. Existing tags, signed tag objects, Releases and installed commits remain unchanged. Raven's accepted current line is `dinext/main/v3`; the prior v2 dependency pin is retained separately and is never used as an implicit current-version update.

After migration, the trusted registry contains only the exact current `dinext/main/*` lines. Historical Frappe v16 is retained read-only: it contains pure upstream publishing workflows and has no activated Dinext acceptance profile. It requires a separate reviewed compatibility/CI activation before further work; namespace migration does not enable it.
