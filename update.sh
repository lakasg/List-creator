#!/usr/bin/env bash
#
# update.sh - pull the latest code from GitHub into the running container.
#
# Run on the Proxmox host shell, as root:
#
#     bash update.sh
#
# It takes a snapshot first, pulls, reinstalls requirements only if they
# changed, restarts, and checks the app still answers and still produces the
# same bay groupings. If any of that fails it tells you how to roll back.

set -euo pipefail

STATE_FILE="/etc/listcreator-deploy.conf"

BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; OFF=$'\e[0m'
step() { echo; echo "${BOLD}==> $*${OFF}"; }
ok()   { echo "    ${GREEN}ok${OFF}  $*"; }
warn() { echo "    ${YELLOW}!${OFF}   $*"; }
die()  { echo; echo "${RED}FAILED:${OFF} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run this as root on the Proxmox host."
command -v pct >/dev/null || die "Run this on the Proxmox host, not inside a container."

# Take the container from the file deploy.sh wrote, or from the command line.
if [[ -n "${1:-}" ]]; then
    CTID="$1"; APP_DIR="/opt/listcreator"
elif [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
else
    die "Don't know which container to update.
       Pass the ID:   bash update.sh 102"
fi

pct status "$CTID" >/dev/null 2>&1 || die "Container $CTID does not exist."
[[ "$(pct status "$CTID")" == "status: running" ]] || die "Container $CTID is not running."

step "Updating container $CTID"

CURRENT=$(pct exec "$CTID" -- git -C "$APP_DIR" rev-parse --short HEAD)
ok "currently on $CURRENT"

step "Snapshot before changing anything"
SNAP="before-update-$(date +%Y%m%d-%H%M)"
if pct snapshot "$CTID" "$SNAP" --description "Automatic, before git pull" >/dev/null 2>&1; then
    ok "snapshot $SNAP"
else
    warn "snapshot failed - continuing, but you have no automatic way back"
fi

step "Pulling"

REQ_BEFORE=$(pct exec "$CTID" -- md5sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)

pct exec "$CTID" -- git -C "$APP_DIR" pull --ff-only \
    || die "The pull failed. Local changes on the server would cause that.
       Look with:  pct exec $CTID -- git -C $APP_DIR status"

NEW=$(pct exec "$CTID" -- git -C "$APP_DIR" rev-parse --short HEAD)
if [[ "$CURRENT" == "$NEW" ]]; then
    ok "already up to date - nothing to do"
    exit 0
fi
ok "now on $NEW"
pct exec "$CTID" -- git -C "$APP_DIR" log --oneline "${CURRENT}..${NEW}" | sed 's/^/    /'

REQ_AFTER=$(pct exec "$CTID" -- md5sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)
if [[ "$REQ_BEFORE" != "$REQ_AFTER" ]]; then
    step "Requirements changed - reinstalling"
    pct exec "$CTID" -- bash -c "cd $APP_DIR && venv/bin/pip install --quiet -r requirements.txt" \
        || die "Installing the new requirements failed. Roll back with:
       pct rollback $CTID $SNAP"
    ok "packages updated"
fi

pct exec "$CTID" -- chown -R listcreator:listcreator "$APP_DIR"

step "Restarting"
pct exec "$CTID" -- systemctl restart listcreator
sleep 3

for _ in $(seq 1 15); do
    pct exec "$CTID" -- curl -sf http://127.0.0.1/healthz >/dev/null 2>&1 && break
    sleep 2
done
pct exec "$CTID" -- curl -sf http://127.0.0.1/healthz >/dev/null || die "The app is not answering after the update.
       See why:     pct exec $CTID -- journalctl -u listcreator -n 40
       Roll back:   pct rollback $CTID $SNAP"
ok "app is answering"

step "Checking the bay groupings still match the original"
pct exec "$CTID" -- bash -c "cd $APP_DIR && venv/bin/python verify_configs.py" \
    | sed 's/^/    /' \
    || die "The bay configurations no longer match the original code.
       If you did not change a vessel on purpose, roll back:
       pct rollback $CTID $SNAP"

echo
echo "${GREEN}${BOLD}Updated.${OFF}  ${CURRENT} -> ${NEW}"
echo
echo "  If something looks wrong:  pct rollback $CTID $SNAP"
echo "  Old snapshots:             pct listsnapshot $CTID"
echo
