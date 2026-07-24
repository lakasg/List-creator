#!/usr/bin/env bash
#
# deploy.sh - build a container on Proxmox and deploy List Creator into it.
#
# Run this ONCE, on the Proxmox host shell, as root:
#
#     bash deploy.sh
#
# It creates the container, installs everything, clones the app from GitHub,
# sets up the service and nginx, checks the app actually answers, and takes a
# snapshot. Nothing is assumed to have worked - every stage is verified.
#
# It will refuse to run rather than touch an existing container.

set -euo pipefail

# ----------------------------------------------------------------- settings

REPO_URL="https://github.com/lakasg/List-creator.git"
# Private repo instead? Add a read-only deploy key to the container and use:
#   REPO_URL="git@github.com:lakasg/List-creator.git"

HOSTNAME="listcreator"
APP_DIR="/opt/listcreator"

CTID=""                 # leave empty to take the next free ID
STORAGE="local-lvm"     # where the container disk lives
TEMPLATE_STORE="local"  # where the Debian template lives
BRIDGE="vmbr0"

CORES=2
DISK_GB=6
MEMORY_MB=1024          # steady state - a ceiling, not a reservation
INSTALL_MEMORY_MB=2048  # temporary, so installing pandas cannot run out
SWAP_MB=512

GUNICORN_WORKERS=2

STATE_FILE="/etc/listcreator-deploy.conf"

# --------------------------------------------------------------- plumbing

BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; OFF=$'\e[0m'

step()  { echo; echo "${BOLD}==> $*${OFF}"; }
ok()    { echo "    ${GREEN}ok${OFF}  $*"; }
warn()  { echo "    ${YELLOW}!${OFF}   $*"; }
die()   { echo; echo "${RED}FAILED:${OFF} $*" >&2; exit 1; }

trap 'echo; echo "${RED}Stopped at line $LINENO.${OFF} Nothing further was changed." >&2' ERR

# --------------------------------------------------------------- pre-flight

step "Checking the host"

[[ $EUID -eq 0 ]] || die "Run this as root on the Proxmox host."
command -v pct >/dev/null || die "pct not found. Run this on the Proxmox host, not inside a container."
ok "running as root on Proxmox"

pvesm status --storage "$STORAGE" >/dev/null 2>&1 \
    || die "Storage '$STORAGE' not found. Check the name in the settings at the top."
ok "storage $STORAGE exists"

TEMPLATE=$(pveam list "$TEMPLATE_STORE" 2>/dev/null \
           | awk '/debian-1[0-9]-standard/ {print $1}' | sort -V | tail -1)
[[ -n "$TEMPLATE" ]] \
    || die "No Debian template found on '$TEMPLATE_STORE'. Download one first:
       Proxmox web interface -> $TEMPLATE_STORE -> CT Templates -> Templates"
ok "template $(basename "$TEMPLATE")"

AVAIL_MB=$(free -m | awk '/^Mem:/ {print $7}')
NEEDED_MB=$((INSTALL_MEMORY_MB + 512))
if (( AVAIL_MB < NEEDED_MB )); then
    die "Only ${AVAIL_MB} MB free on the host; the install needs about ${NEEDED_MB} MB.
       Stop something else first, or lower INSTALL_MEMORY_MB at the top of this script."
fi
ok "${AVAIL_MB} MB free on the host (install needs ~${NEEDED_MB} MB)"

if [[ -z "$CTID" ]]; then
    CTID=$(pvesh get /cluster/nextid 2>/dev/null) || die "Could not work out a free container ID."
fi
if pct status "$CTID" >/dev/null 2>&1; then
    die "Container $CTID already exists. This script will not touch it.
       Set CTID at the top of the script to a free number."
fi
ok "container ID $CTID is free"

ROOT_PASS=$(openssl rand -base64 12)
APP_SECRET=$(openssl rand -hex 32)

# --------------------------------------------------------------- create

step "Creating container $CTID"

pct create "$CTID" "$TEMPLATE" \
    --hostname "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$INSTALL_MEMORY_MB" \
    --swap "$SWAP_MB" \
    --rootfs "${STORAGE}:${DISK_GB}" \
    --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
    --unprivileged 1 \
    --features nesting=1 \
    --onboot 1 \
    --password "$ROOT_PASS" \
    --description "List Creator - deployed from ${REPO_URL}" \
    >/dev/null
ok "created with ${CORES} cores, ${DISK_GB} GB disk"

pct start "$CTID" >/dev/null
ok "started"

step "Waiting for the network"
IP=""
for _ in $(seq 1 60); do
    IP=$(pct exec "$CTID" -- ip -4 -o addr show eth0 2>/dev/null \
         | awk '{print $4}' | cut -d/ -f1 || true)
    [[ -n "$IP" ]] && break
    sleep 2
done
[[ -n "$IP" ]] || die "The container never got an IP address from DHCP.
       Check the bridge name ($BRIDGE) at the top of this script."
ok "address $IP"

for _ in $(seq 1 30); do
    pct exec "$CTID" -- getent hosts github.com >/dev/null 2>&1 && break
    sleep 2
