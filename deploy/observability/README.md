# Albumary log infrastructure

A standalone Debian LXC runs Loki as a native systemd service. Nginx restricts
its LAN-facing port while the service listens only on loopback behind it. The
central homelab Grafana instance queries Loki through that proxy. Alloy on the
application host reads only the two Albumary systemd journals. This setup is
independent of the API and worker and does not change their units.

Runtime IP addresses, credentials, log files, and state are not stored in Git.
The example proxy allowlist must be adapted to the actual LAN and clients,
including the central Grafana host. IP
allowlists are not authentication or encryption: use a trusted LAN, protect
routing, and do not port-forward these services to the internet. Loki has no
login and must remain restricted to trusted clients, including the central
Grafana host.

## Observability host

Create an unprivileged Debian 12 LXC with systemd, nesting, persistent local
storage, LAN IP, boot enabled, and initial resources of 1.5 GiB RAM and 20 GiB
disk. Follow the local Proxmox inventory and IP allocation policies. Run these
commands as root from a checkout, with `OBSERVABILITY_IP`, `ALBUMARY_IP`, and
`DEVELOPMENT_IP` replaced with actual addresses:

```sh
apt-get update && apt-get install -y curl ca-certificates nginx
install -d -m 755 /etc/apt/keyrings
curl -fsSL https://apt.grafana.com/gpg-full.key -o /etc/apt/keyrings/grafana.asc
chmod 644 /etc/apt/keyrings/grafana.asc
echo 'deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main' > /etc/apt/sources.list.d/grafana.list
apt-get update && apt-get install -y loki
# The Loki package may start its default public listener during installation.
# Install on an isolated network or firewall port 3100 before this step.
systemctl stop loki nginx
groupadd -f loki && usermod -g loki loki
install -d -o loki -g loki /var/lib/loki
install -d /etc/loki
install -m 644 deploy/observability/loki.yaml /etc/loki/loki.yaml
install -m 644 deploy/observability/systemd/loki.service /etc/systemd/system/loki.service
install -d /etc/systemd/system/nginx.service.d
install -m 644 deploy/observability/systemd/nginx-restart.conf /etc/systemd/system/nginx.service.d/albumary.conf
# Copy nginx.conf.example to /etc/nginx/sites-available/albumary-observability,
# replace its IP placeholders and LAN CIDR, then enable it:
ln -s /etc/nginx/sites-available/albumary-observability /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
loki -config.file=/etc/loki/loki.yaml -verify-config
systemctl daemon-reload
systemctl enable --now loki nginx
```

The central Grafana datasource uses the nginx Loki endpoint; its configuration
belongs to the homelab monitoring repository, not this application repository.
The 30-day default and 3-day development rule are enforced asynchronously by
Loki's Compactor with 24-hour TSDB index periods. Disk-full protection and
off-host backups are not provided.

## Production collector

Install Alloy from the Grafana APT repository as above (`apt-get install alloy`).
Before enabling it, set the production endpoint in a local systemd drop-in and
install the config (replace the address):

```sh
install -m 644 deploy/observability/alloy-production.alloy /etc/alloy/config.alloy
install -d /etc/systemd/system/alloy.service.d /etc/systemd/journald.conf.d
cat > /etc/systemd/system/alloy.service.d/albumary.conf <<'UNIT'
[Service]
Environment=LOKI_URL=http://OBSERVABILITY_IP:3100/loki/api/v1/push
UNIT
install -m 644 deploy/observability/systemd/journald.conf /etc/systemd/journald.conf.d/albumary-observability.conf
install -d -m 2755 -o root -g systemd-journal /var/log/journal
usermod -aG adm,systemd-journal alloy
alloy validate /etc/alloy/config.alloy
systemctl daemon-reload
systemctl restart systemd-journald
journalctl --flush
systemctl enable --now alloy
```

The package stores Alloy state under `/var/lib/alloy`. The journal limit is
512 MiB with 1 GiB of free-space reservation; tune it for host capacity. The
collector reads at most 72 hours of old journal on startup and delivery after
an outage is best effort, not guaranteed. Protect the collector and Loki from
untrusted clients and don't place secrets in log messages.

