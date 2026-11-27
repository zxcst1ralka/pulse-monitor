# Architecture

PulseMonitor is a modular monolith with separately deployed API, scheduling and execution processes. Nginx forwards `/api/` requests to FastAPI and serves the React SPA through its static frontend service. The browser reaches persistent data through the API.

| Component | Responsibility |
| --- | --- |
| PostgreSQL | Accounts and sessions, monitor configuration, history, incidents, delivery state and public status pages |
| Redis | Celery broker, authorization rate limits, Telegram polling coordination |
| Celery Beat | Regular due-monitor scans, delivery attempts, Telegram polling and retention |
| Celery Worker | Lease ownership, asynchronous HTTP/TLS checks and application of results |
| FastAPI | Ownership checks, validation, aggregation, management APIs and sanitized public projections |

## Check lifecycle

1. Beat queues a scheduler tick. The scheduler selects due records with `FOR UPDATE SKIP LOCKED` and assigns unique, expiring tokens before queuing jobs. An expired lease is recoverable after an interrupted dispatch.
2. A worker acquires the same row briefly, confirms the token and active account, then marks the job started. Overlapping deliveries cannot both execute a lease. Pausing the monitor or editing probe settings invalidates the token.
3. The probe validates the destination, resolves all addresses, connects directly to an approved IP and uses the original hostname in HTTP and TLS. It independently validates every redirect, limits ports, the deadline and the keyword body size, and checks TLS normally.
4. A second transaction writes the check, updates SSL and status, creates or resolves an incident, records relevant notification events, and advances the schedule. A unique check slot and partial unique index for open incidents provide database-level invariants.
5. Delivery claims an outbox row before performing Telegram I/O. The unique event key deduplicates transitions and per-certificate thresholds. If the worker loses the delivery acknowledgement, the row eventually reports failure for review. Unexpected probe exceptions release capacity when the lease expires and leave monitor history untouched.

## Access and data

Access JWTs live in browser memory. Refresh tokens live in Strict, HttpOnly cookies and are stored as hashes in PostgreSQL. Rotation revokes the spent token. Replay revokes its family. Password updates and administrative blocking revoke all sessions for the affected user. Exact Origin checks protect cookie-authenticated endpoints.

API queries scope private resources to the authenticated account. Public status responses project service labels and availability only. Synthetic demo monitoring histories are precomputed and the scheduler skips their monitors.

All timestamps are stored with timezone and generated in UTC. Charts bucket mean latency of successful checks. Degraded checks count as successful for availability. The retention job deletes check history older than the configured number of days. Incident history remains available.
