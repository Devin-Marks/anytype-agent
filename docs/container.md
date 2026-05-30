# Container build and Kubernetes deployment

This project includes a production-focused `Dockerfile` for the FastAPI/LangGraph application. The image installs the package from `pyproject.toml`, exposes port `8000`, and starts:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

The runtime image runs as UID `10001` with group `0` permissions on writable paths so it can work with standard Kubernetes `runAsNonRoot` settings and OpenShift's arbitrary-UID security model.

## Build and push

Replace the registry/tag with one your cluster can pull:

```bash
docker build -t ghcr.io/your-org/anytype-agent:latest .
docker push ghcr.io/your-org/anytype-agent:latest
```

Podman can be used with the same arguments:

```bash
podman build -t ghcr.io/your-org/anytype-agent:latest .
podman push ghcr.io/your-org/anytype-agent:latest
```

## NVIDIA OpenShell support

Authoritative references checked:

- NVIDIA OpenShell installation: <https://docs.nvidia.com/openshell/latest/about/installation>
- Kubernetes setup: <https://docs.nvidia.com/openshell/latest/kubernetes/setup>
- OpenShift setup: <https://docs.nvidia.com/openshell/latest/kubernetes/openshift>
- Compute drivers: <https://docs.nvidia.com/openshell/latest/reference/sandbox-compute-drivers>
- Support matrix: <https://docs.nvidia.com/openshell/latest/reference/support-matrix>
- PyPI package: <https://pypi.org/project/openshell/>

The package name is `openshell`; it is NVIDIA OpenShell's PyPI package and currently requires Python `>=3.12`. The Dockerfile therefore uses a Python 3.12 base image and the project extra pins a verified current minimum (`openshell>=0.0.51`). To build an image that includes the OpenShell CLI/client package:

```bash
docker build --build-arg INSTALL_EXTRAS=openshell -t ghcr.io/your-org/anytype-agent:openshell .
```

`pip install openshell` is **not sufficient** to make this application pod an OpenShell sandbox. NVIDIA documents OpenShell as a gateway/control-plane model: the gateway selects a compute driver, creates the sandbox, runs the supervisor inside the sandbox workload, applies policy, routes egress, and injects credentials. Kubernetes deployments require the official OpenShell Helm chart and the Kubernetes SIG Agent Sandbox controller/CRDs.

This repository's `manifests/` deploy a normal Kubernetes/OpenShift `Deployment` for the API service. They use Kubernetes security context and NetworkPolicy defense-in-depth, but they do not claim to activate OpenShell isolation by mounting policy files.

## Verified Kubernetes/OpenShell path

For Kubernetes, follow NVIDIA's Helm-based path instead of trying to containerize the gateway inside this app image:

1. Install Kubernetes 1.29+ with RBAC enabled and Helm 3.x.
2. Install the Agent Sandbox controller and CRDs before OpenShell.
3. Install the OpenShell chart from `oci://ghcr.io/nvidia/openshell/helm-chart` at an explicit chart version.
4. Configure chart values such as `server.sandboxImage` to point at an image that contains this app when you want OpenShell-created sandboxes to run `anytype-agent`.
5. Configure `server.grpcEndpoint` so sandbox supervisors can reach the gateway from inside the cluster.
6. Register/access the gateway using the mTLS/OIDC/access-proxy flow NVIDIA documents.

For OpenShift, NVIDIA marks the install path experimental. Their current documented path requires:

- OpenShift 4.x, Helm 3.x, Agent Sandbox controller and CRDs.
- `oc adm policy add-scc-to-user privileged -z openshell-sandbox -n openshell` for sandbox pods.
- Helm overrides: `pkiInitJob.enabled=false`, `server.disableTls=true`, `podSecurityContext.fsGroup=null`, and `securityContext.runAsUser=null`.
- Plaintext gateway use only on a private/trusted evaluation network unless you provide a supported TLS/access-proxy setup.

## Configure Kubernetes manifests

The checked-in Deployment uses the placeholder image `ghcr.io/your-org/anytype-agent:latest`. Set it to your pushed image before applying:

```bash
kubectl set image -n anytype deployment/anytype-agent agent=ghcr.io/your-org/anytype-agent:latest --local -o yaml
```

Or update `manifests/deployment.yaml` / a Kustomize overlay and apply:

```bash
kubectl apply -k .
kubectl rollout status deployment/anytype-agent -n anytype
```

Do not commit real API keys. The placeholder secret values in `config/openshift/secrets.yaml` must be replaced or managed through your cluster's secret-management flow before deployment.

## OpenAI Codex/ChatGPT subscription provider auth

`LLM_PROVIDER=openai-codex` enables an explicit, opt-in provider that uses a Codex/ChatGPT subscription bearer token instead of an OpenAI Platform API key. This is separate from `LLM_PROVIDER=openai` and is less stable/official for arbitrary server applications than the public OpenAI API. Keep it isolated to deployments where you accept that risk.

