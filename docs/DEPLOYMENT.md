# Deployment on a Linux VPS

## Prepare the host

Install Docker Engine with the Compose plugin. Use the local setup in the README to create a deployment-specific `.env`, then set `APP_ENV=production`, `APP_DEBUG=false`, `DEMO_MODE=false` and `FRONTEND_URL=https://monitor.example.com`. Keep the application bound to loopback, for example `APP_BIND_ADDRESS=127.0.0.1`, `APP_PORT=8080`.

Terminate TLS on the host proxy. For example, this Caddyfile forwards the HTTPS origin to the Compose gateway.

```caddyfile
monitor.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

With a host proxy, the Compose gateway sees the proxy as the source of API traffic unless Nginx is configured to trust that proxy and its verified forwarding header. Set `set_real_ip_from` to the specific trusted proxy address reachable from the container and set `real_ip_header X-Forwarded-For`. Keep the loopback binding and make the host proxy overwrite any untrusted client-supplied forwarding headers.

## Restrict probe egress

Compose keeps data on an internal network and assigns the worker's public bridge the Linux interface `br-pulse-check`. Apply the supplied [nftables rules](worker-egress.nft) before exposing the application and persist them using your distribution's nftables configuration. These rules apply to Linux hosts with a single PulseMonitor stack. Review the blocked subnets and add any public address ranges that route to infrastructure on your network.

```sh
sudo nft -c -f docs/worker-egress.nft
sudo nft -f docs/worker-egress.nft
docker compose up --build -d --wait
```

The data bridge is used for worker access to PostgreSQL and Redis. Database and Redis ports are private to Compose. Keep only the host TLS proxy publicly reachable. For cloud deployments, also use the provider's network policy to block access from the worker to metadata and private destinations.

## Operational checks

```sh
docker compose ps -a
docker compose exec -T backend alembic current
curl --fail https://monitor.example.com/api/v1/ready
```

The one-off migration service should exit with code 0. Check worker status with `docker compose logs --tail=60 celery-worker celery-beat`. Keep one Beat instance per stack. Configure Telegram using the README.

## Backups and updates

Schedule encrypted PostgreSQL backups and test restoring them to a separate database. Export with `docker compose exec -T postgres pg_dump -U pulse_user -d pulse_monitor -Fc > pulse-monitor.dump`, substituting the configured user and database. Preserve deployment secrets separately from backups. Apply updates using `docker compose up --build -d --wait` after reviewing migrations and taking a backup.
