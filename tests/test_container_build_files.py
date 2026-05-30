"""Static validation for container build support."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_installs_project_and_runs_uvicorn():
    """Dockerfile should build the package and run the FastAPI app on port 8000."""
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12-slim-bookworm AS builder" in dockerfile
    assert "FROM python:3.12-slim-bookworm AS runtime" in dockerfile
    assert "COPY pyproject.toml" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "pip wheel" in dockerfile
    assert "pip install --no-index --find-links=/wheels anytype-agent" in dockerfile
    assert "USER 10001" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert '["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile


def test_dockerignore_excludes_sensitive_and_heavy_paths():
    """Docker build context should exclude secrets, VCS metadata, and caches."""
    ignored = set((ROOT / ".dockerignore").read_text().splitlines())

    assert ".git" in ignored
    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "__pycache__/" in ignored
    assert ".pytest_cache/" in ignored
    assert ".ruff_cache/" in ignored
    assert "implementation/" in ignored


def test_deployment_uses_project_image_placeholder():
    """Manifest image should point at an Anytype Agent placeholder, not an unrelated image."""
    deployment = (ROOT / "manifests" / "deployment.yaml").read_text()

    assert "image: ghcr.io/your-org/anytype-agent:latest" in deployment
    assert "ghcr.io/anytype/agent:latest" not in deployment


def test_codex_kubernetes_workflow_documented():
    """Docs should explain opt-in Codex subscription auth without committing tokens."""
    docs = (ROOT / "docs" / "container.md").read_text()

    assert "LLM_PROVIDER=openai-codex" in docs
    assert "/var/lib/anytype-agent/auth.json" in docs
    assert "python -m src.auth login openai-codex" in docs
    assert "python -m src.auth status openai-codex" in docs
    assert "python -m src.auth logout openai-codex" in docs
    assert "kubectl exec -n anytype" in docs
    assert "CODEX_AUTH_FILE" not in docs
    assert "CODEX_TOKEN_COMMAND" not in docs
    assert "codex login" not in docs
    assert "kubectl create secret generic anytype-agent-codex-auth" not in docs
    assert "Never commit `auth.json`" in docs
