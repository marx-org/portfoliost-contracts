import assert from "node:assert/strict"
import { once } from "node:events"
import { createServer } from "node:http"
import { test } from "node:test"
import { trace } from "@opentelemetry/api"
import { PrometheusExporter } from "@opentelemetry/exporter-prometheus"
import { createSdk } from "../dist/index.js"

test("does not export traces by default, even when OTLP env configuration is present", async () => {
  let requests = 0
  const server = createServer((_request, response) => {
    requests += 1
    response.writeHead(200)
    response.end()
  })
  server.listen(0, "127.0.0.1")
  await once(server, "listening")

  const address = server.address()
  assert.ok(address && typeof address !== "string")
  process.env.OTEL_TRACES_EXPORTER = "otlp"
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT = `http://127.0.0.1:${address.port}`
  process.env.OTEL_BSP_SCHEDULE_DELAY = "10"

  const sdk = createSdk({
    serviceName: "default-tracing-test",
    metricReader: new PrometheusExporter({ preventServerStart: true }),
  })

  try {
    sdk.start()
    const span = trace.getTracer("default-tracing-test").startSpan("must-not-be-exported")
    span.end()
    await sdk.shutdown()
    assert.equal(requests, 0)
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    )
  }
})
