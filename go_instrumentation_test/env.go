package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func loadEnvFile(name string) {
	path := name
	if _, err := os.Stat(path); os.IsNotExist(err) {
		path = filepath.Join(filepath.Dir(os.Args[0]), name)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			return
		}
	}

	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		key, val, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key = strings.TrimSpace(key)
		val = strings.TrimSpace(val)
		val = strings.Trim(val, `"'`)
		if val == "" {
			continue
		}
		if os.Getenv(key) == "" {
			_ = os.Setenv(key, val)
		}
	}
}

// loadOtelEnv loads .env and sets CtrlB OTLP vars (guide Step 3).
func loadOtelEnv() {
	loadEnvFile(".env")

	ingestionHost := os.Getenv("INGESTION_HOST")
	streamName := os.Getenv("STREAM_NAME")
	apiToken := os.Getenv("API_TOKEN")
	if ingestionHost == "" || streamName == "" || apiToken == "" {
		return
	}

	setDefaultEnv("OTEL_EXPORTER", "otlp")
	setDefaultEnv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
	setDefaultEnv("OTEL_SERVICE_NAME", streamName)
	setDefaultEnv("OTEL_EXPORTER_OTLP_ENDPOINT", fmt.Sprintf("https://%s/api/default", ingestionHost))
	setDefaultEnv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
		fmt.Sprintf("https://%s/api/default/%s/_otel/v1/logs", ingestionHost, streamName))
	setDefaultEnv("OTEL_EXPORTER_OTLP_HEADERS",
		fmt.Sprintf("Authorization=Basic %s,stream-name=%s", apiToken, streamName))
}

func setDefaultEnv(key, val string) {
	if os.Getenv(key) == "" {
		_ = os.Setenv(key, val)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
