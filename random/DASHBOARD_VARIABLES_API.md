# Dashboard Variables — Backend API Reference (for Frontend)

Backend reference for implementing the Dashboard Variables UI (Create / Display / Apply / Edit).
All shapes below are taken directly from the Go models and handlers.

## 1. Conventions

- **Base path:** all routes are under `/dashboards`. (Local dev server: `http://localhost:8095`.)
- **Auth:** every request needs `Authorization: Bearer <JWT>`. The JWT is workspace-scoped; the
  server rejects tokens whose `workspaceId` differs from the server workspace.
- **Content type:** `Content-Type: application/json` for bodies.
- **Roles** (rank): `ADMIN(4) > EDITOR(3) > VIEWER(2) > VISITOR(1)`.
  - **Config** endpoints (create/update/duplicate/delete/reorder/impact) require **EDITOR+**.
  - **View-mode** endpoints (apply value, resolve values) require **VIEWER+** (handler checks
    "Visitor", but a pure VISITOR token is only accepted in playground mode — treat the effective
    minimum as VIEWER for normal app users).
  - **Reading** a dashboard (which includes its variables) requires any authenticated workspace user.
- **Error shape:** all errors return `{ "error": "<message>" }` with an appropriate status code.
- **Timestamps:** `from`/`to` query params are **unix seconds**.

## 2. Key concepts the frontend owns

These are intentionally NOT done by the backend:

1. **Runtime substitution.** Panel SQL is stored with literal `{{name}}` placeholders. Before
   sending a panel query to the query endpoints, the frontend replaces each `{{name}}` with the
   variable's selected value, formatted by `outputFormat`:
   - `string` → wrap in single quotes: `{{country}}` → `'US'`
   - `number` → raw: `{{percentile}}` → `90`
   - `identifier` → unquoted: `{{col}}` → `country`
2. **Multi-value** (`multiValue: true`): multiple selected values. Recommended injection is an
   `IN (...)` list with each element formatted per `outputFormat`
   (e.g. string → `IN ('A','B')`, number → `IN (1,2)`).
3. **Include toggle** (`include: false`): the frontend must drop that variable's predicate from
   the query for the session.
