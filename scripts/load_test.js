/**
 * k6 load test — SANKET API
 *
 * Tests three representative load profiles against the most expensive
 * API paths to validate HPA thresholds and find the DB/PgBouncer ceiling:
 *
 *   1. Sales analytics read  — high-frequency read path (many users polling)
 *   2. Forecast trigger      — CPU/ML-intensive, should be rate-limited early
 *   3. CSV ingest upload     — IO-intensive, exercises PgBouncer under write load
 *
 * Usage
 * -----
 *   # Quick smoke test (10 VUs, 30s)
 *   k6 run scripts/load_test.js --vus 10 --duration 30s
 *
 *   # Full ramp-up (mirrors the HPA ramp profile)
 *   k6 run scripts/load_test.js
 *
 *   # Target a deployed environment
 *   k6 run scripts/load_test.js -e BASE_URL=https://api.your-domain.com
 *
 * Required environment variables (can also be set via -e flag)
 * ---------------------------------------------------------------
 *   BASE_URL   — API base URL (default: http://localhost:8000)
 *   AUTH_TOKEN — Bearer token for an owner/analyst account.
 *                Get one via: curl -X POST http://localhost:8000/api/v1/auth/dev-login \
 *                  -H 'Content-Type: application/json' \
 *                  -d '{"workspace_slug":"sanket-dev","email":"owner@sanket-dev.com","password":"Dev@Sanket2024!"}'
 *                Then copy the access_token from the response.
 *
 * Interpreting results
 * --------------------
 * - p95 < 500ms threshold: main SLA target. Failures indicate the API or DB
 *   is saturated and HPA has not scaled fast enough.
 * - http_req_failed rate: should be < 1% (excludes expected 429s).
 * - rate_limit_429_rate: tracks how many requests hit the new heavy-endpoint
 *   bucket. A high rate here means the 30/min limit is appropriate (or
 *   needs tuning) — not a test failure.
 * - Watch Kubernetes HPA metrics (`kubectl get hpa -w`) concurrently to see
 *   at what VU count CPU crosses 70% and pods are added.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { randomItem } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";
const API = `${BASE_URL}/api/v1`;

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------

const forecastDuration = new Trend("forecast_duration_ms", true);
const analyticsDuration = new Trend("analytics_duration_ms", true);
const uploadDuration = new Trend("upload_duration_ms", true);
const rateLimited429 = new Counter("rate_limit_429_total");
const serverErrors5xx = new Counter("server_errors_5xx_total");

// ---------------------------------------------------------------------------
// Load profile — mirrors a realistic HPA validation ramp
// ---------------------------------------------------------------------------

export const options = {
  stages: [
    { duration: "30s", target: 5 },   // warm-up
    { duration: "1m",  target: 20 },  // ramp to moderate load
    { duration: "2m",  target: 50 },  // sustained — should trigger HPA at ~70% CPU
    { duration: "1m",  target: 80 },  // spike — find the ceiling
    { duration: "30s", target: 0 },   // cool-down
  ],
  thresholds: {
    // Core SLA: 95th-percentile response time under 500ms for analytics
    analytics_duration_ms: ["p(95)<500"],
    // Forecasts are slow by nature; we track them but don't fail on latency
    forecast_duration_ms: ["p(95)<30000"],
    // Overall error rate (excludes 429s which are expected on heavy paths)
    http_req_failed: ["rate<0.01"],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HEADERS = {
  "Content-Type": "application/json",
  ...(AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {}),
};

// Minimal CSV payload for upload tests — realistic enough to exercise parsing
const SAMPLE_CSV = `date,sku,quantity,revenue
2024-01-01,SKU-001,10,500.00
2024-01-01,SKU-002,5,250.00
2024-01-02,SKU-001,12,600.00
2024-01-02,SKU-002,3,150.00
`;

function trackResponse(res, durationMetric) {
  if (res.status === 429) {
    rateLimited429.add(1);
    return; // expected — don't count as failure
  }
  if (res.status >= 500) {
    serverErrors5xx.add(1);
  }
  if (durationMetric && res.timings) {
    durationMetric.add(res.timings.duration);
  }
}

// ---------------------------------------------------------------------------
// Scenario: Sales Analytics read (high frequency)
// ---------------------------------------------------------------------------

function runAnalytics() {
  const res = http.get(`${API}/sales-analytics/summary`, {
    headers: HEADERS,
    tags: { name: "analytics_summary" },
  });

  trackResponse(res, analyticsDuration);

  check(res, {
    "analytics: 2xx or 429": (r) => r.status === 200 || r.status === 429,
    "analytics: not 5xx": (r) => r.status < 500,
  });
}

// ---------------------------------------------------------------------------
// Scenario: Forecast trigger (CPU/ML-intensive, expect heavy rate-limiting)
// ---------------------------------------------------------------------------

function runForecast() {
  const payload = JSON.stringify({
    sku_id: null,  // null = aggregate forecast for the tenant
    horizon_days: 30,
    model: "auto",
  });

  const res = http.post(`${API}/forecasts`, payload, {
    headers: HEADERS,
    tags: { name: "forecast_trigger" },
    timeout: "120s",
  });

  trackResponse(res, forecastDuration);

  check(res, {
    "forecast: 2xx, 429, or 202": (r) =>
      r.status === 200 || r.status === 202 || r.status === 429,
    "forecast: not 5xx": (r) => r.status < 500,
  });
}

// ---------------------------------------------------------------------------
// Scenario: CSV ingest upload (IO-intensive)
// ---------------------------------------------------------------------------

function runUpload() {
  // List integrations to get a valid integration ID
  const listRes = http.get(`${API}/integrations`, {
    headers: HEADERS,
    tags: { name: "integrations_list" },
  });

  if (listRes.status !== 200) {
    trackResponse(listRes, null);
    return;
  }

  let integrations = [];
  try {
    integrations = JSON.parse(listRes.body);
  } catch (_) {
    return;
  }

  if (!Array.isArray(integrations) || integrations.length === 0) {
    return; // no integrations seeded — skip upload scenario
  }

  const integration = randomItem(integrations);
  const integrationId = integration.id || integration.connection_id;
  if (!integrationId) return;

  const formData = {
    file: http.file(SAMPLE_CSV, "sales.csv", "text/csv"),
  };

  const uploadHeaders = {
    ...(AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {}),
    // Do NOT set Content-Type here — k6 sets it to multipart/form-data automatically
  };

  const res = http.post(
    `${API}/integrations/${integrationId}/upload`,
    formData,
    {
      headers: uploadHeaders,
      tags: { name: "integration_upload" },
      timeout: "60s",
    }
  );

  trackResponse(res, uploadDuration);

  check(res, {
    "upload: 2xx, 422, or 429": (r) =>
      r.status === 200 ||
      r.status === 201 ||
      r.status === 202 ||
      r.status === 422 || // validation error is OK — we're not sending valid tenant data
      r.status === 429,
    "upload: not 5xx": (r) => r.status < 500,
  });
}

// ---------------------------------------------------------------------------
// Default function — mixed workload
// ---------------------------------------------------------------------------

export default function () {
  // Workload mix: 70% analytics reads, 20% forecasts, 10% uploads.
  // This reflects typical production traffic patterns.
  const roll = Math.random();

  if (roll < 0.70) {
    runAnalytics();
    sleep(1);
  } else if (roll < 0.90) {
    runForecast();
    sleep(5); // forecast calls are slow; back off more between retries
  } else {
    runUpload();
    sleep(2);
  }
}

// ---------------------------------------------------------------------------
// Summary annotations (printed after the run)
// ---------------------------------------------------------------------------

export function handleSummary(data) {
  const summary = {
    thresholds_passed: Object.entries(data.metrics)
      .filter(([, m]) => m.thresholds)
      .every(([, m]) =>
        Object.values(m.thresholds).every((t) => !t.ok === false)
      ),
    rate_limit_429_total:
      data.metrics["rate_limit_429_total"]?.values?.count ?? 0,
    server_errors_5xx_total:
      data.metrics["server_errors_5xx_total"]?.values?.count ?? 0,
    analytics_p95_ms:
      data.metrics["analytics_duration_ms"]?.values?.["p(95)"] ?? null,
    forecast_p95_ms:
      data.metrics["forecast_duration_ms"]?.values?.["p(95)"] ?? null,
  };

  console.log("\n=== SANKET Load Test Summary ===");
  console.log(JSON.stringify(summary, null, 2));
  console.log(
    "\nTip: Run `kubectl get hpa -w` concurrently to observe HPA scaling events."
  );
  console.log(
    "Tip: rate_limit_429_total > 0 means the heavy-endpoint bucket is working."
  );

  return {
    stdout: JSON.stringify(summary, null, 2),
  };
}
