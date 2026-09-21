#!/usr/bin/env bash
# Builds a systemd-capable container per supported Ubuntu version, runs
# the real install.sh inside it exactly as a VPS operator would (minus the
# curl-pipe bootstrap, since the repo is already mounted in), and checks
# that every service actually comes up healthy. Prints a compatibility
# table at the end. Meant to be run from the repo root:
#   bash tests/integration/run-matrix.sh [version ...]
set -uo pipefail

# On Windows/git-bash, MSYS silently (and unreliably) rewrites any argument
# that looks like a Unix path -- including container-side paths like
# /sys/fs/cgroup or /repo that must reach `docker` untouched. Disabling
# that conversion and passing host-side paths through `cygpath -w`
# ourselves is the combination that has actually been verified to work
# here; on Linux/macOS both no-ops harmlessly.
export MSYS_NO_PATHCONV=1
_winpath() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        echo "$1"
    fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_ROOT_HOST="$(_winpath "$REPO_ROOT")"
VERSIONS=("$@")
if [[ ${#VERSIONS[@]} -eq 0 ]]; then
    VERSIONS=(18.04 20.04 22.04 24.04 26.04)
fi

RESULTS_FILE="$(mktemp)"

run_one() {
    local version="$1"
    local image="sshws-test:$version"
    local container="sshws-test-$version-$$"
    local notes=""

    echo "=================================================================="
    echo " Testing Ubuntu $version"
    echo "=================================================================="

    if ! docker build -q --build-arg "UBUNTU_VERSION=$version" \
            -t "$image" -f "${REPO_ROOT_HOST}\\tests\\integration\\Dockerfile" "$REPO_ROOT_HOST" \
            >"/tmp/build-$version.log" 2>&1; then
        echo "$version|BUILD_FAILED|no|no|no|no|no|Base image build failed, see /tmp/build-$version.log|" >> "$RESULTS_FILE"
        return
    fi

    docker rm -f "$container" >/dev/null 2>&1 || true
    # Named volume (not bind mount) for pip's cache: shared across every
    # version's container run, so re-running the matrix (or re-running
    # after a fix) doesn't re-download the same wheels from PyPI each time.
    if ! docker run -d --name "$container" --privileged --cgroupns=host \
            -v "/sys/fs/cgroup:/sys/fs/cgroup:rw" \
            -v "${REPO_ROOT_HOST}:/repo:ro" \
            -v "sshws-pip-cache:/root/.cache/pip" \
            "$image" >/dev/null; then
        echo "$version|CONTAINER_START_FAILED|no|no|no|no|no|Could not start systemd container|" >> "$RESULTS_FILE"
        return
    fi

    sleep 5
    docker exec "$container" bash -c 'until systemctl is-system-running 2>/dev/null | grep -qE "running|degraded"; do sleep 1; done' \
        || notes="systemd did not reach a ready state within timeout; "

    docker exec "$container" bash -c 'cp -a /repo /opt/ssh-websocket-server-src && cd /opt/ssh-websocket-server-src && SSHWS_ASSUME_YES=1 bash install.sh --yes --skip-ssl --admin-username=admin --admin-password=IntegrationTest12345' \
        > "/tmp/install-$version.log" 2>&1
    local install_rc=$?

    local installer_ok="no" sshd_ok="no" nginx_ok="no" ws_ok="no" manager_ok="no"
    if [[ $install_rc -eq 0 ]]; then
        installer_ok="yes"
    fi

    # gunicorn can take a couple of seconds to bind after `systemctl enable
    # --now`; poll briefly rather than judging on a single snapshot.
    for _ in 1 2 3 4 5 6; do
        docker exec "$container" systemctl is-active sshws-manager >/dev/null 2>&1 && { manager_ok="yes"; break; }
        sleep 2
    done
    docker exec "$container" systemctl is-active ssh >/dev/null 2>&1 && sshd_ok="yes"
    docker exec "$container" systemctl is-active nginx >/dev/null 2>&1 && nginx_ok="yes"
    docker exec "$container" nginx -t >/dev/null 2>&1 && \
        docker exec "$container" bash -c 'curl -s -o /dev/null -w "%{http_code}" -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" http://127.0.0.1:80/ssh' 2>/dev/null | grep -q 101 && ws_ok="yes"

    # UFW's `enable` step reliably fails inside this Docker sandbox
    # specifically (verified root cause: ip6tables can't initialize --
    # "Table does not exist (do you need to insmod?)" -- a missing kernel
    # module in the container runtime, not something install.sh can fix
    # or should work around by weakening IPv6 filtering). `ufw allow`
    # (rule syncing) *does* work in this sandbox and is exercised by every
    # run. Real firewall-enable behavior needs a real VPS kernel; see
    # docs/COMPATIBILITY.md.
    local firewall_ok="no"
    docker exec "$container" bash -c "ufw status 2>/dev/null | grep -q 'Status: active'" && firewall_ok="yes"
    if [[ "$firewall_ok" == "no" ]]; then
        notes="${notes}firewall enable not verifiable in this Docker sandbox (ip6tables kernel module unavailable) -- needs real-VPS verification; "
    fi

    echo "$version|$installer_ok|$sshd_ok|$nginx_ok|$ws_ok|$manager_ok|$firewall_ok|see /tmp/install-$version.log|$notes" >> "$RESULTS_FILE"

    docker logs "$container" > "/tmp/container-$version.log" 2>&1 || true
    docker rm -f "$container" >/dev/null 2>&1 || true
}

for v in "${VERSIONS[@]}"; do
    run_one "$v"
done

echo
echo "| OS | Installer | sshd | nginx | ws endpoint | manager | firewall enable* | Notes |"
echo "|----|-----------|------|-------|-------------|---------|-------------------|-------|"
while IFS='|' read -r version installer sshd nginx ws manager firewall logref notes; do
    echo "| Ubuntu $version | $installer | $sshd | $nginx | $ws | $manager | $firewall | ${notes:-$logref} |"
done < "$RESULTS_FILE"
echo
echo "* firewall enable: see docs/COMPATIBILITY.md -- a Docker-sandbox-only"
echo "  ip6tables limitation, not a code defect; needs real-VPS verification."

rm -f "$RESULTS_FILE"
