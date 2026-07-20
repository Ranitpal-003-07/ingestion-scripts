# Dashboard Variables — Test Report

**Feature:** Dashboard Variables (Create / Display / Apply / Edit)
**Date:** 2026-06-23
**Result:** **72 / 72 PASS** (0 failed)

| Suite | Type | Cases | Pass | Fail |
|-------|------|-------|------|------|
| Sheet A | Automated (`go test`) | 60 | 60 | 0 |
| Sheet B | Live integration (server + Lake + Mongo) | 12 | 12 | 0 |
| **Total** | | **72** | **72** | **0** |

Environment for Sheet B: live `seeker` on `:8095`, workspace `d796dc5d-…`, real Lake (`staging.ctrlb.dev`), live Mongo, dataset `staging_engine` (logs).
Quality gates: `go build ./...` ✅ · `go vet` ✅ (only a pre-existing unrelated prometheus warning).

---

## Sheet A — Automated tests

### A1. Service: variable validation & helpers (`internal/services/dashboards_variables_test.go`)

| # | Test case | Result |
|---|-----------|--------|
| 1 | Valid query variable accepted | ✅ PASS |
| 2 | Empty name rejected | ✅ PASS |
| 3 | Name with space rejected | ✅ PASS |
| 4 | Name starting with digit rejected | ✅ PASS |
| 5 | Query type with empty query → "Field is required" | ✅ PASS |
| 6 | Invalid type rejected | ✅ PASS |
| 7 | Invalid output format rejected | ✅ PASS |
| 8 | List type without values rejected | ✅ PASS |
| 9 | List type with values accepted | ✅ PASS |
| 10 | Text Field needs no query/list | ✅ PASS |
| 11 | Name length: 64 chars ok, 65 rejected | ✅ PASS |
| 12 | Whitespace-only query → "Field is required" | ✅ PASS |
| 13 | Duplicate name case-insensitive (`action`/`Action`) → conflict | ✅ PASS |
| 14 | `variableNameTaken` excludes self, case-insensitive | ✅ PASS |
| 15 | Duplicate copy-name suffixing (`_copy`, `_copy_2`) | ✅ PASS |
| 16 | Default normalization (trim, DisplayName, type, format) | ✅ PASS |
| 17 | `findDashboardVariable` hit / miss / nil slice | ✅ PASS |
| 18 | Reorder normalization sorts by `order`; nil-safe | ✅ PASS |
| 19 | Reorder validation: valid perm / length / unknown id / duplicate id | ✅ PASS |
| 20 | Time window: explicit / ignore→1h / invalid→1h / inverted passthrough | ✅ PASS |
| 21 | Value extraction: single-col, multi-col deterministic, nil/non-map skip, limit cap, numeric, empty | ✅ PASS |

### A2. Utils: placeholder matching — rename & delete-impact core (`internal/utils/variableplaceholder_test.go`)

| # | Test case | Result |
|---|-----------|--------|
| 22 | Match `{{action}}` | ✅ PASS |
| 23 | Match `{{ action }}` (internal whitespace) | ✅ PASS |
| 24 | No match when placeholder absent | ✅ PASS |
| 25 | Empty name never matches | ✅ PASS |
| 26 | Prefix `{{action_2}}` is NOT a match for `action` | ✅ PASS |
| 27 | Suffix `{{my_action}}` is NOT a match | ✅ PASS |
| 28 | Case-sensitive (`{{Action}}` ≠ `action`) | ✅ PASS |
| 29 | Multiple occurrences detected | ✅ PASS |
| 30 | Regex-special name (`a.b`) escaped & matched | ✅ PASS |
| 31 | Special-char name does not wildcard-match (`axb`) | ✅ PASS |
| 32 | Rename: simple `{{old}}`→`{{new}}` | ✅ PASS |
| 33 | Rename: whitespace normalized | ✅ PASS |
| 34 | Rename: multiple occurrences | ✅ PASS |
| 35 | Rename: prefix `{{old_2}}` untouched | ✅ PASS |
| 36 | Rename: no-match left unchanged | ✅ PASS |
| 37 | Rename: empty old name is a no-op | ✅ PASS |
| 38 | Rename: case-sensitive (`{{Old}}` untouched) | ✅ PASS |

