#!/usr/bin/env bash
# Apply CtrlB OTEL ConfigMap/Secret + Flask Deployment (local kind/minikube/docker-desktop).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${INGESTION_HOST:?set INGESTION_HOST in .env}"
: "${STREAM_NAME:?set STREAM_NAME in .env}"
: "${API_TOKEN:?set API_TOKEN in .env}"

IMAGE="${IMAGE:-flask-otel-test:latest}"
NS="${NAMESPACE:-default}"

echo "Building image ${IMAGE}..."
docker build -t "${IMAGE}" .

# Load into local cluster if kind/minikube
if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -q .; then
  echo "Loading image into kind..."
  kind load docker-image "${IMAGE}" || true
elif command -v minikube >/dev/null 2>&1 && minikube status >/dev/null 2>&1; then
  echo "Loading image into minikube..."
  minikube image load "${IMAGE}" || true
fi

echo "Applying ConfigMap / Secret / Deployment..."
kubectl -n "${NS}" apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-config
data:
  OTEL_EXPORTER: "otlp"
  OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
  OTEL_SERVICE_NAME: "${STREAM_NAME}"
  OTEL_EXPORTER_OTLP_ENDPOINT: "https://${INGESTION_HOST}/api/default"
  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: "https://${INGESTION_HOST}/api/default/${STREAM_NAME}/_otel/v1/logs"
  PORT: "8080"
EOF

kubectl -n "${NS}" create secret generic otel-secret \
  --from-literal=OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}" \
  --dry-run=client -o yaml | kubectl -n "${NS}" apply -f -

kubectl -n "${NS}" apply -f k8s/deployment.yaml

kubectl -n "${NS}" rollout status deployment/flask-instrumentation-test --timeout=120s

echo
echo "Ready. Port-forward and hit traffic:"
echo "  kubectl -n ${NS} port-forward svc/flask-instrumentation-test 8080:8080"
echo "  ./hit-endpoints.sh"
echo "CtrlB service/stream: ${STREAM_NAME}"