## Optional local development

Install a standalone Alloy binary from Grafana's official release page or use
`brew install grafana/grafana/alloy`. The collector is optional and runs only
when explicitly started. Configure the Loki proxy to allow the machine's current
IP; update its allowlist if the address changes.

```sh
export ALBUMARY_LOG_DIR="$HOME/.local/state/albumary-logs"
export LOKI_URL="http://OBSERVABILITY_IP:3100/loki/api/v1/push"
mkdir -p "$ALBUMARY_LOG_DIR" "$HOME/.local/state/albumary-alloy"
touch "$ALBUMARY_LOG_DIR/api.log" "$ALBUMARY_LOG_DIR/worker.log"
alloy run --storage.path="$HOME/.local/state/albumary-alloy" deploy/observability/alloy-development.alloy
```

In another terminal, start `make backend 2>&1 | tee -a "$ALBUMARY_LOG_DIR/api.log"`
or `make track-all 2>&1 | tee -a "$ALBUMARY_LOG_DIR/worker.log"` after exporting
the same `ALBUMARY_LOG_DIR`. Stop Alloy with Ctrl-C. Local log files have no
automatic rotation; delete or rotate them as needed. These files can contain
sensitive application output and should remain outside the repository.

## Grafana dashboard

Grafana provisions the [Albumary Operations dashboard](grafana/dashboards/albumary-operations.json)
with native **Overview**, **User activity**, and **Diagnostics** tabs. The
existing `albumary-operations` UID and URL are unchanged. Environment, time
range, and optional Grafana filters are shared; the activity and diagnostic text
filters are scoped to their respective tabs.

The dashboard uses Grafana's v2 resource format and requires Grafana 13 or newer.
The central homelab Grafana file provider reads it from its dedicated Albumary
dashboard directory, prevents UI saves, and retains the database copy if the
file disappears. Its `albumary-loki` datasource UID is part of the dashboard
contract and must remain unchanged.

Update the file from a checkout with SSH access to the Proxmox host:

```sh
./deploy/observability/update-dashboard.sh PROXMOX_SSH_HOST GRAFANA_CT_ID
```

For this homelab, the arguments are `nuc 108`. The script validates the v2
resource and UID, then replaces the file atomically in CT `108`'s dedicated
Albumary dashboard directory. Grafana polls for updates every 30 seconds. This
requires the central Grafana's `albumary-loki` datasource and Albumary dashboard
provider to be installed first. To roll back, restore an earlier dashboard file
in the checkout and rerun the script.

Select **Environment** and a time range to inspect events. Counts represent
observed log events, not live health, unique incidents, or guaranteed audit
records. Production logs retain 30 days; development logs retain three days and
can contain simulated validation events. Use Explore for full event details.
Standalone maintenance command output is not collected by default.

## Verify and update

- `systemctl is-enabled loki nginx` and `systemctl is-active loki nginx` on the observability host; check `alloy` on the app host.
- `curl http://127.0.0.1:3101/ready` on the observability host; Loki may take a short time to become ready.
- Log into the central Grafana, choose Explore and `Albumary Loki`, and query `{app="albumary",environment="production",service="api"}` or `service="worker"`. Replace the environment with `development` for local output.
- Confirm unauthorized clients receive HTTP 403 from port 3100 and the central Grafana requires login. Check `ss -ltn` to ensure Loki binds only to loopback.
- Restart Alloy and Loki individually, check the app API and timer remain healthy, and verify fresh messages arrive. Reboot the observability guest during an appropriate window to verify autostart and persistence. Journal retention and finite retry buffers limit outage recovery.
- Inspect `journalctl -u alloy`, `journalctl -u loki`, `df -h`, and memory use. Review Loki Compactor logs and metrics; retention deletion is delayed and does not immediately reclaim disk.
- Update packages manually with APT, review release notes and config changes, validate the configs, and restart affected services. Reapply repository-managed config and local allowlist changes when updating. Back up or export Grafana settings separately if they become valuable; log history is not backed up by this setup.
