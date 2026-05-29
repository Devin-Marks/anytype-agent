# OpenShift deployment

These manifests deploy `anytype-agent` into the `anytype` namespace with OpenShell policies mounted from a ConfigMap. This single-agent deployment intentionally does **not** deploy the OpenShell Gateway; Kubernetes manages lifecycle through normal Deployment rollouts.

## Prerequisites

- OpenShift 4.x with `oc` access
- An image for this application, for example the default placeholder `ghcr.io/your-org/anytype-agent:latest`. See `docs/container.md` for build and tag guidance.
- OpenShell CLI/runtime is optional at image build time. If it is not installed from the declared `openshell` extra, the app starts without sandbox isolation and reports that state from `/health/sandbox`.
- An `anytype-cli` Service/Pod reachable as `http://anytype-cli:31012` in the `anytype` namespace

## Configure secrets

Edit `config/openshift/secrets.yaml` before applying:

- `ANYTYPE_API_KEY`
- `OPENAI_API_KEY`
- optional `ANTHROPIC_API_KEY`
- OpenShell provider values if your runtime consumes `OPENSHELL_PROVIDER_*`

Do not commit real secret values.

## Deploy

```bash
oc apply -k .
oc rollout status deployment/anytype-agent -n anytype
oc get route anytype-agent -n anytype
```

## Update policy or app config

```bash
oc apply -f config/openshift/agent-policy-configmap.yaml
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
