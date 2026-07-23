package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

func main() {
	loadOtelEnv()

	ctx := context.Background()
	shutdown, err := initTracer(ctx)
	if err != nil {
		log.Fatalf("failed to initialize tracer: %v", err)
	}
	defer func() {
		shutdownCtx := context.Background()
		if err := shutdown(shutdownCtx); err != nil {
			log.Printf("error shutting down tracer: %v", err)
		}
	}()

	serviceName := envOr("OTEL_SERVICE_NAME", "go_instrumentation_test")
	tracer := otel.Tracer(serviceName)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})
	mux.HandleFunc("GET /roll", rollHandler(tracer))
	mux.HandleFunc("GET /work", workHandler(tracer))

	port := envOr("PORT", "8080")
	addr := ":" + port

	// Guide Step 2B: wrap the mux with otelhttp so HTTP requests create spans
	server := &http.Server{
		Addr:    addr,
		Handler: otelhttp.NewHandler(mux, "server"),
	}

	go func() {
		log.Printf("go_instrumentation_test listening on http://localhost%s", addr)
		log.Println("  GET /health  — liveness")
		log.Println("  GET /roll    — random 1-6 (manual span dice.roll)")
		log.Println("  GET /work    — nested spans + simulated latency")
		log.Printf("  OTEL_SERVICE_NAME=%s", serviceName)
		log.Printf("  OTEL_EXPORTER_OTLP_ENDPOINT=%s", os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))
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

func rollHandler(tracer trace.Tracer) http.HandlerFunc {
	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, span := tracer.Start(r.Context(), "dice.roll")
		defer span.End()

		value := rng.Intn(6) + 1
		span.SetAttributes(attribute.Int("dice.value", value))

		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprint(w, value)
		_ = ctx
	}
}

func workHandler(tracer trace.Tracer) http.HandlerFunc {
	rng := rand.New(rand.NewSource(time.Now().UnixNano()))
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, span := tracer.Start(r.Context(), "work.request")
		defer span.End()

		simulateStep(ctx, tracer, rng, "work.validate", 20, 80)
		simulateStep(ctx, tracer, rng, "work.process", 50, 200)
		simulateStep(ctx, tracer, rng, "work.persist", 30, 120)

		span.SetAttributes(attribute.String("work.status", "done"))
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "done"})
	}
}

func simulateStep(ctx context.Context, tracer trace.Tracer, rng *rand.Rand, name string, minMs, maxMs int) {
	ctx, span := tracer.Start(ctx, name)
	defer span.End()

	delay := minMs
	if maxMs > minMs {
		delay += rng.Intn(maxMs - minMs + 1)
	}
	span.SetAttributes(attribute.Int("simulated.delay_ms", delay))
	time.Sleep(time.Duration(delay) * time.Millisecond)
	_ = ctx
}
