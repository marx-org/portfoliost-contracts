import assert from "node:assert/strict"
import { test } from "node:test"
import { trace } from "@opentelemetry/api"
import { PrometheusExporter } from "@opentelemetry/exporter-prometheus"
import { createSdk } from "../dist/index.js"

test("exports spans when a trace exporter is explicitly supplied", async () => {
  let exportedSpans = 0
  const traceExporter = {
    export(spans, resultCallback) {
      exportedSpans += spans.length
      resultCallback({ code: 0 })
    },
    async shutdown() {},
  }
  const sdk = createSdk({
    serviceName: "explicit-tracing-test",
    metricReader: new PrometheusExporter({ preventServerStart: true }),
    traceExporter,
  })

  sdk.start()
  const span = trace.getTracer("explicit-tracing-test").startSpan("must-be-exported")
  span.end()
  await sdk.shutdown()

  assert.equal(exportedSpans, 1)
})
