# What to set in OpenObserve so span → logs/metrics correlation works
#
# Root cause of traces → logs/metrics failing while logs → traces/metrics works:
# OTLP span attributes flatten to `attributes_<key>` (e.g. `attributes_namespace`).
# Logs keep bare names (`namespace`). Without peeling / aliasing those names,
# `_correlate` from a span only sees `service` (+ maybe `environment`) and cannot
# pick the K8s vs AWS identity set → API returns null.
#
# Also avoid a weak Discovered Services row:
#   Workload: common
#   Identity: environment=prod, service=checkout
# That skips cluster/namespace, so AWS vs K8s checkout collide.

## 1. Field aliases
Import: field-aliases.correlation.json
(includes bare names AND `attributes_*` / `service_*` spellings for traces)

## 2. Service identity (Settings → Correlation → Service discovery)

sets:
  - id: k8s
    label: Kubernetes
    distinguish_by: [k8s-cluster, k8s-namespace]
  - id: aws
    label: AWS
    distinguish_by: [aws-account, aws-region]
tracked_alias_ids: [environment]
service_optional: false

After save → Reset discovered services.

## 3. UI fix (openobserve web)
TraceDetailsSidebar peels `attributes_*` via `unwrapTraceAttributeFields` before
calling `_correlate`. Rebuild / refresh the UI after pulling that change.

## 4. Restart ingest
./run.sh

## 5. Verify Discovered Services
Expect for checkout (K8s):
  Workload: k8s (not "common")
  Identity: k8s-cluster=prod-us-east, k8s-namespace=payments, (+ service, environment)
  Coverage: Logs + Traces + Metrics
Do NOT expect a service named o2-correlation-metrics.

## 6. From a specific span
Traces → open a checkout span → Logs / Metrics correlation tabs.
Time range uses ~±5 minutes around the span.
Metrics live in streams: container_cpu, http_requests_total (not "default").

If Logs tab still says no data: open the browser network tab and check
POST .../service_streams/_correlate — `available_dimensions` must include
`service`, `k8s-namespace`, and `k8s-cluster` (not only `service`).
