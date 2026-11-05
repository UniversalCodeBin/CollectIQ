// Read-model benchmark. Env: BASE, WS, EMAIL, PASSWORD. Thresholds are NFR-01: dashboard/queue p95 <= 2 s, filter/sort <= 1 s.
import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE || "http://127.0.0.1:8000";
const P95 = (ms) => [`p(95)<${ms}`];

export const options = {
  scenarios: {
    reads: { executor: "constant-vus", vus: 5, duration: "30s" },
  },
  thresholds: {
    "http_req_duration{name:list}": P95(1000),
    "http_req_duration{name:queue}": P95(2000),
    "http_req_duration{name:dashboard}": P95(2000),
    "http_req_duration{name:detail}": P95(1000),
    http_req_failed: ["rate<0.01"],
  },
};

export function setup() {
  const res = http.post(
    `${BASE}/api/v1/auth/login`,
    JSON.stringify({ email: __ENV.EMAIL, password: __ENV.PASSWORD }),
    { headers: { "Content-Type": "application/json" } },
  );
  if (res.status !== 200) throw new Error(`login failed: ${res.status}`);
  const cookie = Object.entries(res.cookies).map(([k, v]) => `${k}=${v[0].value}`).join("; ");
  const first = http.get(`${BASE}/api/v1/workspaces/${__ENV.WS}/invoices?limit=1`, { headers: { Cookie: cookie } });
  return { cookie, id: first.json("items.0.id") || first.json("data.0.id") };
}

export default function (data) {
  const params = (name) => ({ headers: { Cookie: data.cookie }, tags: { name } });
  const root = `${BASE}/api/v1/workspaces/${__ENV.WS}`;
  const responses = [
    http.get(`${root}/invoices?limit=50&sort=due_date`, params("list")),
    http.get(`${root}/invoices?tile=overdue&limit=50`, params("list")),
    http.get(`${root}/queue?limit=50`, params("queue")),
    http.get(`${root}/dashboard`, params("dashboard")),
    http.get(`${root}/invoices/${data.id}`, params("detail")),
  ];
  for (const r of responses) check(r, { "200": (x) => x.status === 200 });
}
