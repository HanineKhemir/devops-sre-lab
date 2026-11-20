# devops-sre-lab — Continuous Delivery, Quality/Security Gates & SRE

Catalog microservice (FastAPI) with a gated CI pipeline, GitOps delivery,
OPA Gatekeeper admission policies, and a full OpenTelemetry observability
stack with SLOs, error budgets and multi-window burn-rate alerts.

| Path | Content |
|---|---|
| `app/`, `tests/` | Microservice (`/products`, `/checkout`, `/flaky`, `/metrics`) + pytest (coverage ≥ 85 %) |
| `Dockerfile` | Non-root, multi-stage image |
| `.github/workflows/ci.yml` | Lint & Test → Sonar Quality Gate → Build → Trivy (CRITICAL = fail) → Push GHCR → GitOps bump |
| `policies/` | Gatekeeper ConstraintTemplates (Rego), constraints, test manifests |
| `deploy/helm/catalog-api/` | Helm chart, PrometheusRule (SLO + burn rate), Grafana dashboard |
| `deploy/argocd/` | ArgoCD Applications |
| `deploy/observability/` | Prometheus/Alertmanager/Grafana, Loki, Tempo, Alloy values |
| `k6/` | Load test: ramp-up 100 VU, stress 500 VU, spike 1500 VU |
| `docs/` | SRE report and runbook |

See [`docs/RAPPORT-SRE.md`](docs/RAPPORT-SRE.md) for setup steps and results.
