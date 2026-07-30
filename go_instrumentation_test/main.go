package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"log/slog"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	loadOtelEnv()

	ctx := context.Background()
	serviceName := envOr("OTEL_SERVICE_NAME", "go_instrumentation_test")

	var shutdownTracer func(context.Context) error
	if tracesEnabled() {
		var err error
		shutdownTracer, err = initTracer(ctx)
		if err != nil {
			log.Fatalf("failed to initialize tracer: %v", err)
		}
		defer func() {
			if err := shutdownTracer(context.Background()); err != nil {
				log.Printf("error shutting down tracer: %v", err)
			}
		}()
	}

	lp, err := initLoggerProvider(ctx)
	if err != nil {
		log.Fatalf("failed to initialize logger provider: %v", err)
	}
	defer func() {
		if err := lp.Shutdown(context.Background()); err != nil {
			log.Printf("error shutting down logger provider: %v", err)
		}
	}()

	logger := otelslog.NewLogger(serviceName)

	var tracer trace.Tracer
	if tracesEnabled() {
		tracer = otel.Tracer(serviceName)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", healthHandler(logger))
	mux.HandleFunc("GET /roll", rollHandler(logger, tracer))
	mux.HandleFunc("GET /work", workHandler(logger, tracer))

	port := envOr("PORT", "8080")
	addr := ":" + port

	var handler http.Handler = mux
	if tracesEnabled() {
		handler = otelhttp.NewHandler(mux, "server")
	}

	server := &http.Server{
		Addr:    addr,
		Handler: handler,
	}

	go func() {
		log.Printf("go_instrumentation_test listening on http://localhost%s", addr)
		log.Println("  GET /health  — liveness")
		log.Println("  GET /roll    — random 1-6")
		log.Println("  GET /work    — simulated latency")
		log.Printf("  OTEL_SERVICE_NAME=%s", serviceName)
		log.Printf("  OTEL_LOGS_EXPORTER=%s", os.Getenv("OTEL_LOGS_EXPORTER"))
		log.Printf("  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=%s", os.Getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"))
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = server.Shutdown(shutdownCtx)
}

func tracesEnabled() bool {
	exporter := os.Getenv("OTEL_TRACES_EXPORTER")
	return exporter == "" || exporter == "otlp"
}

func healthHandler(logger *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger.InfoContext(r.Context(), "health check")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	}
}

func rollHandler(logger *slog.Logger, tracer trace.Tracer) http.HandlerFunc {
	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		if tracer != nil {
			var span trace.Span
			ctx, span = tracer.Start(ctx, "dice.roll")
			defer span.End()
		}

		value := rng.Intn(6) + 1
		if span := trace.SpanFromContext(ctx); span.IsRecording() {
			span.SetAttributes(attribute.Int("dice.value", value))
		}

		logger.InfoContext(ctx, "dice.roll", "dice.value", value)
		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprint(w, value)
	}
}

func workHandler(logger *slog.Logger, tracer trace.Tracer) http.HandlerFunc {
	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		if tracer != nil {
			var span trace.Span
			ctx, span = tracer.Start(ctx, "work.request")
			defer span.End()
		}

		logger.InfoContext(ctx, "work.request started")
		simulateStep(ctx, logger, tracer, rng, "work.validate", 20, 80)
		simulateStep(ctx, logger, tracer, rng, "work.process", 50, 200)
		simulateStep(ctx, logger, tracer, rng, "work.persist", 30, 120)
		logger.InfoContext(ctx, "work.request done", "work.status", "done")

		if span := trace.SpanFromContext(ctx); span.IsRecording() {
			span.SetAttributes(attribute.String("work.status", "done"))
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "done"})
	}
}

func simulateStep(ctx context.Context, logger *slog.Logger, tracer trace.Tracer, rng *rand.Rand, name string, minMs, maxMs int) {
	stepCtx := ctx
	if tracer != nil {
		var span trace.Span
		stepCtx, span = tracer.Start(ctx, name)
		defer span.End()
		ctx = stepCtx
	}

	delay := minMs
	if maxMs > minMs {
		delay += rng.Intn(maxMs - minMs + 1)
	}
	if span := trace.SpanFromContext(stepCtx); span.IsRecording() {
		span.SetAttributes(attribute.Int("simulated.delay_ms", delay))
	}

	logger.InfoContext(stepCtx, name, "simulated.delay_ms", delay)
	time.Sleep(time.Duration(delay) * time.Millisecond)
}
