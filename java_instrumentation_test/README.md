# java_instrumentation_test

Java HTTP app matching the **CtrlB Java zero-code guide**.

`App.java` has **no** OpenTelemetry imports. The agent does instrumentation:

```bash
java -javaagent:$PWD/opentelemetry-javaagent.jar -jar target/java-instrumentation-test.jar
```

## Requirements

- Java 17+
- Maven 3.8+
- macOS: `brew install openjdk@17 maven`

## Step 1 — Agent JAR

`./run.sh` downloads it if missing, or:

```bash
curl -L -O https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar
```

## Step 2 — Configure `.env`

```bash
cp .env.example .env
```

```bash
INGESTION_HOST=staging.ctrlb.dev/engine
STREAM_NAME=java_instrumentation_test
API_TOKEN=your_token
```

## Step 3 — Run

```bash
./run.sh
```

Same as the guide:

```bash
OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_SERVICE_NAME=java_instrumentation_test \
OTEL_EXPORTER_OTLP_ENDPOINT=https://staging.ctrlb.dev/engine/api/default \
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://staging.ctrlb.dev/engine/api/default/java_instrumentation_test/_otel/v1/logs \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic YOUR_TOKEN,stream-name=java_instrumentation_test" \
java -javaagent:$PWD/opentelemetry-javaagent.jar -jar target/java-instrumentation-test.jar
```

## Step 4 — Generate traffic

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/roll
curl http://127.0.0.1:8080/work
# or: ./hit-endpoints.sh
```

## CtrlB

Stream: **`java_instrumentation_test`** — HTTP spans, JVM/HTTP metrics, JUL logs (agent defaults).
