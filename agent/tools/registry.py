import json
from dataclasses import dataclass


@dataclass
class ToolSpec:
    name: str
    description: str
    risk_level: str  # low|medium|high
    requires_confirmation: bool


class ToolError(RuntimeError):
    pass


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[ToolSpec, callable]] = {}

    def register(self, spec: ToolSpec, fn):
        self._tools[spec.name] = (spec, fn)

    def spec(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        return self._tools[name][0]

    def list_specs(self) -> list[ToolSpec]:
        return [v[0] for v in self._tools.values()]

    def execute(self, name: str, args: dict, *, context: dict | None = None) -> dict:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        spec, fn = self._tools[name]
        if not isinstance(args, dict):
            raise ToolError("Tool args must be a dict")

        # Ensure JSON-serializable inputs (avoid accidental passing of objects)
        json.dumps(args)

        res = fn(args=args, context=context or {})
        # Ensure JSON-serializable outputs
        json.dumps(res)
        return res
