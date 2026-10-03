from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Protocol


PROFILE_SCHEMA = "agentos.executor-provider-profile/v0.1"


class ExecutorProvider(Protocol):
    executor_id: str
    provider_id: str
    executor_class: str

    def discover(self) -> dict[str, Any]: ...
    def capabilities(self) -> Iterable[str]: ...
    def health(self) -> dict[str, Any]: ...
    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def cancel(self, invocation_id: str) -> dict[str, Any]: ...
    def receipt(self, invocation_id: str) -> dict[str, Any]: ...


def _default_profile_root() -> Path:
    override = os.environ.get("AGENTOS_EXECUTOR_PROFILE_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / ".agentos" / "executors"


def _require_string(profile: dict[str, Any], key: str) -> str:
    value = str(profile.get(key) or "").strip()
    if not value:
        raise ValueError(f"executor profile missing {key}")
    return value


def validate_provider_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("executor provider profile must be an object")
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("unsupported executor provider profile schema")

    _require_string(profile, "executor_id")
    _require_string(profile, "provider_id")
    _require_string(profile, "executor_class")

    modes = profile.get("modes")
    if not isinstance(modes, list) or not modes or not all(isinstance(x, str) and x.strip() for x in modes):
        raise ValueError("executor profile modes must be non-empty strings")

    capabilities = profile.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(x, str) and x.strip() for x in capabilities):
        raise ValueError("executor profile capabilities must be strings")

    discovery = profile.get("discovery")
    if not isinstance(discovery, dict):
        raise ValueError("executor profile discovery is required")
    if discovery.get("provider_owned_allowlists_only") is not True:
        raise ValueError("provider-owned discovery allowlists are required")
    if discovery.get("credential_access") is not False:
        raise ValueError("executor discovery may not access credentials")

    invocation = profile.get("invocation")
    if not isinstance(invocation, dict):
        raise ValueError("executor profile invocation is required")
    if invocation.get("bounded_semantic_requests_only") is not True:
        raise ValueError("bounded semantic invocation is required")
    for key in ("caller_supplied_executable", "caller_supplied_argv", "caller_supplied_env"):
        if invocation.get(key) is not False:
            raise ValueError(f"{key} must be false")

    receipt = profile.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("required") is not True or receipt.get("secrets_allowed") is not False:
        raise ValueError("governed secret-free receipt is required")

    smoke = profile.get("smoke")
    if not isinstance(smoke, dict) or smoke.get("required") is not True:
        raise ValueError("provider smoke acceptance is required")

    adoption = profile.get("adoption")
    if not isinstance(adoption, dict):
        raise ValueError("executor profile adoption is required")
    if adoption.get("reinstall_by_default") is not False or adoption.get("preserve_existing_identity") is not True:
        raise ValueError("executor adoption must preserve existing identity and avoid default reinstall")

    implementation = profile.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("executor profile implementation is required")
    adapter_module = implementation.get("adapter_module")
    if adapter_module is not None and (not isinstance(adapter_module, str) or not adapter_module.strip()):
        raise ValueError("adapter_module must be null or non-empty string")

    return profile


def load_provider_profiles(profile_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(profile_root) if profile_root is not None else _default_profile_root()
    if not root.exists():
        return []
    profiles: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name.startswith("_") or path.name.endswith(".schema.json"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        profile = validate_provider_profile(raw)
        profile = dict(profile)
        profile["_profile_path"] = str(path)
        profiles.append(profile)
    ids = [str(p["executor_id"]) for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate executor_id in provider profiles")
    return profiles


def _load_symbol(spec: str) -> Any:
    module_name, sep, symbol = spec.partition(":")
    module_name = module_name.strip()
    symbol = symbol.strip()
    if not module_name:
        raise ValueError("adapter module name is required")
    module = importlib.import_module(module_name)
    if sep:
        target = getattr(module, symbol)
        return target() if callable(target) else target
    if hasattr(module, "create_provider"):
        return module.create_provider()
    if hasattr(module, "PROVIDER"):
        return module.PROVIDER
    raise ValueError(f"executor provider module must expose create_provider() or PROVIDER: {module_name}")


def load_provider(profile: dict[str, Any]) -> ExecutorProvider | None:
    implementation = profile.get("implementation") or {}
    spec = implementation.get("adapter_module")
    if spec is None:
        return None
    provider = _load_symbol(str(spec))
    expected = {
        "executor_id": str(profile["executor_id"]),
        "provider_id": str(profile["provider_id"]),
        "executor_class": str(profile["executor_class"]),
    }
    for key, value in expected.items():
        if str(getattr(provider, key, "") or "") != value:
            raise ValueError(f"executor provider {key} mismatch for {expected['executor_id']}")
    for method in ("discover", "capabilities", "health", "invoke", "cancel", "receipt"):
        if not callable(getattr(provider, method, None)):
            raise ValueError(f"executor provider missing {method}(): {expected['executor_id']}")
    declared = sorted({str(x).strip() for x in profile.get("capabilities") or [] if str(x).strip()})
    implemented = sorted({str(x).strip() for x in provider.capabilities() if str(x).strip()})
    if declared != implemented:
        raise ValueError(f"executor provider capability mismatch for {expected['executor_id']}")
    return provider
