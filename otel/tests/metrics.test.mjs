import test from 'node:test'
import assert from 'node:assert/strict'
import { metrics } from '@opentelemetry/api'
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus'
import { Hono } from 'hono'
import { createSdk, buildMetricsRoute } from '../dist/index.js'

test('registers the supplied metric reader and serves recorded metrics', async () => {
  const exporter = new PrometheusExporter({ preventServerStart: true })
  const sdk = createSdk({ serviceName: 'reader-regression', metricReader: exporter })
  sdk.start()
  try {
    const meter = metrics.getMeter('reader-regression')
    meter.createCounter('verified_requests').add(2)
    meter.createHistogram('http.client.request.duration').record(0.125)
    const app = new Hono()
    app.get('/metrics', buildMetricsRoute(exporter))
    const res = await app.request('/metrics')
    assert.equal(res.status, 200)
    const text = await res.text()
    assert.match(text, /verified_requests_total(?:\{[^\n]*\})? 2(?:\s|$)/)
    assert.match(text, /http_client_request_duration_seconds/)
  } finally {
    await sdk.shutdown()
    metrics.disable()
  }
})
