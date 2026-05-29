# Container build and Kubernetes deployment

This project includes a production-focused `Dockerfile` for the FastAPI/LangGraph application.
The image installs the package from `pyproject.toml`, exposes port `8000`, and starts:

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

The default build installs only the production dependencies declared in `pyproject.toml`.
The optional OpenShell extra is declared by the project, but availability depends on the package index and target platform. If you have verified access to that dependency, build with:

```bash
docker build --build-arg INSTALL_EXTRAS=openshell -t ghcr.io/your-org/anytype-agent:openshell .
```

Without OpenShell available, the application starts in development/no-isolation mode and `/health/sandbox` reports that OpenShell is unavailable.

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
