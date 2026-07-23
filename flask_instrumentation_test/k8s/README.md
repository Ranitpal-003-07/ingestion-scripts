# Kubernetes (CtrlB guide)

Pass OTEL env via ConfigMap + Secret, same values as `./run.sh`.

## Files

| File | Purpose |
|------|---------|
| `otel-configmap.yaml` | Non-secret OTEL + PORT |
| `otel-secret.yaml` | `OTEL_EXPORTER_OTLP_HEADERS` |
| `deployment.yaml` | Flask pod + Service + k8s resource attrs |
| `apply.sh` | Build image, apply from `.env`, wait for rollout |

## Step-by-step (Docker Desktop / kind / minikube)

### 1. Build the image (same Dockerfile as Docker guide)

```bash
cd flask_instrumentation_test
docker build -t flask-otel-test:latest .
```

For **kind**:
```bash
kind load docker-image flask-otel-test:latest
```

For **minikube**:
```bash
minikube image load flask-otel-test:latest
```

### 2. Apply ConfigMap + Secret + Deployment

**Option A — from `.env` (recommended):**
```bash
chmod +x k8s/apply.sh
./k8s/apply.sh
```

**Option B — manual YAML:**
```bash
# edit k8s/otel-configmap.yaml and k8s/otel-secret.yaml with real host/token
kubectl apply -f k8s/otel-configmap.yaml
kubectl apply -f k8s/otel-secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/flask-instrumentation-test
```

### 3. Generate traffic

```bash
kubectl port-forward svc/flask-instrumentation-test 8080:8080
# other terminal:
./hit-endpoints.sh
```

### 4. CtrlB

Service/stream = your `STREAM_NAME` (e.g. `flask_instrumentation_test`).  
Resource attrs include `k8s.namespace.name` and `k8s.pod.name`.

## What the Deployment injects

```yaml
envFrom:
  - configMapRef: { name: otel-config }
  - secretRef:    { name: otel-secret }
env:
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: "k8s.namespace.name=$(NAMESPACE),k8s.pod.name=$(POD_NAME),..."
```

Pod `CMD` (from image): `opentelemetry-instrument python app.py`

## Optional: sidecar Collector

App → `localhost:4318` → Collector sidecar → CtrlB.

1. Set ConfigMap endpoint to `http://127.0.0.1:4318`
2. Add an OTEL Collector container in the same pod that exports to CtrlB with your headers
3. See CtrlB “OpenTelemetry Collector for Traces”

For a first test, **skip the sidecar** — send OTLP straight to CtrlB with the ConfigMap/Secret above.
