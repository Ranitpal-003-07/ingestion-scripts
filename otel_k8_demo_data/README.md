# OpenTelemetry Demo → CtrlB

Helm install of the [OpenTelemetry Demo](https://opentelemetry.io/docs/demo/kubernetes-deployment/) with the collector exporting to CtrlB staging.

## What gets sent

| Signal | Source | CtrlB |
|--------|--------|--------|
| Traces | Demo services | stream `otel_demo_traces` |
| Metrics | `hostmetrics`, `kubeletstats`, `k8s_cluster` | per-metric streams (`k8s_daemonset_*`, `system_cpu_*`, …) |
| Logs | filelog `/var/log/pods` | stream `k8s` |
| App logs | OTLP from demo SDKs | stream `otel_demo_logs` |

`k8s` log fields for the Kubernetes / Logs dashboard: `body`, `log_iostream`, `logtag`, `log_file_path`, `k8s_cluster_name`, `resource_k8s_*`.

## Prerequisites

- Kubernetes 1.24+ (~6 GB free RAM)
- Helm 3.14+ (`~/.local/bin/helm` if installed via the get-helm script)

## Install

```bash
export PATH="$HOME/.local/bin:$PATH"
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update

kubectl create namespace otel-demo 2>/dev/null || true
helm install my-otel-demo open-telemetry/opentelemetry-demo \
  --namespace otel-demo \
  --values ./ctrlb-values.yaml
```

The demo chart **does not support upgrade**. To change values:

```bash
helm uninstall my-otel-demo -n otel-demo
helm install my-otel-demo open-telemetry/opentelemetry-demo \
  --namespace otel-demo \
  --values ./ctrlb-values.yaml
```

## Use the UI

```bash
kubectl -n otel-demo port-forward svc/frontend-proxy 8080:8080
```

- Store: http://localhost:8080/
- Loadgen: http://localhost:8080/loadgen/

## Cluster name

Default `k8s.cluster.name` is `minikube` in `ctrlb-values.yaml`. Change that value for other clusters.
