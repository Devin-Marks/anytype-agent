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
