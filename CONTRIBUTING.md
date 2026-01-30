# Contributing

Thanks for helping improve the framework. This repo has two primary workflows:

1) Testing the `nami` CLI in a contained environment.
2) Developing the framework itself.

Both are driven by the Makefile targets below.

## Quick start

```bash
make dev
```

This starts a contained Ubuntu environment (via Docker Compose) for testing the `nami` CLI.

```bash
make workspace
```

This starts the framework workspace container for feature development.

## Project structure

High-level layout:

```
.
├─ ops/                     # Devops files and scripts (docker + helpers)
├─ src/                     # Framework source (CLI, orchestrator, core runtime)
├─ template/                # Project template parent (contains app/)
├─ releases/                # Built CLI artifacts
├─ docs/                    # Documentation and generated autodocs
└─ Makefile                 # Common developer commands
```

Key folders:

- `src/cli`  
  The `nami` CLI and its subcommands. `make build` packages this into `releases/bin`.

- `src/orchestrator`  
  The orchestrator that compiles `template/app` into a runtime workspace and
  builds frontend assets via the embedded Vite setup in `src/orchestrator/vite`.

- `src/python_module`  
  The core runtime package (`tsunami`) used by generated projects.

- `src/routing`  
  Request routing and dynamic endpoint plumbing used by the runtime.

- `template/app`  
  The source template for new projects. `nami init` copies this directory as-is.
  Do not modify or clean it in automation.

## How it works

At a high level:

1) The `nami` CLI can initialize a new project by copying `template/app`.
2) The orchestrator compiles the template into a runtime layout:
   - Python endpoints from `template/app/routes/*.py` are staged under `endpoint/`.
   - Route pages from `template/app/routes/*.tsx` are staged under `routing/`.
   - Utilities and optional config/init files are copied into the runtime root.
3) Asset builds are handled by the Vite project under `src/orchestrator/vite`,
   which uses generated entries from the template routes.
4) The runtime server starts using the `tsunami` package (`src/python_module`)
   and the routing layer (`src/routing`).

## Makefile targets

```bash
make help
```

Key targets:

- `make dev`  
  Spins up the contained environment for testing the `nami` CLI using
  `ops/docker/nami-dev.compose.yaml`.

- `make workspace`  
  Starts the framework workspace container using
  `ops/docker/workspace.compose.yaml`.

- `make build`  
  Builds the `nami` command into `releases/bin` using `ops/scripts/build_nami.sh`.

- `make document`  
  Generates autodocs into `docs/autodoc` using `ops/scripts/document.sh`.

- `make clean`  
  Prunes cache/build artifacts using `ops/scripts/clean.sh`.  
  Note: this does **not** modify the `template/` directory.

## Docker environment

Container image:

- `ops/docker/Dockerfile` (Ubuntu 24.04 + Python tooling)
- Default command: `sleep infinity`
- Repo is bind-mounted to `/workspace`

Port remapping:

The container exposes port `23541`. You can remap via `TSUNAMI_PORT`:

```bash
TSUNAMI_PORT=24500 make dev
```

## Docs generation

`make document` runs `ops/scripts/document.sh`, which uses `pydoc` to generate
HTML docs into `docs/autodoc`. If you prefer Sphinx/MkDocs/pdoc, update that
script and document the change here.

## Clean behavior

`make clean` removes caches and build artifacts (Python caches, node_modules,
dist, etc.). It does **not** touch `template/` because `nami` uses that folder
to generate new projects.
