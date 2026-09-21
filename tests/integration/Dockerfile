# Minimal systemd-capable Ubuntu image used to exercise install.sh the
# same way it runs on a real VPS (systemd services, apt, ufw, etc).
# Build per-version: docker build --build-arg UBUNTU_VERSION=22.04 ...
ARG UBUNTU_VERSION=22.04
FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq && apt-get install -y -qq systemd systemd-sysv sudo iproute2 dbus \
    && rm -rf /var/lib/apt/lists/*

# Strip units this container doesn't need / that fail under Docker, matching
# the well-established "systemd in Docker" pattern.
RUN find /etc/systemd/system /lib/systemd/system -name '*.wants' -type d \
      | xargs -r -I{} find {} -mindepth 1 -maxdepth 1 -exec rm -f {} \; ; \
    rm -f /lib/systemd/system/multi-user.target.wants/* \
          /etc/systemd/system/*.wants/* \
          /lib/systemd/system/local-fs.target.wants/* \
          /lib/systemd/system/sockets.target.wants/*udev* \
          /lib/systemd/system/sockets.target.wants/*initctl* \
          /lib/systemd/system/basic.target.wants/* \
          /lib/systemd/system/anaconda.target.wants/* 2>/dev/null || true

VOLUME ["/sys/fs/cgroup"]
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
