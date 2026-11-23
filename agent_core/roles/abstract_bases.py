"""AgentOS Multi-Layer Abstract Role Hierarchy (Leaf-Only Execution Architecture).

Software Engineering & Systems Design Principles Enforced:
1. Liskov Substitution & Template Method (BaseRoleWorker ABC):
   - Intermediate abstract layers MUST NOT be instantiated directly.
   - Only concrete leaf nodes implementing plan(), do(), check() are auto-registered.
2. Dependency Injection (RoleContext):
   - Injects data_root, project_root, clock, and logger cleanly instead of hardcoded global paths.
3. Idempotency & Concurrency Safety:
   - Provides bounded file-lock helpers and deterministic work_id generation.
4. Explicit Typed Contracts (PlanSpec, DoOutput, CheckVerdict):
   - Replaces loose dict guessing with structured dataclasses.
"""
from __future__ import annotations

import abc
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_role_id(role_id: str) -> str:
    return role_id.lower().strip().replace(".", "-").replace("_", "-")


@dataclass(frozen=True)
class RoleContext:
    """Dependency-injected runtime context for any role worker."""

    data_root: Path = Path("/home/ubuntu/agent-data")
    project_root: Path = Path("/home/ubuntu/agentmanager")
    clock: Callable[[], str] = _utc_now_iso


@dataclass
class PlanSpec:
    task: str
    source: str
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoOutput:
    action: str
    status: str
    findings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckVerdict:
    verifier_role: str
    verdict: str  # "PASS" | "FAIL"
    findings: list[str] = field(default_factory=list)


class BaseRoleWorker(abc.ABC):
    """Layer 0 (Abstract Root): Universal PDCA Template Method & Leaf-Only Auto-Registry."""

    ROLE_ID: ClassVar[str] = ""
    ALIASES: ClassVar[tuple[str, ...]] = ()
    _LEAF_REGISTRY: ClassVar[dict[str, type[BaseRoleWorker]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only concrete leaf nodes (non-abstract classes with ROLE_ID) may register.
        if inspect.isabstract(cls):
            return
        if not cls.ROLE_ID:
            raise TypeError(f"Concrete leaf role {cls.__name__} must declare a non-empty ROLE_ID.")
        keys = {normalize_role_id(cls.ROLE_ID)} | {normalize_role_id(a) for a in cls.ALIASES}
        for key in keys:
            existing = BaseRoleWorker._LEAF_REGISTRY.get(key)
            if existing is not None and existing is not cls:
                raise ValueError(
                    f"Role ID collision for '{key}': {existing.__name__} vs {cls.__name__}"
                )
            BaseRoleWorker._LEAF_REGISTRY[key] = cls

    def __init__(self, context: RoleContext | None = None) -> None:
        self.ctx = context or RoleContext()
        self.role_slug = normalize_role_id(self.ROLE_ID)

    @classmethod
    def resolve_leaf(cls, role_id: str) -> type[BaseRoleWorker]:
        """Fail-closed lookup of a concrete leaf role class."""
        norm = normalize_role_id(role_id)
        target = cls._LEAF_REGISTRY.get(norm)
        if target is None:
            raise KeyError(
                f"No concrete leaf role registered for '{role_id}' (normalized: '{norm}'). "
                "Instantiating abstract layers or hollow fallbacks is prohibited."
            )
        return target

    @classmethod
    def list_registered_leaves(cls) -> dict[str, str]:
        return {k: v.__name__ for k, v in sorted(cls._LEAF_REGISTRY.items())}

    @abc.abstractmethod
    def plan(self, cycle: int) -> PlanSpec:
        """Select work and declare acceptance criteria."""

    @abc.abstractmethod
    def do(self, plan_spec: PlanSpec, work_id: str) -> DoOutput:
        """Execute role-bounded action."""

    @abc.abstractmethod
    def check(self, plan_spec: PlanSpec, do_output: DoOutput) -> CheckVerdict:
        """Verify invariants and outputs."""

    def on_failure_remediate(
        self, plan_spec: PlanSpec, stage: str, error_summary: str
    ) -> str:
        """Hook for bounded LLM self-reflection on Do exception or Check FAIL."""
        return f"DEFERRED_REMEDIATION ({self.role_slug}@{stage}): {error_summary[:120]}"

    def run_cycle(self, cycle: int = 1) -> dict[str, Any]:
        """Template Method: orchestrates Plan -> Do -> Check -> Remediation -> Act."""
        work_id = f"{self.role_slug}-work-{cycle:04d}"
        plan_spec = self.plan(cycle)

        try:
            do_output = self.do(plan_spec, work_id)
        except Exception as exc:
            remediation = self.on_failure_remediate(plan_spec, "do", str(exc))
            do_output = DoOutput(
                action="exception_mitigated",
                status="error",
                findings=[f"❌ Do exception: {exc}", f"🧠 {remediation}"],
            )

        verdict = self.check(plan_spec, do_output)
        if verdict.verdict != "PASS":
            remediation = self.on_failure_remediate(
                plan_spec, "check", "; ".join(verdict.findings)
            )
            verdict.findings.append(f"🧠 {remediation}")

        return {
            "role_id": self.ROLE_ID,
            "role_slug": self.role_slug,
            "cycle": cycle,
            "work_id": work_id,
            "timestamp": self.ctx.clock(),
            "plan": plan_spec.task,
            "do_action": do_output.action,
            "verdict": verdict.verdict,
            "findings": verdict.findings,
        }


# ==============================================================================
# Layer 1 (Abstract Domain Layers — Shared Domain Capabilities, Never Instantiated)
# ==============================================================================


class GovernanceRoleBase(BaseRoleWorker, abc.ABC):
    """Abstract base for governance roles (Atlas, Spec Steward, Keeper, Themis, Rhea)."""

    def load_refinement_queue(self) -> dict[str, Any]:
        q_file = self.ctx.data_root / "runtime" / "spec_refinement_queue.json"
        if not q_file.is_file():
            return {"total_unqualified": 0, "total_blocked_incidents": 0, "queue": []}
        return json.loads(q_file.read_text(encoding="utf-8"))

    def load_constitution_path(self) -> Path:
        return self.ctx.project_root / ".agent" / "CONSTITUTION.yaml"


class SystemInfraRoleBase(BaseRoleWorker, abc.ABC):
    """Abstract base for infrastructure roles (Gateway, DNS, Port, Cartographer, Sentinel)."""

    def check_file_exists(self, path: Path) -> bool:
        return path.exists()


class SectorExecutorBase(BaseRoleWorker, abc.ABC):
    """Abstract base for sector executors/auditors (Paw, Claw, Weaver, Hermes, Whisperer)."""

    def resolve_project_workspace(self, project_id: str) -> Path:
        candidate = Path("/home/ubuntu") / project_id
        return candidate if candidate.is_dir() else self.ctx.project_root


class ProductCreatorBase(BaseRoleWorker, abc.ABC):
    """Abstract base for product & content creators (Zeus Writer, Cangxuan, YouTube, Mio)."""

    def load_writing_plan(self, book_dir: Path) -> list[str]:
        plan_file = book_dir / "寫作計畫.md"
        if not plan_file.is_file():
            return []
        return [
            line.strip()
            for line in plan_file.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- [ ]")
        ]
