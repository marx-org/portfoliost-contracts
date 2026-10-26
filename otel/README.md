# `@marx-org/otel`

Shared OpenTelemetry bootstrap helpers for pfire Hono services.

## Tracing defaults

`createSdk` does **not** export traces unless a service passes `traceExporter`. This keeps a
service from silently sending spans to the OpenTelemetry SDK's default OTLP endpoint
(`http://localhost:4318`) when no collector is configured. Setting OTLP endpoint environment
variables alone does not enable trace export through this helper.

Metrics are independent: continue passing the service's `PrometheusExporter` as `metricReader`
to expose `/metrics` as usual.

## Opt in to OTLP tracing

Install the OTLP trace exporter in the service that owns the collector configuration:

```sh
npm install @opentelemetry/exporter-trace-otlp-proto
```

Then explicitly pass it to `createSdk`. Configure the full traces endpoint for a reachable
collector (the example uses `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`):

```ts
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto"
import { createSdk } from "@marx-org/otel"

const traceEndpoint = process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
if (!traceEndpoint) {
  throw new Error("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT is required when tracing is enabled")
}

const sdk = createSdk({
  serviceName: "my-service",
  metricReader: prometheusExporter,
  traceExporter: new OTLPTraceExporter({ url: traceEndpoint }),
})
sdk.start()
```

Only opt in once the collector endpoint is deployed and reachable. The endpoint environment
variable configures the exporter above; it does not by itself opt the service into trace export.
