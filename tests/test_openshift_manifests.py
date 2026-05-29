"""Validation tests for Phase 6 OpenShift manifests."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OPENSHIFT_CONFIG = ROOT / "config" / "openshift"
MANIFESTS = ROOT / "manifests"

YAML_FILES = [
    OPENSHIFT_CONFIG / "agent-policy-configmap.yaml",
    OPENSHIFT_CONFIG / "app-configmap.yaml",
    OPENSHIFT_CONFIG / "secrets.yaml",
    MANIFESTS / "namespace.yaml",
    MANIFESTS / "deployment.yaml",
    MANIFESTS / "service.yaml",
    MANIFESTS / "route.yaml",
    MANIFESTS / "hpa.yaml",
    MANIFESTS / "network-policy.yaml",
    ROOT / "kustomization.yaml",
]


def load_yaml(path: Path):
    """Load a single-document YAML file."""
    return yaml.safe_load(path.read_text())


def test_openshift_yaml_files_are_parseable():
    """All OpenShift YAML files should parse as valid YAML."""
    for path in YAML_FILES:
        assert path.exists(), f"missing {path}"
        assert load_yaml(path), f"empty YAML document in {path}"


def test_kustomization_references_all_phase_6_resources():
    """The root kustomization should include all Phase 6 resources."""
    kustomization = load_yaml(ROOT / "kustomization.yaml")
    assert kustomization["kind"] == "Kustomization"
    assert set(kustomization["resources"]) == {
        "manifests/namespace.yaml",
        "config/openshift/agent-policy-configmap.yaml",
        "config/openshift/app-configmap.yaml",
        "config/openshift/secrets.yaml",
        "manifests/deployment.yaml",
        "manifests/service.yaml",
        "manifests/route.yaml",
        "manifests/hpa.yaml",
        "manifests/network-policy.yaml",
    }


def test_deployment_mounts_openshell_policy_and_uses_health_probes():
    """Deployment should mount policy ConfigMap and expose app health endpoints."""
    deployment = load_yaml(MANIFESTS / "deployment.yaml")
    assert deployment["kind"] == "Deployment"
    assert deployment["metadata"]["namespace"] == "anytype"
    assert deployment["spec"]["replicas"] == 3

    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert "runAsUser" not in pod_spec["securityContext"]

    container = pod_spec["containers"][0]
    assert container["name"] == "agent"
    assert container["ports"][0]["containerPort"] == 8000
    assert {ref_key for env_from in container["envFrom"] for ref_key in env_from} == {
        "configMapRef",
        "secretRef",
    }
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert "ALL" in container["securityContext"]["capabilities"]["drop"]

    mounts = {mount["name"]: mount for mount in container["volumeMounts"]}
    assert mounts["openshell-policy"]["mountPath"] == "/etc/openshell/policies"
    assert mounts["openshell-policy"]["readOnly"] is True

    volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
    policy_volume = volumes["openshell-policy"]["configMap"]
    assert policy_volume["name"] == "anytype-agent-policy"
    assert {item["key"] for item in policy_volume["items"]} == {
        "sandbox-policy.yaml",
        "inference-policy.yaml",
        "provider.yaml",
    }


def test_policy_configmap_contains_expected_openshell_policies():
    """OpenShell policy ConfigMap should enforce filesystem, network, and process rules."""
    configmap = load_yaml(OPENSHIFT_CONFIG / "agent-policy-configmap.yaml")
    assert configmap["kind"] == "ConfigMap"
    assert configmap["metadata"]["name"] == "anytype-agent-policy"

    data = configmap["data"]
    sandbox_policy = yaml.safe_load(data["sandbox-policy.yaml"])
    inference_policy = yaml.safe_load(data["inference-policy.yaml"])
    provider_policy = yaml.safe_load(data["provider.yaml"])

    assert sandbox_policy["sandbox"]["name"] == "anytype-agent"
    assert "/host" in sandbox_policy["filesystem"]["blocked"]
    assert {entry["host"] for entry in sandbox_policy["network"]["allow"]} >= {
        "anytype-cli",
        "api.openai.com",
    }
    assert "sudo" in sandbox_policy["process"]["blocked"]
    assert inference_policy["inference"]["privacy"]["strip_credentials"] is True
    assert {provider["name"] for provider in provider_policy["providers"]} >= {"anytype", "openai"}


def test_service_route_hpa_and_network_policy_target_agent():
    """Service, Route, HPA, and NetworkPolicy should consistently target the app."""
    service = load_yaml(MANIFESTS / "service.yaml")
    route = load_yaml(MANIFESTS / "route.yaml")
    hpa = load_yaml(MANIFESTS / "hpa.yaml")
    network_policy = load_yaml(MANIFESTS / "network-policy.yaml")

    assert service["spec"]["selector"]["app.kubernetes.io/name"] == "anytype-agent"
    assert service["spec"]["ports"][0]["port"] == 8000
    assert route["apiVersion"] == "route.openshift.io/v1"
    assert route["spec"]["to"]["name"] == "anytype-agent"
    assert route["spec"]["tls"]["insecureEdgeTerminationPolicy"] == "Redirect"
    assert hpa["spec"]["scaleTargetRef"]["name"] == "anytype-agent"
    assert hpa["spec"]["minReplicas"] == 1
    assert hpa["spec"]["maxReplicas"] == 10
    assert network_policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"] == "anytype-agent"
    assert set(network_policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}


def test_network_policy_excludes_internal_and_metadata_ranges():
    """Internet egress should not include private, loopback, or metadata addresses."""
    network_policy = load_yaml(MANIFESTS / "network-policy.yaml")
    internet_egress = next(
        rule
        for rule in network_policy["spec"]["egress"]
        if rule.get("to", [{}])[0].get("ipBlock", {}).get("cidr") == "0.0.0.0/0"
    )

    assert set(internet_egress["to"][0]["ipBlock"]["except"]) >= {
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
    }


def test_single_agent_deployment_does_not_configure_openshell_gateway():
    """Phase 6 is single-agent mode and must not deploy or reference a Gateway."""
    for path in YAML_FILES:
        text = path.read_text().lower()
        assert "openshell-gateway" not in text
        assert "gatewayurl" not in text
        assert "kind: gateway" not in text
