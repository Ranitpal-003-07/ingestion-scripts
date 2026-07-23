package dev.ctrlb.instrumentation;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.concurrent.Executors;
import java.util.logging.Logger;

/**
 * Demo HTTP app — no OpenTelemetry imports.
 *
 * Zero-code (CtrlB / OTEL Java agent):
 *
 *   java -javaagent:opentelemetry-javaagent.jar -jar target/java-instrumentation-test.jar
 *
 * The agent auto-instruments:
 *   - Traces:  com.sun.net.httpserver (javahttpserver)
 *   - Metrics: JVM runtime + HTTP server metrics from instrumented servers
 *   - Logs:    java.util.logging → OTLP (enable JUL instrumentation)
 */
public final class App {
    private static final Logger LOG = Logger.getLogger("java_instrumentation_test");
    private static final Random RANDOM = new Random();

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/health", App::health);
        server.createContext("/roll", App::roll);
        server.createContext("/work", App::work);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();

        System.out.printf("java_instrumentation_test listening on http://localhost:%d%n", port);
        System.out.println("  GET /health  — liveness");
        System.out.println("  GET /roll    — random 1-6");
        System.out.println("  GET /work    — simulated latency");
        System.out.println("  zero-code: -javaagent:opentelemetry-javaagent.jar");
        System.out.printf("  OTEL_SERVICE_NAME=%s%n",
                System.getenv().getOrDefault("OTEL_SERVICE_NAME", "(unset)"));
    }

    private static void health(HttpExchange ex) throws IOException {
        LOG.info("health check");
        write(ex, 200, "ok\n");
    }

    private static void roll(HttpExchange ex) throws IOException {
        if (!"GET".equalsIgnoreCase(ex.getRequestMethod())) {
            write(ex, 405, "method not allowed\n");
            return;
        }
        int value = RANDOM.nextInt(6) + 1;
        LOG.info("dice.roll value=" + value);
        write(ex, 200, Integer.toString(value));
    }

    private static void work(HttpExchange ex) throws IOException {
        if (!"GET".equalsIgnoreCase(ex.getRequestMethod())) {
            write(ex, 405, "method not allowed\n");
            return;
        }
        LOG.info("work.request started");
        sleep(20, 80);
        sleep(50, 200);
        sleep(30, 120);
        LOG.info("work.request done");
        write(ex, 200, "{\"status\":\"done\"}\n");
    }

    private static void sleep(int minMs, int maxMs) {
        try {
            Thread.sleep(minMs + RANDOM.nextInt(Math.max(1, maxMs - minMs + 1)));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void write(HttpExchange ex, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }
}
