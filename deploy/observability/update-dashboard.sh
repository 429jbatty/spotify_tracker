#!/bin/sh
# Run from a checkout on a machine with SSH access to the Proxmox host as root.
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 PROXMOX_SSH_HOST GRAFANA_CT_ID" >&2
    exit 2
fi
host=$1
grafana_ct_id=$2
case "$host" in ''|-*) echo "Invalid SSH host" >&2; exit 2 ;; esac
case "$grafana_ct_id" in ''|*[!0-9]*) echo "Container ID must be numeric" >&2; exit 2 ;; esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dashboard="$script_dir/grafana/dashboards/albumary-operations.json"
# Grafana v2 dashboards use a resource envelope; metadata.name is the UID.
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("apiVersion") == "dashboard.grafana.app/v2" and d.get("kind") == "Dashboard" and d.get("metadata", {}).get("name") == "albumary-operations", "unexpected dashboard resource"' "$dashboard"

# Write on the same filesystem and rename atomically, so Grafana never reads a
# partially transferred dashboard. This updates only the dashboard, not the app.
remote_command="pct exec $grafana_ct_id -- sh -c 'set -eu; target=/opt/monitoring/grafana/albumary-dashboards; test -d \"\$target\"; tmp=\$(mktemp \"\$target/.albumary-operations.XXXXXX\"); trap '\''rm -f \"\$tmp\"'\'' EXIT HUP INT TERM; cat > \"\$tmp\"; chmod 644 \"\$tmp\"; mv -f \"\$tmp\" \"\$target/albumary-operations.json\"'"
ssh "$host" "$remote_command" < "$dashboard"
echo "Dashboard copied; Grafana checks for updates within 30 seconds."
