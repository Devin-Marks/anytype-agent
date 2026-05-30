# Agent Notes: Architecture

Read this when changing project structure, high-level data flow, module boundaries, graph behavior, or core data models.

## What This Project Is

Anytype-Agent is a specialized FastAPI + LangGraph service for interacting with Anytype. It exposes a stateless, one-off request agent with Anytype-focused tools, guardrail nodes, SSE streaming, optional Agent-to-Agent (A2A) protocol support, LLM provider abstraction, and Kubernetes/OpenShift deployment manifests.

It is not a general-purpose shell agent or unrestricted automation runtime. Anytype operations should flow through explicit typed tools, safety checks, and Pydantic request/response schemas.

The architectural source of truth is split between:

- `IMPLEMENTATION_PLAN.md` — roadmap, phase dependencies, target project structure.
- `implementation/phases/*.md` — detailed implementation notes for each subsystem.
- Checked-in code and tests — current behavior when phase docs and implementation differ.

---

## Core Architecture Decisions

- **Web framework:** FastAPI + uvicorn.
- **Agent graph:** LangGraph `StateGraph`.
- **Request model:** Stateless one-off requests; no checkpointer by default.
- **Guardrails:** Input and output guardrails are graph nodes, not prompt-only comments.
- **Streaming:** Server-Sent Events for user-facing progress and output.
- **LLM access:** Provider abstraction under `src/llm/`; graph nodes should not hard-code provider quirks.
- **Anytype access:** Only through registered tools under `src/graph/tools/` with validated inputs.
- **Deployment:** Containerized FastAPI app with Kubernetes/OpenShift manifests.
- **Security posture:** Prefer explicit allowlists, graceful degradation, safe errors, and no committed secrets.

---

## Repository Layout

```text
Anytype-Agent/
├── src/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Pydantic settings / environment config
│   ├── schemas.py                 # Public request/response models
│   ├── api/
│   │   ├── streaming.py           # SSE streaming endpoints
│   │   └── a2a/                   # A2A API route support
│   ├── a2a/                       # A2A protocol primitives/client/server helpers
│   ├── auth/                      # Local auth helpers and CLI entrypoints
│   ├── graph/
│   │   ├── state.py               # LangGraph AgentState
│   │   ├── builder.py             # StateGraph construction
│   │   ├── nodes/                 # Guardrails, intent parsing, routing, formatting
│   │   └── tools/                 # Anytype-specific typed tools and registry
│   ├── llm/                       # LLM provider interface, providers, router
│   ├── pi_integration/            # Integration adapters for pi/A2A use
│   └── safety/                    # Sandbox, container health, security events/state
├── tests/                         # Unit/integration coverage for modules and API behavior
├── implementation/phases/          # Phase-by-phase implementation specs
├── docs/                          # Operator and agent-facing documentation
├── config/                        # Runtime/deployment config examples
├── manifests/                     # Kubernetes/OpenShift resources
├── pyproject.toml                 # Python package metadata and tool config
├── Dockerfile                     # Production image
└── AGENTS.md                      # Always-loaded agent instructions
```

Prefer extending the existing modules over creating parallel stacks. For example, add A2A behavior to the existing `src/a2a/` / `src/api/a2a/` areas rather than introducing a second protocol tree.

---

## Request and Graph Flow

```text
HTTP client
  │
  ├─ POST request / streaming request
  │
  ▼
FastAPI endpoint (`src/main.py`, `src/api/*`)
  │ validates Pydantic request models and configuration
  ▼
LangGraph graph (`src/graph/builder.py`)
  │
  ├─ input guardrails
  ├─ intent parser
  ├─ tool router
  ├─ Anytype tool execution (`src/graph/tools/*`)
  ├─ response formatter
  └─ output guardrails
  │
  ▼
Pydantic response or SSE events
```

Streaming endpoints should emit stable event types and safe payloads. Graph/tool failures should become structured errors or failure events rather than uncaught tracebacks to clients.

---

## Major Subsystems

### FastAPI API Layer

- Owns HTTP route registration, request validation, response models, and status codes.
- Should keep business logic thin and delegate graph work, tool execution, LLM calls, and safety checks to focused modules.
- Expected validation failures should become `4xx`; internal unexpected failures should become safe `5xx` responses with enough operator diagnostics in logs.

### LangGraph Layer

- `src/graph/state.py` defines the state contract shared by nodes.
- `src/graph/builder.py` constructs the graph and edge flow.
- Nodes in `src/graph/nodes/` should each do one job: guardrail, intent parse, route, format, etc.
- State mutations must be predictable and covered by tests.

### Anytype Tool Layer

- Tools live in `src/graph/tools/` and are exposed through a registry.
- Tool inputs should be explicit and validated before execution.
- Tool outputs should distinguish success, expected user-facing failures, and unexpected operational failures.
- Avoid destructive bulk operations or whole-object deletion unless explicitly designed with safeguards.

### LLM Layer

- Provider-independent contracts live in `src/llm/base.py`.
- Provider implementations and routing live under `src/llm/`.
- Provider-specific authentication, model naming, retries, or compatibility behavior should not leak into graph nodes.

### Safety Layer

- Sandbox/container/security checks live in `src/safety/`.
- OpenShell integration is optional and should degrade gracefully when unavailable in local development.
- Do not rely on prompt instructions as the only safety boundary for tool or shell behavior.

### A2A Layer

- A2A metadata, server/router behavior, and clients live in the existing `src/a2a/` and `src/api/a2a/` modules.
- Keep protocol models stable and tested because other agents may depend on them.

### Deployment Layer

- `Dockerfile`, `config/`, `manifests/`, and `kustomization.yaml` define deployable artifacts.
- Keep placeholder values safe to commit. Real API keys, OAuth tokens, cluster credentials, and generated secrets must never be committed.
- Read `docs/container.md` before changing container or Kubernetes/OpenShift behavior.

---

## Phase Dependency Map

Implementation should respect the plan's dependency order unless the user asks otherwise:

1. Project setup: package metadata, config, schemas, app skeleton.
2. State schema and graph structure.
3. Anytype tool registry and tool implementations.
4. Shell/OpenShell protection and container security.
5. SSE streaming.
6. Kubernetes/OpenShift deployment.
7. A2A protocol.
8. LLM provider abstraction.
9. Rate limiting.
10. Observability and tracing.
11. Resilience: retries, circuit breakers, timeouts, graceful degradation.

Later phases should not backdoor around earlier safety and schema layers.

---

## Critical Conventions

1. **Keep API contracts typed.** Use Pydantic models for public request/response boundaries.
2. **Keep graph state typed.** Update `src/graph/state.py` and tests when state shape changes.
3. **Route Anytype behavior through tools.** Do not place direct Anytype API calls in endpoints or generic graph nodes.
4. **Keep provider specifics in `src/llm/`.** Graph nodes call provider abstractions, not concrete SDKs directly.
5. **Safety checks are code, not only prompts.** Guardrails, sandbox checks, and destructive-operation safeguards must be enforceable and tested.
6. **Errors must be user-safe.** Do not leak secrets, auth files, bearer tokens, redirect URLs, or sensitive Anytype content.
7. **Tests accompany behavior.** New endpoints, graph nodes, tools, providers, safety checks, and middleware need tests in `tests/`.
8. **Lint after implementation.** Run `python -m ruff check .` after code changes when practical.
