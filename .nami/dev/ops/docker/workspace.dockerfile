FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# Base tools + Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash \
    postgresql-client \
    python3 python3-venv python3-pip \
    util-linux \
  && rm -rf /var/lib/apt/lists/*

# --- Python venv as the default python3/pip ---
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV" \
  && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir -U pip setuptools wheel

# OPTIONAL (recommended): install your project deps
# COPY src/backend/requirements.txt /tmp/requirements.txt
# RUN "$VIRTUAL_ENV/bin/pip" install --no-cache-dir -r /tmp/requirements.txt

# Make venv the default python/pip no matter what shell VS Code uses
RUN ln -sf "$VIRTUAL_ENV/bin/python" /usr/local/bin/python \
 && ln -sf "$VIRTUAL_ENV/bin/python" /usr/local/bin/python3 \
 && ln -sf "$VIRTUAL_ENV/bin/pip" /usr/local/bin/pip \
 && ln -sf "$VIRTUAL_ENV/bin/pip" /usr/local/bin/pip3
# ---------------------------------------------


# Node 20 + npm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get update && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/*

# --- Python venv (fixes "Import cherrypy could not be resolved") ---
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV" \
  && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir -U pip setuptools wheel
COPY src/backend/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
 && /opt/venv/bin/pip install --no-cache-dir watchfiles

ENV PATH="$VIRTUAL_ENV/bin:$PATH"
# ---------------------------------------------------------------

# Create a non-root dev user
RUN useradd -m -s /bin/bash coder

WORKDIR /workspaces/app

# Copy bootstrap scripts
COPY ops/docker/workspace.entrypoint.sh /usr/local/bin/workspace-entrypoint
COPY ops/docker/workspace.bootstrap.sh /usr/local/bin/workspace-bootstrap
RUN chmod +x /usr/local/bin/workspace-entrypoint /usr/local/bin/workspace-bootstrap

ENTRYPOINT ["workspace-entrypoint"]

CMD ["bash", "-lc", "sleep infinity"]
