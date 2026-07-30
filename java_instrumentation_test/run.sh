#!/usr/bin/env bash
# CtrlB Java guide — traces only.
#
#   OTEL_EXPORTER=otlp \
#   OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
#   OTEL_SERVICE_NAME=<service_name> \
#   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://<INGESTION_HOST>/api/default/v1/traces \
#   OTEL_METRICS_EXPORTER=none \
#   OTEL_LOGS_EXPORTER=none \
#   OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <API_TOKEN>,stream-name=<STREAM_NAME>" \
#   java -javaagent:$PWD/opentelemetry-javaagent.jar -jar <my-app>.jar
set -euo pipefail
cd "$(dirname "$0")"

AGENT_JAR="${OTEL_JAVAAGENT_JAR:-$PWD/opentelemetry-javaagent.jar}"
AGENT_VERSION="${OTEL_JAVAAGENT_VERSION:-2.14.0}"
APP_JAR="target/java-instrumentation-test.jar"
JAVA_BIN=""

ensure_java() {
  if command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
    JAVA_BIN="$(command -v java)"
    return 0
  fi
  for candidate in \
    /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
    /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home \
    /usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
    /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home; do
    if [[ -x "$candidate/bin/java" ]]; then
      export JAVA_HOME="$candidate"
      export PATH="$JAVA_HOME/bin:$PATH"
      JAVA_BIN="$JAVA_HOME/bin/java"
      return 0
    fi
  done
  echo "Java not found. Install with: brew install openjdk@17 maven" >&2
  exit 1
}

ensure_agent() {
  if [[ -f "$AGENT_JAR" ]]; then
    return 0
  fi
  echo "Downloading OpenTelemetry Java agent v${AGENT_VERSION}..."
  curl -fsSL \
    "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${AGENT_VERSION}/opentelemetry-javaagent.jar" \
    -o "$AGENT_JAR"
}

# Drop stale OTEL_* from other demos
unset DJANGO_SETTINGS_MODULE 2>/dev/null || true
while IFS= read -r var; do
  unset "$var" 2>/dev/null || true
done < <(env | awk -F= '/^OTEL_/ {print $1}')

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${INGESTION_HOST:?set INGESTION_HOST in .env}"
: "${STREAM_NAME:?set STREAM_NAME in .env}"
: "${API_TOKEN:?set API_TOKEN in .env}"

export OTEL_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME="${STREAM_NAME}"
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://${INGESTION_HOST}/api/default/v1/traces"
export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic ${API_TOKEN},stream-name=${STREAM_NAME}"
unset OTEL_EXPORTER_OTLP_ENDPOINT 2>/dev/null || true
unset OTEL_EXPORTER_OTLP_LOGS_ENDPOINT 2>/dev/null || true

ensure_java
ensure_agent
mvn -q package

echo "java_instrumentation_test (CtrlB Java guide — traces only)"
echo "  OTEL_SERVICE_NAME=${OTEL_SERVICE_NAME}"
echo "  OTEL_METRICS_EXPORTER=${OTEL_METRICS_EXPORTER}"
echo "  OTEL_LOGS_EXPORTER=${OTEL_LOGS_EXPORTER}"
echo "  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT}"
echo "  launcher: java -javaagent:\$PWD/opentelemetry-javaagent.jar -jar ${APP_JAR}"
echo

exec "$JAVA_BIN" -javaagent:"$AGENT_JAR" -jar "$APP_JAR"