4. **Missing-variable fallback:** if a panel references a `{{name}}` that no longer exists, run the
   query without that filter (don't error).
5. **Shared runtime state is stored in the BACKEND (not client-side).** `selectedValue` (the
   current/last-used value) and `include` are persisted **on the dashboard document, scoped to the
   dashboard** — i.e. **general to the dashboard, shared by everyone viewing it**, NOT per-user and
   NOT in localStorage. The frontend persists them by calling the apply-value endpoint (#7) and
   reads them back from the dashboard (#1); on load, restore the bar from these stored values.
6. **Display rules:** hide variables with `hideOnBar: true` in view mode; show them (with a hidden
   indicator) in edit mode. Chip label = `displayName` (falls back to `name`). Chip value =
   `selectedValue` if set, else `defaultValue`, else empty.

## 3. The Variable object

Returned by create/duplicate/apply and embedded in the dashboard's `variables[]`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Server-assigned (24-char hex). |
| `name` | string | Identifier used in `{{name}}`. Unique per dashboard (case-insensitive). Pattern `^[A-Za-z_][A-Za-z0-9_]*$`, ≤64 chars, no spaces. |
| `displayName` | string | Label for the chip. Defaults to `name` if omitted. |
| `type` | enum | `query` \| `list` \| `textField`. |
| `outputFormat` | enum | `string` \| `number` \| `identifier`. Default `string`. |
| `hideOnBar` | bool | Hidden in view mode when true. |
| `multiValue` | bool | Multi-select allowed when true. |
| `defaultValue` | string[] | Pre-selected value(s). |
| `order` | int | Position in the bar (ascending). |
| `query` | string | (type=query) SQL whose first column populates the dropdown. |
| `streamName` | string | (type=query) dataset the SQL targets. |
| `telemetryType` | string | (type=query) `logs` \| `metrics` \| `traces`. |
| `ignoreTimePicker` | bool | (type=query) true → always last 1h; false → use dashboard time. Default true. |
| `listValues` | string[] | (type=list) the comma-separated values. |
| `selectedValue` | string[] | Persisted shared selection (runtime). |
| `include` | bool | Persisted "Include variable" toggle. Default true. |

> Legacy fields `dataType`, `dataset`, `attribute` may appear on old documents; ignore them for new UI.

### Enums
- `type`: `"query"`, `"list"`, `"textField"`
- `outputFormat`: `"string"`, `"number"`, `"identifier"`

### Example variable
```json
{
  "id": "6a3a21b4a999f0e660bcaaeb",
  "name": "select_host",
  "displayName": "Host",
  "type": "query",
  "outputFormat": "string",
  "hideOnBar": false,
  "multiValue": false,
  "defaultValue": ["host-1"],
  "order": 0,
  "query": "SELECT DISTINCT hostname FROM staging_engine",
  "streamName": "staging_engine",
  "telemetryType": "logs",
  "ignoreTimePicker": true,
  "selectedValue": ["host-1"],
  "include": true
}
```

## 4. Endpoint summary

| # | Method | Path | Role | Purpose |
|---|--------|------|------|---------|
| 1 | GET | `/dashboards/{dashboardId}` | any | Read dashboard incl. `variables[]` |
| 2 | POST | `/dashboards/{dashboardId}/variables` | EDITOR | Create variable |
| 3 | PUT | `/dashboards/{dashboardId}/variables/reorder` | EDITOR | Reorder variables |
| 4 | PUT | `/dashboards/{dashboardId}/variables/{variableId}` | EDITOR | Update variable (may rename) |
| 5 | POST | `/dashboards/{dashboardId}/variables/{variableId}/duplicate` | EDITOR | Duplicate variable |
| 6 | DELETE | `/dashboards/{dashboardId}/variables/{variableId}` | EDITOR | Delete variable |
| 7 | PUT | `/dashboards/{dashboardId}/variables/{variableId}/value` | VIEWER | Apply value / toggle include (view-mode) |
| 8 | GET | `/dashboards/{dashboardId}/variables/{variableId}/impact` | EDITOR | List panels referencing the variable |
| 9 | GET | `/dashboards/{dashboardId}/variables/{variableId}/values?from&to` | VIEWER | Resolve dropdown values |

> Note: `/variables/reorder` is matched before `/variables/{variableId}`; `reorder` is reserved.

## 5. Endpoint details

### 1) Read dashboard (variables embedded)
`GET /dashboards/{dashboardId}` → `200`
Returns the full dashboard; variables are in `variables[]` (sorted by `order`), each with current
`selectedValue`/`include`. Use this on dashboard load to render the variable bar.

### 2) Create variable
`POST /dashboards/{dashboardId}/variables` → `201` returns the created **Variable object**.

Request body (`CreateDashboardVariableRequest`):
```json
{
  "name": "select_host",
  "displayName": "Host",
  "type": "query",
  "outputFormat": "string",
  "hideOnBar": false,
  "multiValue": false,
  "defaultValue": ["host-1"],
  "query": "SELECT DISTINCT hostname FROM staging_engine",
  "streamName": "staging_engine",
  "telemetryType": "logs",
  "ignoreTimePicker": true,
  "listValues": []
}
```
Field rules / defaults applied by server: `type` defaults `query`; `outputFormat` defaults
`string`; `ignoreTimePicker` defaults `true` (query); `include` set `true`; `selectedValue` seeded
from `defaultValue`; `order` = end of list.
Type-specific required fields: `query` non-empty for `type=query`; `listValues` non-empty for
`type=list`; `textField` needs neither.

Errors: `400` validation (e.g. `{"error":"Field is required"}` for empty query, bad name),
`409` duplicate name, `403` not editor / preset, `404` dashboard not found.

### 3) Reorder variables
`PUT /dashboards/{dashboardId}/variables/reorder` → `200` `{ "message": "..." }`

Body (`ReorderDashboardVariablesRequest`) — must be a full permutation of existing ids:
```json
{ "order": ["id3", "id1", "id2"] }
```
Errors: `400` if `order` isn't exactly the existing id set (length / unknown id / duplicate).

### 4) Update variable
`PUT /dashboards/{dashboardId}/variables/{variableId}` → `200`

Body (`UpdateDashboardVariableRequest`) — partial; send only changed fields. Renaming via `name`
rewrites `{{old}}`→`{{new}}` in all referencing panel queries.
```json
{ "displayName": "Hostname", "name": "select_hostname", "multiValue": true }
```
Response envelope:
```json
{
  "variable": { "...": "the updated Variable object" },
  "renamedPanelsUpdated": 1
}
```
Use `renamedPanelsUpdated` for the toast (e.g. "Variable updated; 1 panel updated").
Errors: `400` validation, `409` duplicate name, `404` variable/dashboard not found, `403` preset.

### 5) Duplicate variable
`POST /dashboards/{dashboardId}/variables/{variableId}/duplicate` → `201` returns the new
**Variable object**. Name auto-suffixed (`<name>_copy`, then `_copy_2`, …); appended at end.

### 6) Delete variable
`DELETE /dashboards/{dashboardId}/variables/{variableId}` → `200` `{ "message": "..." }`
Removes the variable only; panel queries keep their `{{name}}` (frontend applies the
missing-variable fallback). Call endpoint #8 first to warn about affected panels.

### 7) Apply value / toggle include (view-mode)
`PUT /dashboards/{dashboardId}/variables/{variableId}/value` → `200` returns updated **Variable object**.

Body (`ApplyVariableValueRequest`) — `include` optional (omit to leave unchanged):
```json
{ "selectedValue": ["host-2"], "include": true }
```
Used for: selecting a value (single or multi), "Reset to default" (send `selectedValue` =
`defaultValue`), and the Include toggle (send `include`). Writes only this variable's runtime
fields (safe under concurrent applies). Allowed for VIEWER+ (no editor needed).
For a Text Field variable, send the typed string as `{"selectedValue":["typed text"]}`.

### 8) Delete impact (affected panels)
`GET /dashboards/{dashboardId}/variables/{variableId}/impact` → `200`
```json
{ "affectedPanels": [ { "panelId": "6a..f0", "title": "Errors by host", "tabId": 0 } ] }
```
Drive the delete-confirmation dialog with this. Empty `affectedPanels` = safe to delete.

### 9) Resolve dropdown values
`GET /dashboards/{dashboardId}/variables/{variableId}/values?from=<sec>&to=<sec>` → `200`
```json
{ "values": ["host-1", "host-2", "host-3"] }
```
Behaviour by type:
- `query`: runs the SQL against the lake, returns the **first column**, capped at **10** values.
  Time window = last 1h when `ignoreTimePicker` is true (or `from`/`to` omitted); otherwise the
  provided `from`/`to` (unix seconds). Call this when the user opens the dropdown / default-value
  picker (on demand — no auto-run while typing).
- `list`: returns `listValues` as-is.
- `textField`: returns `[]` (no dropdown).

Errors: `400` invalid SQL (`{"error":"invalid SQL syntax: ..."}`) or empty query
(`{"error":"Field is required"}`); `404` not found; `504` on lake timeout.

## 6. Status codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created (create/duplicate) |
| 400 | Validation error / bad params |
| 401 | Missing/invalid JWT |
| 403 | Insufficient role or preset dashboard (read-only) |
| 404 | Dashboard or variable not found |
| 409 | Duplicate variable name |
| 500 | Server error |
| 504 | Lake query timeout (resolve values) |

## 7. Frontend flow → endpoint map

| PRD flow | Endpoints |
|----------|-----------|
| Create sidepanel (Query/List/Text) | `POST .../variables`; default-value dropdown uses `GET .../{id}/values` |
| Variable bar render on load | `GET /dashboards/{id}` → `variables[]` (respect `hideOnBar`, `order`) |
| Apply dropdown / text input | `GET .../{id}/values` (open), `PUT .../{id}/value` (select / include / reset) |
| Edit mode → Edit | `PUT .../{id}` (use `renamedPanelsUpdated` for toast) |
| Edit mode → Duplicate | `POST .../{id}/duplicate` |
| Edit mode → Delete | `GET .../{id}/impact` then `DELETE .../{id}` |
| Edit mode → Reorder (drag) | `PUT .../variables/reorder` on "Done editing" |
| Panel query execution | Frontend substitutes `{{name}}` per `outputFormat`/`multiValue`/`include`; missing var → drop predicate |