Configuration:

```bash
LLM_PROVIDER=openai-codex
LLM_MODEL=gpt-5-codex              # or another model available to your subscription
CODEX_AUTH_FILE=/var/lib/anytype-agent/codex/auth.json
# Optional: command that prints a fresh bearer token to stdout.
CODEX_TOKEN_COMMAND='codex-token-helper'
# Optional endpoint override; by default the provider uses the known Codex responses endpoint.
CODEX_BASE_URL=https://chatgpt.com/backend-api/codex/responses
# Optional OAuth refresh overrides; defaults match current Codex CLI/OpenCode behavior.
CODEX_AUTH_ISSUER=https://auth.openai.com
CODEX_CLIENT_ID=app_EMoamEEZ73f0CkXaXp7hrann
CODEX_REFRESH_SKEW_SECONDS=300
```

`CODEX_TOKEN_COMMAND` takes precedence over `CODEX_AUTH_FILE`. Use it when you have external tooling that safely refreshes the token and prints only the bearer token. The command is parsed into argv and executed without a shell, has a 15-second timeout, and error messages intentionally do not echo stderr because helpers may accidentally write secrets there.

Without a token command, the provider reads a Codex-compatible `auth.json`, extracts explicit access-token fields such as `access_token`/`accessToken`/`access`, detects expiry from common expiry fields or the JWT `exp` claim, and refreshes expired or near-expired ChatGPT/Codex access tokens using the same OAuth token endpoint, client id, and `refresh_token` grant used by current OpenAI Codex CLI/OpenCode implementations. Refreshed credentials preserve the existing token key style where practical and are written back atomically with `0600` file permissions where the filesystem supports it. This refresh flow is private subscription auth and may change; for production-style automation, OpenAI still recommends Platform API keys.

### Kubernetes exec login workflow

If your image or a debug/ephemeral container includes a verified Codex CLI, you may log in inside the pod and write the cache to a mounted volume:

```bash
kubectl exec -n anytype deploy/anytype-agent -c agent -- sh
# inside the container
export HOME=/var/lib/anytype-agent/codex-home
codex login --device-auth
cp "$HOME/.codex/auth.json" /var/lib/anytype-agent/codex/auth.json
```

Mount `/var/lib/anytype-agent/codex` from a writable PVC so the auth file survives restarts and automatic refresh can persist rotated refresh tokens. Set `CODEX_AUTH_FILE=/var/lib/anytype-agent/codex/auth.json`.

The checked-in Dockerfile does **not** install the Codex CLI. No validated package/install method is pinned in this repository, and the runtime image is kept minimal to avoid inventing unsupported install steps. Build a derived image only after you verify the CLI installation source/version for your environment, or use the Secret/PVC workflow below.

### Local login to Kubernetes Secret or PVC

A safer operational path is to authenticate locally with the Codex CLI, then copy only the resulting auth cache into Kubernetes storage. Prefer a writable PVC when you want Anytype-Agent to auto-refresh and persist rotated tokens:

```bash
codex login --device-auth
kubectl create secret generic anytype-agent-codex-auth \
  -n anytype \
  --from-file=auth.json="$HOME/.codex/auth.json"
```

Mounting that secret directly is acceptable only as a bootstrap or non-refreshing workflow. Kubernetes Secret volumes are read-only: Anytype-Agent can read a still-valid access token without taking a write lock, but it cannot persist refreshed credentials there once refresh is required, and refresh-token rotation may break future refreshes. For auto-refresh, copy the Secret into a writable PVC with an initContainer, or create/populate the PVC directly, then mount the PVC at `/var/lib/anytype-agent/codex`.

Writable PVC example:

```yaml
env:
  - name: LLM_PROVIDER
    value: openai-codex
  - name: LLM_MODEL
    value: gpt-5-codex
  - name: CODEX_AUTH_FILE
    value: /var/lib/anytype-agent/codex/auth.json
volumeMounts:
  - name: codex-auth-pvc
    mountPath: /var/lib/anytype-agent/codex
volumes:
  - name: codex-auth-pvc
    persistentVolumeClaim:
      claimName: anytype-agent-codex-auth
```

Read-only Secret example (no persisted auto-refresh unless copied to a writable volume first):

```yaml
env:
  - name: LLM_PROVIDER
    value: openai-codex
  - name: LLM_MODEL
    value: gpt-5-codex
  - name: CODEX_AUTH_FILE
    value: /var/lib/anytype-agent/codex/auth.json
volumeMounts:
  - name: codex-auth
    mountPath: /var/lib/anytype-agent/codex/auth.json
    subPath: auth.json
    readOnly: true
volumes:
  - name: codex-auth
    secret:
      secretName: anytype-agent-codex-auth
```

Never commit `auth.json` or bearer tokens. Rotate/delete the Kubernetes Secret when access should be revoked.
