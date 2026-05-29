"""Tests for src/safety/sandbox_manager.py."""
from unittest.mock import patch

import pytest

from src.safety.sandbox_manager import (
    SandboxManager,
    DevSandboxManager,
    SandboxConfig,
    SandboxState,
    _check_openshell_available,
    get_sandbox_manager,
)


class TestCheckOpenshellAvailable:
    """Tests for _check_openshell_available."""

    def test_no_openshell(self):
        """Should return False when no OpenShell is present."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("builtins.__import__", side_effect=ImportError):
                assert _check_openshell_available() is False

    def test_env_var_detected(self):
        """Should return True when OPENSHELL_SANDBOX_NAME is set."""
        with patch.dict("os.environ", {"OPENSHELL_SANDBOX_NAME": "test"}, clear=True):
            assert _check_openshell_available() is True

    def test_policy_path_env_var_is_not_runtime_detection(self):
        """Policy path config alone should not be treated as active isolation."""
        with patch.dict("os.environ", {"OPENSHELL_POLICY_PATH": "/etc/openshell/policy.yaml"}, clear=True):
            with patch("builtins.__import__", side_effect=ImportError):
                assert _check_openshell_available() is False

    def test_sandbox_id_env_var_detected(self):
        """Should return True when a known sandbox runtime marker exists."""
        with patch.dict("os.environ", {"OPENSHELL_SANDBOX_ID": "sandbox-1"}, clear=True):
            assert _check_openshell_available() is True


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.name == "anytype-agent"
        assert cfg.gpu is False
        assert cfg.provider == "anytype"

    def test_resolve_paths(self):
        cfg = SandboxConfig()
        resolved = cfg.resolve_paths()
        assert resolved.policy_file.endswith("config/openshell/sandbox-policy.yaml")
        assert resolved.inference_policy.endswith("config/openshell/inference-policy.yaml")


class TestSandboxManager:
    """Tests for SandboxManager."""

    @pytest.fixture(autouse=True)
    def _clear_singleton(self):
        """Clear singleton before/after each test."""
        import src.safety.sandbox_manager as sm
        sm._sandbox_manager = None
        yield
        sm._sandbox_manager = None

    def test_initial_state(self):
        mgr = SandboxManager()
        assert mgr.state == SandboxState.STOPPED
        assert mgr.sandbox_name is None

    @pytest.mark.asyncio
    async def test_create_sandbox_raises_when_unavailable(self):
        mgr = SandboxManager()
        mgr._openshell_available = False
        with pytest.raises(RuntimeError, match="not available"):
            await mgr.create_sandbox()

    @pytest.mark.asyncio
    async def test_create_sandbox_success(self):
        mgr = SandboxManager()
        mgr._openshell_available = True
        name = await mgr.create_sandbox()
        assert name.startswith("anytype-agent-")
        assert mgr.state == SandboxState.RUNNING
        assert mgr.sandbox_name == name

    @pytest.mark.asyncio
    async def test_apply_policy_without_sandbox(self):
        mgr = SandboxManager()
        with pytest.raises(RuntimeError, match="No sandbox running"):
            await mgr.apply_policy("policy.yaml")

    @pytest.mark.asyncio
    async def test_apply_policy_when_unavailable(self):
        mgr = SandboxManager()
        mgr._sandbox_name = "test-sandbox"
        mgr._openshell_available = False
        result = await mgr.apply_policy("policy.yaml")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_logs_when_unavailable(self):
        mgr = SandboxManager()
        mgr._sandbox_name = "test"
        mgr._openshell_available = False
        logs = await mgr.get_logs()
        assert "unavailable" in logs.lower() or logs == ""

    @pytest.mark.asyncio
    async def test_stop_sandbox(self):
        mgr = SandboxManager()
        mgr._sandbox_name = "test"
        await mgr.stop_sandbox()
        assert mgr.sandbox_name is None
        assert mgr.state == SandboxState.STOPPED


class TestDevSandboxManager:
    """Tests for DevSandboxManager."""

    @pytest.fixture(autouse=True)
    def _clear_singleton(self):
        import src.safety.sandbox_manager as sm
        sm._sandbox_manager = None
        yield
        sm._sandbox_manager = None

    def test_forces_unavailable(self):
        mgr = DevSandboxManager()
        assert mgr.is_available is False
        assert mgr._openshell_available is False

    @pytest.mark.asyncio
    async def test_create_sandbox_raises(self):
        mgr = DevSandboxManager()
        with pytest.raises(RuntimeError, match="not available"):
            await mgr.create_sandbox()


class TestGetSandboxManager:
    """Tests for get_sandbox_manager singleton."""

    def test_returns_same_instance(self):
        import src.safety.sandbox_manager as sm
        sm._sandbox_manager = None
        with patch("src.safety.sandbox_manager._check_openshell_available", return_value=False):
            m1 = get_sandbox_manager()
            m2 = get_sandbox_manager()
            assert m1 is m2
        sm._sandbox_manager = None

    def test_returns_dev_when_unavailable(self):
        import src.safety.sandbox_manager as sm
        sm._sandbox_manager = None
        with patch("src.safety.sandbox_manager._check_openshell_available", return_value=False):
            mgr = get_sandbox_manager()
            assert isinstance(mgr, DevSandboxManager)
        sm._sandbox_manager = None

    def test_returns_production_when_available(self):
        import src.safety.sandbox_manager as sm
        sm._sandbox_manager = None
        with patch("src.safety.sandbox_manager._check_openshell_available", return_value=True):
            mgr = get_sandbox_manager()
            assert isinstance(mgr, SandboxManager)
            assert not isinstance(mgr, DevSandboxManager)
        sm._sandbox_manager = None


class TestSandboxState:
    """Tests for SandboxState enum."""

    def test_states(self):
        assert SandboxState.STOPPED.value == "stopped"
        assert SandboxState.CREATING.value == "creating"
        assert SandboxState.RUNNING.value == "running"
        assert SandboxState.ERROR.value == "error"