done
pct exec "$CTID" -- getent hosts github.com >/dev/null 2>&1 \
    || die "The container cannot resolve github.com. Check its DNS settings."
ok "can reach github.com"

# --------------------------------------------------------------- install

step "Installing inside the container (this is the slow part)"

INNER=$(mktemp)
cat > "$INNER" <<INNEREOF
#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

APP_DIR="${APP_DIR}"
REPO_URL="${REPO_URL}"
APP_SECRET="${APP_SECRET}"
WORKERS="${GUNICORN_WORKERS}"

echo "--- packages"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-dev git nginx curl ca-certificates

echo "--- clone"
rm -rf "\$APP_DIR"
git clone --depth 1 "\$REPO_URL" "\$APP_DIR"

echo "--- python packages"
cd "\$APP_DIR"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip wheel
if ! venv/bin/pip install --quiet -r requirements.txt; then
    echo "--- prebuilt packages unavailable, installing build tools and retrying"
    apt-get install -y -qq build-essential
    venv/bin/pip install -r requirements.txt
fi

echo "--- service account"
id -u listcreator >/dev/null 2>&1 || adduser --system --group --home "\$APP_DIR" listcreator
chown -R listcreator:listcreator "\$APP_DIR"

echo "--- systemd unit"
cat > /etc/systemd/system/listcreator.service <<UNIT
[Unit]
Description=List Creator
After=network.target

[Service]
User=listcreator
Group=listcreator
WorkingDirectory=\$APP_DIR
Environment="LIST_SECRET=\$APP_SECRET"
ExecStart=\$APP_DIR/venv/bin/gunicorn --workers \$WORKERS --timeout 120 --bind 127.0.0.1:8000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

echo "--- nginx"
cat > /etc/nginx/sites-available/listcreator <<NGINX
server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 32M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \\\$host;
        proxy_set_header X-Forwarded-For \\\$proxy_add_x_forwarded_for;
    }
}
NGINX
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/listcreator /etc/nginx/sites-enabled/listcreator
nginx -t

echo "--- starting"
systemctl daemon-reload
systemctl enable --now listcreator >/dev/null
systemctl reload nginx || systemctl restart nginx
INNEREOF

pct push "$CTID" "$INNER" /root/setup.sh --perms 755 >/dev/null
rm -f "$INNER"

if ! pct exec "$CTID" -- bash /root/setup.sh; then
    die "The install failed inside the container.
       Look around with:   pct enter $CTID
       Start over with:    pct stop $CTID && pct destroy $CTID"
fi
pct exec "$CTID" -- rm -f /root/setup.sh
ok "installed"

# --------------------------------------------------------------- verify

step "Checking it actually works"

for _ in $(seq 1 20); do
    pct exec "$CTID" -- curl -sf http://127.0.0.1/healthz >/dev/null 2>&1 && break
    sleep 2
done
pct exec "$CTID" -- curl -sf http://127.0.0.1/healthz >/dev/null \
    || die "The app is not responding inside the container.
       Look at why with:   pct exec $CTID -- journalctl -u listcreator -n 40"
ok "app answers on port 80"

curl -sf --max-time 10 "http://${IP}/healthz" >/dev/null \
    && ok "reachable from the host at http://${IP}" \
    || warn "not reachable from the host - it works inside the container, so check your network"

pct exec "$CTID" -- bash -c "cd ${APP_DIR} && venv/bin/python verify_configs.py" \
    | sed 's/^/    /' \
    || die "The bay configurations do not match the original code. Do not use this until that is understood."
ok "bay configurations verified against the original"

# --------------------------------------------------------------- settle

step "Setting final resources"

pct set "$CTID" --memory "$MEMORY_MB" >/dev/null
ok "memory reduced from ${INSTALL_MEMORY_MB} MB to ${MEMORY_MB} MB"

USED_MB=$(pct exec "$CTID" -- free -m | awk '/^Mem:/ {print $3}')
ok "currently using about ${USED_MB} MB"

step "Taking a snapshot"
pct snapshot "$CTID" working-install \
    --description "First working install, $(date +%Y-%m-%d)" >/dev/null 2>&1 \
    && ok "snapshot 'working-install' taken" \
    || warn "snapshot failed - not fatal, take one from the web interface"

cat > "$STATE_FILE" <<STATE
# Written by deploy.sh - used by update.sh
CTID=$CTID
APP_DIR=$APP_DIR
IP=$IP
STATE

# --------------------------------------------------------------- done

cat <<SUMMARY

${GREEN}${BOLD}Done.${OFF}

  Open it at        ${BOLD}http://${IP}${OFF}
  Container ID      $CTID
  Root password     $ROOT_PASS
                    ${YELLOW}write this down - it is not stored anywhere${OFF}

  Update later      bash update.sh
  Get a shell       pct enter $CTID
  See the log       pct exec $CTID -- journalctl -u listcreator -f
  Roll back         pct rollback $CTID working-install

  The address comes from DHCP. To pin it so bookmarks keep working, see
  "Giving it a fixed address" in DEPLOY.md.

SUMMARY