### A3. Handlers: HTTP auth & validation (`internal/api/handlers/dashboards_variables_test.go`)

| # | Test case | Result |
|---|-----------|--------|
| 39 | Create: non-Editor → 403 | ✅ PASS |
| 40 | Create: missing dashboardId → 400 | ✅ PASS |
| 41 | Create: malformed JSON → 400 | ✅ PASS |
| 42 | Update: non-Editor → 403 | ✅ PASS |
| 43 | Update: missing variableId → 400 | ✅ PASS |
| 44 | Update: malformed JSON → 400 | ✅ PASS |
| 45 | Duplicate: non-Editor → 403 | ✅ PASS |
| 46 | Duplicate: missing variableId → 400 | ✅ PASS |
| 47 | Delete: non-Editor → 403 | ✅ PASS |
| 48 | Delete: missing variableId → 400 | ✅ PASS |
| 49 | Impact: non-Editor → 403 | ✅ PASS |
| 50 | Impact: missing variableId → 400 | ✅ PASS |
| 51 | Reorder: non-Editor → 403 | ✅ PASS |
| 52 | Reorder: missing dashboardId → 400 | ✅ PASS |
| 53 | Reorder: malformed JSON → 400 | ✅ PASS |
| 54 | Apply (view-mode): no role → 403 | ✅ PASS |
| 55 | Apply: missing variableId → 400 | ✅ PASS |
| 56 | Apply: malformed JSON → 400 | ✅ PASS |
| 57 | Resolve: no role → 403 | ✅ PASS |
| 58 | Resolve: missing variableId → 400 | ✅ PASS |
| 59 | Resolve: bad `from` param → 400 | ✅ PASS |
| 60 | Resolve: bad `to` param → 400 | ✅ PASS |

---

## Sheet B — Live integration tests (server + Lake + Mongo)

| # | Scenario | Verified | Result |
|---|----------|----------|--------|
| B1 | Create query variable | `201`, persisted, `order=0`, `include=true` | ✅ PASS |
| B1b | Embedded read | Variable returned in `GET /dashboards/{id}` | ✅ PASS |
| B2 | Duplicate name (`SELECT_HOST` vs `select_host`) | `409` case-insensitive conflict | ✅ PASS |
| B3 | Resolve query (ignoreTimePicker) | `200`, ≤10 values from Lake | ✅ PASS |
| B4 | Resolve with explicit `?from&to` | `200`, ran against given window | ✅ PASS |
| B5 | Resolve invalid SQL | `400` `invalid SQL syntax … near 'not'` | ✅ PASS |
| B6 | List & Text Field resolution | list → `[ALLOW,BLOCK,COUNT]`; textField → `[]` | ✅ PASS |
| B7 | Rename → panel cascade | `renamedPanelsUpdated=1`; panel SQL now `{{select_hostname}}` | ✅ PASS |
| B8 | Delete-impact + delete | impact listed panel; delete `200`; panel left intact (fallback) | ✅ PASS |
| B9 | Reorder persists | reversed order saved and read back | ✅ PASS |
| B10 | Apply as Viewer (view-mode) | `200` (not 403); `selectedValue=[BLOCK], include=false`; other variable untouched (positional update) | ✅ PASS |
| B11 | Preset dashboard mutation | `403` read-only | ✅ PASS |

---

## Files under test

**Implementation**
- `internal/models/dashboards.go`
- `internal/repositories/dashboards.go`
- `internal/services/dashboards.go`, `internal/services/services.go`
- `internal/api/handlers/dashboards.go`, `internal/api/router.go`
- `internal/utils/variableplaceholder.go`
- `cmd/seeker/main.go`

**Tests**
- `internal/services/dashboards_variables_test.go`
- `internal/utils/variableplaceholder_test.go`
- `internal/api/handlers/dashboards_variables_test.go`
