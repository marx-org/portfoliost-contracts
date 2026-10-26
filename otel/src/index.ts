// @marx-org/otel — shared OpenTelemetry bootstrap helpers for pfire Hono services (D56)
import type { Resource } from "@opentelemetry/resources"
import { resourceFromAttributes, defaultResource } from "@opentelemetry/resources"
import { NodeSDK } from "@opentelemetry/sdk-node"
import type { SpanExporter } from "@opentelemetry/sdk-trace-base"
import type { MetricReader, ViewOptions } from "@opentelemetry/sdk-metrics"
import type { Instrumentation } from "@opentelemetry/instrumentation"
import type { PrometheusExporter } from "@opentelemetry/exporter-prometheus"
import type { Context } from "hono"

/**
 * Views that rename the OTel http duration histograms so the JS Prometheus exporter
 * produces `http_*_request_duration_seconds_*` — matching the Python exporter's convention.
 *
 * The JS exporter (≥0.200) emits the bare sanitised name without appending the unit
 * (it uses a `# UNIT` metadata line instead).  Renaming the instrument to include
 * `.seconds` makes the sanitised Prometheus name consistent with Python's output.
 */
const HTTP_DURATION_VIEWS: ViewOptions[] = [
  {
    name: "http.server.request.duration.seconds",
    instrumentName: "http.server.request.duration",
  },
  {
    name: "http.client.request.duration.seconds",
    instrumentName: "http.client.request.duration",
  },
]

const NOOP_SPAN_EXPORTER: SpanExporter = {
  export(_spans, resultCallback) {
    resultCallback({ code: 0 })
  },
  shutdown: async () => {},
}

/**
 * Build an OTel Resource with standard pfire service attributes.
 */
export function createResource(serviceName: string): Resource {
  return defaultResource().merge(
    resourceFromAttributes({
      "service.name": serviceName,
      "service.version": process.env.APP_VERSION ?? "0.0.0-dev",
      "deployment.environment": process.env.NODE_ENV ?? "production",
    }),
  )
}

export interface CreateSdkOpts {
  serviceName: string
  metricReader: MetricReader
  instrumentations?: Instrumentation[]
  /** Pass an exporter to opt in to trace export. Tracing is disabled when omitted. */
  traceExporter?: SpanExporter
}

/**
 * Create and return a configured NodeSDK instance.
 * Call `sdk.start()` after receiving this.
 *
 * Trace exporting is disabled by default. Pass a trace exporter to opt in — wire Tempo exporter
 * in D57.
 */
export function createSdk(opts: CreateSdkOpts): NodeSDK {
  const sdkOpts: ConstructorParameters<typeof NodeSDK>[0] = {
    resource: createResource(opts.serviceName),
    metricReader: opts.metricReader,
    instrumentations: opts.instrumentations ?? [],
    views: HTTP_DURATION_VIEWS,
  }
  if (opts.traceExporter) {
    sdkOpts.traceExporter = opts.traceExporter
  } else {
    // Older NodeSDK versions only support traceExporter; newer versions support spanProcessors.
    // Supply a no-op exporter for the former and an empty processor list for the latter, so neither
    // path falls back to the environment-driven OTLP exporter (localhost:4318 by default).
    sdkOpts.traceExporter = NOOP_SPAN_EXPORTER
    sdkOpts.spanProcessors = []
  }
  return new NodeSDK(sdkOpts)
}

/**
 * Returns a Hono-compatible route handler that serves Prometheus text format.
 * Uses PrometheusExporter.getMetricsRequestHandler() — the public API.
 * Mount as `app.get('/metrics', metricsRouteHandler)`.
 */
export function buildMetricsRoute(exporter: PrometheusExporter) {
  const handler = exporter.getMetricsRequestHandler.bind(exporter)
  return (c: Context) =>
    new Promise<Response>((resolve, reject) => {
      const mockReq = { method: "GET", url: "/metrics", headers: {} } as any
      const mockRes = {
        statusCode: 200,
        setHeader(_k: string, _v: string) {},
        end(body: string | Buffer) {
          const text = Buffer.isBuffer(body) ? body.toString() : (body ?? "")
          resolve(
            c.body(text, 200, {
              "Content-Type": "text/plain; version=0.0.4; charset=utf-8",
            }),
          )
        },
      }
      try {
        handler(mockReq, mockRes as any)
      } catch (err) {
        reject(err)
      }
    })
}
