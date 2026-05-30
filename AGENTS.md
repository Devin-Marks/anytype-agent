# AGENTS.md

This file is the always-loaded entrypoint for coding agents working on Anytype-Agent.
Keep it short and reliable. Detailed implementation guidance lives in
`IMPLEMENTATION_PLAN.md`, `implementation/phases/*`, and focused docs under `docs/`.
Read the relevant files before touching that area.

---

## What This Project Is

Anytype-Agent is a specialized FastAPI + LangGraph service for interacting with
Anytype. It exposes a stateless, single-purpose agent with Anytype-focused tools,
input/output guardrails, SSE streaming, optional Agent-to-Agent (A2A) support,
LLM provider abstraction, and deployment manifests for Kubernetes/OpenShift.

This project should not become a general shell agent or unrestricted automation
runtime. Anytype operations must be routed through explicit typed tools, safety
checks, and request/response schemas.

---

## Required Reading by Task

Before making changes, read the most specific guide(s):

| If you are touching... | Read first |
|---|---|
| High-level architecture, repo layout, data flow, module boundaries | `docs/agent/architecture.md` |
| Overall roadmap, architecture decisions, phase ordering | `IMPLEMENTATION_PLAN.md` |
| Project skeleton, config, app startup, base schemas | `implementation/phases/phase-1-setup.md` |
| LangGraph state, graph builder, nodes, routing | `implementation/phases/phase-2-graph.md` |
| Anytype tool implementations and registry | `implementation/phases/phase-2b-tools.md` |
| Shell/OpenShell protection and sandbox lifecycle | `implementation/phases/phase-3-shell-protection.md` |
| Container security, health checks, security events | `implementation/phases/phase-4-container-security.md` and `docs/container.md` |
| SSE event shape and streaming endpoint behavior | `implementation/phases/phase-5-streaming.md` |
| Kubernetes/OpenShift manifests, deployment config | `implementation/phases/phase-6-openshift.md` and `docs/container.md` |
| Cutting a release, bumping versions, release notes | `docs/agent/releases.md` |
| A2A agent card, server, router, client | `implementation/phases/phase-7-a2a.md` |
| LLM provider abstraction and routing | `implementation/phases/phase-8-llm-abstraction.md` |
| Rate limiting middleware | `implementation/phases/phase-9-rate-limiting.md` |
| Observability, tracing, logs, metrics | `implementation/phases/phase-10-observability.md` |
| Retries, circuit breakers, timeouts, graceful degradation | `implementation/phases/phase-11-resilience.md` |
| End-of-session PR description or handoff summary | `docs/agent/prs.md` |

When phase docs and checked-in code disagree, inspect the code and tests first,
then update docs in the same change if behavior intentionally changed.

---

## Build, Test, and Lint Commands

```bash
python -m pip install -e '.[dev]'   # Install package with dev tools
python -m pytest                    # Run the full test suite
python -m pytest tests/test_tools.py # Run a focused test file
python -m ruff check .              # Lint after implementation
python -m mypy src tests            # Type-check when changing typed Python APIs
python check-syntax.js              # Quick syntax check used by this repo
uvicorn src.main:app --reload       # Local FastAPI dev server
```

Run the strongest practical checks before handing off. For docs-only changes, a
syntax/lint run may be enough. For behavior changes, add or update tests in the
same change and run the relevant focused tests plus the full suite when practical.

---

## Implementation Standards

1. **Design for structure first.** Keep modules small, typed, and purpose-specific.
   Prefer explicit interfaces and registries over ad-hoc branching.
2. **Bake in error handling on the initial implementation.** Map expected failures
   to typed results or HTTP errors; do not leave broad `except Exception` blocks
   without logging and a clear user-safe response.
3. **Bake in tests on the initial implementation.** New nodes, tools, providers,
   middleware, safety checks, and endpoints should land with unit or integration
   coverage in `tests/`.
4. **Lint after implementation.** Run `python -m ruff check .` and fix violations
   before handoff unless the user explicitly asks for a partial prototype.
5. **Keep request and response shapes explicit.** Use Pydantic models in
   `src/schemas.py` or focused modules rather than unvalidated dictionaries at API
   boundaries.
6. **Keep LangGraph state predictable.** State changes should be clear, typed, and
   covered by tests; nodes should not smuggle unrelated side effects into state.
7. **Do not expose unrestricted shell access.** Shell/OpenShell integration must be
   constrained by the safety modules and phase guidance.
8. **Do not commit secrets.** API keys, OAuth tokens, redirect URLs, `auth.json`,
   kube secrets, and generated credentials must stay out of git.
9. **Prefer graceful degradation.** Optional integrations such as OpenShell,
   observability backends, or specific LLM providers should fail with actionable
   messages when unavailable.
10. **Use structured logs and safe errors.** Preserve diagnostics for operators but
    do not leak credentials or sensitive Anytype content in errors.

---

## Architecture Guardrails

- FastAPI app entrypoint lives in `src/main.py`.
- Runtime configuration belongs in `src/config.py` and should be environment-driven
  through Pydantic settings.
- Public API models should be Pydantic schemas, not untyped dict contracts.
- LangGraph construction belongs under `src/graph/`; Anytype callable tools belong
  under `src/graph/tools/`.
- Safety-sensitive behavior belongs under `src/safety/` and should be covered by
  explicit tests.
- LLM provider implementations belong under `src/llm/`; provider-specific quirks
  should not leak into graph nodes.
- A2A support belongs under the existing `src/a2a/` / `src/api/a2a/` modules; avoid
  creating parallel protocol stacks without consolidating the old one.
- Kubernetes/OpenShift manifests and config should remain deployable with
  placeholder values only; never hard-code local cluster secrets.

---

## Anytype Tooling Rules

- The agent should only perform Anytype operations through registered tools with
  explicit input validation.
- Tool failures should return useful, safe error messages and be covered by tests.
- Avoid whole-object deletion or destructive bulk operations unless a phase doc and
  user request explicitly require them with safeguards.
- Keep Anytype-specific safety checks close to the tool or in `src/safety/` rather
  than relying on prompt-only guardrails.

---

## End-of-Session PR Summaries

When preparing a PR description or merge-ready handoff, read `docs/agent/prs.md`
and use its Summary / Usage / What changed / Test plan structure.
