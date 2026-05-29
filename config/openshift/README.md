# OpenShift deployment

These manifests deploy `anytype-agent` into the `anytype` namespace as a normal OpenShift/Kubernetes `Deployment`. They do **not** deploy NVIDIA OpenShell and do **not** activate OpenShell isolation by mounting policy files.

The included `agent-policy-configmap.yaml` is retained as a reference for the intended Anytype/LLM allow-list policy shape, but NVIDIA OpenShell policy enforcement requires the OpenShell gateway/supervisor path documented by NVIDIA, not this standalone app Deployment.

## Prerequisites for this app Deployment

- OpenShift 4.x with `oc` access.
- An image for this application, for example `ghcr.io/your-org/anytype-agent:latest`. See `docs/container.md` for build and tag guidance.
- An `anytype-cli` Service/Pod reachable as `http://anytype-cli:31012` in the `anytype` namespace.
- Secrets configured without committing real values.

## OpenShell on OpenShift

NVIDIA's OpenShift path is separate and currently experimental:

- Documentation: <https://docs.nvidia.com/openshell/latest/kubernetes/openshift>
- Requires Helm 3.x and the Kubernetes SIG Agent Sandbox controller/CRDs.
- Requires sandbox pods to run under the `privileged` SCC:

```bash
oc create ns openshell
oc adm policy add-scc-to-user privileged -z openshell-sandbox -n openshell
```

- NVIDIA's documented OpenShift chart overrides are:

```bash
helm install openshell oci://ghcr.io/nvidia/openshell/helm-chart \
  --version <version> \
  --namespace openshell \
  --set pkiInitJob.enabled=false \
  --set server.disableTls=true \
  --set podSecurityContext.fsGroup=null \
  --set securityContext.runAsUser=null
```

Because that disables the chart PKI job and TLS, use it only for evaluation on a private/trusted network unless you provide a supported TLS/access-proxy setup.

## Configure secrets

Edit `config/openshift/secrets.yaml` before applying:

- `ANYTYPE_API_KEY`
- `LLM_API_KEY` for hosted providers that require a key. For local/keyless endpoints such as Ollama, leave it empty and set `LLM_PROVIDER`/`LLM_BASE_URL` in `app-configmap.yaml`.
- optional `GUARDRAIL_LLM_API_KEY` when guardrails should use a different key from the main LLM.

Prefer these generic app settings in `app-configmap.yaml`:

- `LLM_PROVIDER` (`openai` for OpenAI-compatible chat completions, `anthropic`, or `ollama`)
- `LLM_BASE_URL`
- `LLM_MODEL`
- optional `GUARDRAIL_LLM_PROVIDER`, `GUARDRAIL_LLM_BASE_URL`, and `GUARDRAIL_MODEL`

Legacy `DEFAULT_PROVIDER`, `MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `OLLAMA_BASE_URL` are still recognized for compatibility, but new deployments should use the generic names above. Do not commit real secret values.

## Deploy this app

```bash
oc apply -k .
oc rollout status deployment/anytype-agent -n anytype
oc get route anytype-agent -n anytype
```

## Update app config

```bash
oc apply -f config/openshift/app-configmap.yaml
oc rollout restart deployment/anytype-agent -n anytype
oc rollout status deployment/anytype-agent -n anytype
```

The Deployment also includes Stakater Reloader annotations for clusters that run Reloader.

## Validate locally

```bash
python3 -m pytest tests/test_openshift_manifests.py
```

If `kubectl` or `oc` is available, you can additionally run:

```bash
kubectl kustomize .
```
