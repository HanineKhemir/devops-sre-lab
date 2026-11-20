// k6 load test for catalog-api: ramp-up, stress and spike scenarios.
//
//   SCENARIO=ramp|stress|spike|all  (default: all, run one after another)
//   BASE_URL                        (default: http://sre-lab-control-plane:30080)
//
// Thresholds mirror the SLOs, so a run "fails" exactly when the SLO is broken.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://sre-lab-control-plane:30080';
const SCENARIO = (__ENV.SCENARIO || 'all').toLowerCase();

const serverErrors = new Counter('server_errors_5xx');

const ALL = {
  // 1. Ramp-up: 0 -> 100 VU, hold, ramp down.
  ramp: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 100 },
      { duration: '3m', target: 100 },
      { duration: '30s', target: 0 },
    ],
    gracefulRampDown: '10s',
    tags: { scenario: 'ramp' },
  },
  // 2. Stress: long plateau at 500 VU.
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '2m', target: 500 },
      { duration: '10m', target: 500 },
      { duration: '1m', target: 0 },
    ],
    gracefulRampDown: '10s',
    tags: { scenario: 'stress' },
  },
  // 3. Spike: sudden jump to 1500 VU for 30 s.
  spike: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '5s', target: 1500 },
      { duration: '30s', target: 1500 },
      { duration: '5s', target: 0 },
    ],
    gracefulRampDown: '5s',
    tags: { scenario: 'spike' },
  },
};

function selectScenarios() {
  if (SCENARIO !== 'all') {
    if (!ALL[SCENARIO]) throw new Error(`unknown SCENARIO ${SCENARIO}`);
    return { [SCENARIO]: ALL[SCENARIO] };
  }
  // Chain them with a 1-minute cool-down in between.
  return {
    ramp: { ...ALL.ramp, startTime: '0s' },
    stress: { ...ALL.stress, startTime: '6m30s' },
    spike: { ...ALL.spike, startTime: '20m30s' },
  };
}

export const options = {
  scenarios: selectScenarios(),
  thresholds: {
    // Availability SLO: 99.5 % of requests are not 5xx (checks fail only on 5xx / no response).
    checks: ['rate>=0.995'],
    // Latency SLO: p95 <= 200 ms.
    http_req_duration: ['p(95)<=200'],
    'http_req_duration{scenario:ramp}': ['p(95)<=200'],
    'http_req_duration{scenario:stress}': ['p(95)<=200'],
    'http_req_duration{scenario:spike}': ['p(95)<=200'],
  },
  summaryTrendStats: ['avg', 'p(50)', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// 404/409/422 are legitimate business answers, not failures.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 499 }));

const PRODUCT_IDS = [1, 2, 3, 4];

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function record(res, name) {
  if (res.status >= 500 || res.status === 0) serverErrors.add(1, { endpoint: name });
  check(res, { [`${name}: no 5xx`]: (r) => r.status > 0 && r.status < 500 });
}

// Traffic mix: 55 % browse, 25 % product detail, 12 % checkout, 8 % flaky.
export default function () {
  const r = Math.random();
  let res;
  if (r < 0.55) {
    res = http.get(`${BASE_URL}/products?limit=20`, { tags: { name: 'GET /products' } });
    record(res, 'list');
  } else if (r < 0.8) {
    res = http.get(`${BASE_URL}/products/${pick(PRODUCT_IDS)}`, {
      tags: { name: 'GET /products/{id}' },
    });
    record(res, 'detail');
  } else if (r < 0.92) {
    const body = JSON.stringify({
      items: [{ product_id: pick(PRODUCT_IDS), quantity: 1 + Math.floor(Math.random() * 3) }],
    });
    res = http.post(`${BASE_URL}/checkout`, body, {
      headers: { 'Content-Type': 'application/json' },
      tags: { name: 'POST /checkout' },
    });
    record(res, 'checkout');
  } else {
    res = http.get(`${BASE_URL}/flaky`, { tags: { name: 'GET /flaky' } });
    record(res, 'flaky');
  }
  sleep(0.5 + Math.random() * 0.5);
}

export function handleSummary(data) {
  const name = SCENARIO === 'all' ? 'all' : SCENARIO;
  return {
    [`/results/summary-${name}.json`]: JSON.stringify(data, null, 2),
    stdout: textSummary(data),
  };
}

function textSummary(data) {
  const m = data.metrics;
  const d = m.http_req_duration.values;
  const fmt = (v) => (v === undefined ? 'n/a' : `${v.toFixed(1)} ms`);
  const reqs = m.http_reqs.values;
  const errs = m.server_errors_5xx ? m.server_errors_5xx.values.count : 0;
  const lines = [
    `scenario         : ${SCENARIO}`,
    `requests         : ${reqs.count} (${reqs.rate.toFixed(1)} req/s)`,
    `5xx / conn errors: ${errs} (${((errs / reqs.count) * 100).toFixed(3)} %)`,
    `latency p50/p90  : ${fmt(d['p(50)'])} / ${fmt(d['p(90)'])}`,
    `latency p95/p99  : ${fmt(d['p(95)'])} / ${fmt(d['p(99)'])}`,
    `max VUs          : ${m.vus_max.values.max}`,
    'thresholds       :',
  ];
  for (const [metric, v] of Object.entries(data.metrics)) {
    if (!v.thresholds) continue;
    for (const [t, res] of Object.entries(v.thresholds)) {
      lines.push(`  ${res.ok ? 'PASS' : 'FAIL'} ${metric} ${t}`);
    }
  }
  return lines.join('\n') + '\n';
}
