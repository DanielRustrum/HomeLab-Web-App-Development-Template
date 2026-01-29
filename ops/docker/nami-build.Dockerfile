FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    git \
    make \
    nodejs \
    npm \
    python3 \
    python3-build \
    python3-pip \
    python3-venv \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g typescript

WORKDIR /workspace

CMD ["make", "build"]
