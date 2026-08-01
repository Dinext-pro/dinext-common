<!-- Centrally managed navigation stub for dinext_common. -->

# Dinext Agent Navigation Stub

Этот файл намеренно минимален.

Общие агентные инструкции, навыки и правила для Dinext ведутся централизованно в sibling-репозитории `dinext-docs`.

## Сначала читай отсюда

- `../dinext-docs/agents/registry/index.yaml`
- `../dinext-docs/agents/ide/agents/dinext-frappe-developer-guide.md`
- `../dinext-docs/agents/ide/skills/`
- `../dinext-docs/agents/ide/rules/`
- `../dinext-docs/agents/ide/runtime-access.md`

## Локально в этом приложении допустимы только

- app-specific skills в `.cursor/skills/`, если они относятся только к этому приложению;
- app-specific rules в `.cursor/rules/`, если они относятся только к этому приложению.

Если нужный shared-артефакт отсутствует локально, не создавай его в этом репозитории. Добавляй или обновляй его в `dinext-docs`.

## OpenSpec Store

Планы (proposal / design / specs / tasks) читать и создавать только в центральном Store `dinext-docs`. Локально допустим только `openspec/config.yaml` с `store: dinext-docs`. Реализация кода — в этом репозитории. См. `../dinext-docs/process/development-management/openspec-store.md`.
