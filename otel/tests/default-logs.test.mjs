import assert from "node:assert/strict"
import { once } from "node:events"
import { createServer } from "node:http"
import { test } from "node:test"
import { register } from "import-in-the-middle/register-hooks.mjs"
import { PrometheusExporter } from "@opentelemetry/exporter-prometheus"
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node"
import { createSdk } from "../dist/index.js"

register()

test("does not export Pino logs by default, even when OTLP logs are enabled in the environment", async () => {
  const requests = []
  const server = createServer((request, response) => {
    requests.push(request.url)
    response.writeHead(200)
    response.end()
  })
  server.listen(0, "127.0.0.1")
  await once(server, "listening")

  const address = server.address()
  assert.ok(address && typeof address !== "string")
  process.env.OTEL_LOGS_EXPORTER = "otlp"
  process.env.OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = `http://127.0.0.1:${address.port}/v1/logs`

  const sdk = createSdk({
    serviceName: "default-logs-test",
    metricReader: new PrometheusExporter({ preventServerStart: true }),
    instrumentations: getNodeAutoInstrumentations(),
  })

  try {
    sdk.start()
    const { default: pino } = await import("pino")
    pino({ level: "info" }, pino.destination("/dev/null")).info("must-stay-on-stdout")
    await sdk.shutdown()
    assert.deepEqual(requests, [])
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    )
  }
})
