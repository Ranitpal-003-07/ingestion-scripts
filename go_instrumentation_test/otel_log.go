package main

import (
	"context"
	"fmt"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/log/global"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
)

// initLoggerProvider registers a global LoggerProvider that exports log records
// via OTLP HTTP. Endpoint and auth come from OTEL_EXPORTER_OTLP_* env vars.
func initLoggerProvider(ctx context.Context) (*sdklog.LoggerProvider, error) {
	exporter, err := otlploghttp.New(ctx)
	if err != nil {
		return nil, fmt.Errorf("create log exporter: %w", err)
	}

	res, err := resource.New(ctx,
		resource.WithFromEnv(), // picks up OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES
	)
	if err != nil {
		return nil, fmt.Errorf("create resource: %w", err)
	}

	lp := sdklog.NewLoggerProvider(
		sdklog.WithResource(res),
		sdklog.WithProcessor(sdklog.NewBatchProcessor(exporter)),
	)
	global.SetLoggerProvider(lp)
	return lp, nil
}
