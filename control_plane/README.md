# LlamaGrid Control Plane

This directory contains the product control plane for the existing LlamaGrid inference fabric. It is deliberately separated from `tools/qwen_replica_dispatcher.py`: the dispatcher remains the low-latency inference data plane, while this application owns inventory, model catalog, provider credentials, deployments, jobs, chat playground and operational UI.

## Stack

| Layer | Choice | Responsibility |
| --- | --- | --- |
| Web API | FastAPI + Uvicorn | Authenticated REST, SSE chat, health and Prometheus metrics |
| Persistence | PostgreSQL + optional TimescaleDB extension | Durable inventory, deployments, audit records and future time-series metrics |
| Migrations | Alembic | Versioned schema changes |
| Jobs | Celery + Redis | Resumable provisioning/deployment state machines and event updates |
| UI | Next.js App Router + TypeScript | Responsive operations panel and chat playground |
| UI state/data | Zustand + TanStack Query | Local UI state, caching, mutations and invalidation |
| Motion/charts | Framer Motion + Recharts | Progress transitions and future capacity visualizations |
| Secrets | Fernet envelope encryption + hashed API keys | Provider tokens are never sent to the browser or stored in plaintext |
| Runtime | Docker Compose | Reproducible local/staging deployment |

## Run

```bash
cp .env.example .env
# Replace SECRET_KEY and POSTGRES_PASSWORD before starting.
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

On the Model-Hub host, `llamagrid-control-plane.service` loads deployment
configuration from the ignored `.env` file and the existing
`/etc/llamagrid/api.env`. The dispatcher URL, backend inventory, model ID,
context limit, and port are all deployment settings; none is required to be a
particular IP address or model. `LLAMAGRID_API_KEY` is passed only to the
backend container as `DISPATCHER_API_KEY`; it is never put in Git or sent to
the browser.

The first browser visit uses `/api/auth/status`; if no user exists, bootstrap an administrator through the UI/API. The frontend is bound to `127.0.0.1:3000` so the existing host Caddy can proxy `beyra-ai.com` without exposing the container directly.

## Production boundaries

- The existing `api.beyra-ai.com` dispatcher and all private worker ports stay unchanged.
- Provider tokens are accepted only by the backend, encrypted before PostgreSQL persistence, and never logged.
- Model installation and server provisioning are explicit tracked jobs. They use provider adapters and never execute arbitrary browser-supplied shell.
- `deployment.apply` starts with a plan/state machine. A provider-specific executor can be enabled after validation; it does not restart the current 14-replica cluster automatically.
- Add Timescale hypertables for high-volume `metrics` data in a later migration; ordinary relational data remains normal PostgreSQL tables.

## Public reverse proxy

Use `deploy/caddy/beyra-ai.com.Caddyfile` alongside the existing API site. Keep `api.beyra-ai.com` pointed at the dispatcher and `beyra-ai.com` pointed at `127.0.0.1:3000`.
