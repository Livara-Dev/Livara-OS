# syntax=docker/dockerfile:1
ARG UBUNTU_BASE=ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
FROM ${UBUNTU_BASE} AS desktop
ARG LIVARA_APT_REFRESH=manual
ENV DEBIAN_FRONTEND=noninteractive
COPY build/packages.txt /tmp/livara-packages.txt
RUN --mount=type=secret,id=proxy_ca \
    set -eux; \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; \
      printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99livara-build-ca; fi; \
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod +x /usr/sbin/policy-rc.d; \
    printf 'APT refresh: %s\n' "$LIVARA_APT_REFRESH"; \
    apt-get update; apt-get dist-upgrade -y; \
    xargs -r apt-get install -y --no-install-recommends < /tmp/livara-packages.txt; \
    apt-get clean; rm -rf /var/lib/apt/lists/* /tmp/*; \
    rm -f /etc/apt/apt.conf.d/99livara-build-ca /usr/sbin/policy-rc.d

FROM desktop AS rootfs
COPY dist/forks/livara-code-linux-x64.tar.xz dist/forks/livara-browser-linux-x64.tar.xz dist/forks/livara-tor-browser-linux-x64.tar.xz /tmp/livara-forks/
COPY build/install-forks.py /tmp/livara-install-forks.py
RUN python3 /tmp/livara-install-forks.py /tmp/livara-forks \
    && rm -rf /tmp/livara-forks /tmp/livara-install-forks.py
COPY dist/livara-desktop_0.1.0_all.deb build/configure-rootfs.sh build/live-selftest.sh build/livara-selftest.service /tmp/livara-build/
RUN install -D -m 0755 /tmp/livara-build/live-selftest.sh /usr/lib/livara/live-selftest \
    && install -m 0644 /tmp/livara-build/livara-selftest.service /etc/systemd/system/livara-selftest.service \
    && dpkg -i /tmp/livara-build/livara-desktop_0.1.0_all.deb \
    && bash /tmp/livara-build/configure-rootfs.sh && rm -rf /tmp/livara-build
CMD ["/sbin/init"]

FROM ${UBUNTU_BASE} AS assembler
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca \
    set -eux; \
    if [ -s /run/secrets/proxy_ca ]; then printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99livara-build-ca; fi; \
    apt-get update; apt-get install -y --no-install-recommends \
      squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin grub-common mtools \
      qemu-system-x86 ovmf python3 python3-pil; \
    apt-get clean; rm -rf /var/lib/apt/lists/*; rm -f /etc/apt/apt.conf.d/99livara-build-ca
COPY --chmod=0755 build/assemble.sh /usr/local/bin/livara-assemble
COPY build/grub.cfg /usr/local/share/livara-build/grub.cfg
ENTRYPOINT ["/usr/local/bin/livara-assemble"]

