# Runbook — catalog-api error budget burn

## CatalogApiAvailabilityBudgetBurnCritical / Warning
1. Grafana › *Catalog API — SRE*: which route drives the 5xx (panel **Errors**)?
2. Loki: `{namespace="catalog", level="error"}`, then open a `trace_id` in Tempo to find the failing span.
3. `kubectl -n catalog get pods`: look for restarts or OOMKilled (`kubectl describe pod`).
4. If a deploy is in progress: `argocd app rollback catalog-api` (or revert the GitOps commit).
5. If the cause is load: scale out with `kubectl -n catalog scale deploy/catalog-api --replicas=6`, then raise `replicaCount` in Git.

## CatalogApiLatencyBudgetBurnCritical / Warning
1. Use the **p95 by route** panel to tell whether `/checkout` alone is slow or every route is.
2. If every route is slow, CPU saturation is likely. Check `container_cpu_cfs_throttled_seconds_total` and scale out.
3. If only `/checkout` is slow, inspect the `payment.authorize` span duration in Tempo.
