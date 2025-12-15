FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# Base tools + Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash \
    postgresql-client \
    python3 python3-venv python3-pip \
    util-linux \
  && rm -rf /var/lib/apt/lists/*

# Node 20 + npm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# Create a non-root dev user
RUN useradd -m -s /bin/bash coder

WORKDIR /workspaces/app

# Copy bootstrap scripts
COPY docker/workspace.entrypoint.sh /usr/local/bin/workspace-entrypoint
COPY docker/workspace.bootstrap.sh /usr/local/bin/workspace-bootstrap
RUN chmod +x /usr/local/bin/workspace-entrypoint /usr/local/bin/workspace-bootstrap

ENTRYPOINT ["workspace-entrypoint"]

# Keep container alive by default
CMD ["bash", "-lc", "sleep infinity"]
