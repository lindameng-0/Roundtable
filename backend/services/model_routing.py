"""Per-role model routing and transparent token-cost estimates."""
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import config as _cfg


# USD per million tokens. Unknown models intentionally produce no dollar
# estimate instead of silently using the wrong price. Values can be overridden
# through MODEL_PRICING_USD_JSON in a later deployment if needed.
MODEL_PRICING_USD: Dict[str, Dict[str, float]] = {
    "gemini:gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini:gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini:gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "anthropic:claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "anthropic:claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "openai:gpt-5.6-luna": {"input": 0.20, "output": 1.20},
    "openai:gpt-5.6-terra": {"input": 2.00, "output": 12.00},
}


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class UsageRecord:
    provider: str
    model: str
    role: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def parse_route(value: str, default: str = "gemini:gemini-2.5-flash") -> ModelRoute:
    raw = (value or default).strip()
    if ":" not in raw:
        raise ValueError(f"Invalid model route '{raw}'. Expected provider:model")
    provider, model = raw.split(":", 1)
    if provider not in {"gemini", "anthropic", "openai"} or not model.strip():
        raise ValueError(f"Unsupported model route '{raw}'")
    return ModelRoute(provider.strip(), model.strip())


def reader_routes() -> List[ModelRoute]:
    values = [item.strip() for item in _cfg.READER_MODEL_POOL.split(",") if item.strip()]
    return [parse_route(value) for value in values] or [parse_route("")]


def route_for_reader(reader: Dict) -> ModelRoute:
    explicit = reader.get("model_route")
    if explicit:
        return parse_route(explicit)
    routes = reader_routes()
    try:
        index = int(reader.get("avatar_index", 0))
    except (TypeError, ValueError):
        index = 0
    return routes[index % len(routes)]


def fallback_routes_for_reader(reader: Dict) -> List[ModelRoute]:
    """Primary route followed by the other configured providers once each."""
    primary = route_for_reader(reader)
    configured = reader_routes()
    ordered = [primary, *configured]
    unique: List[ModelRoute] = []
    seen = set()
    for route in ordered:
        if route.key not in seen:
            unique.append(route)
            seen.add(route.key)
    return unique


def route_for_role(role: str, reader: Optional[Dict] = None) -> ModelRoute:
    if role == "reader":
        return route_for_reader(reader or {})
    if role == "memory":
        return parse_route(_cfg.MEMORY_MODEL_ROUTE)
    if role == "editor":
        return parse_route(_cfg.EDITOR_MODEL_ROUTE)
    if role == "copyedit":
        return parse_route(_cfg.COPYEDIT_MODEL_ROUTE)
    raise ValueError(f"Unknown model role '{role}'")


def usage_record(route: ModelRoute, role: str, input_tokens: int, output_tokens: int) -> UsageRecord:
    prices = MODEL_PRICING_USD.get(route.key)
    cost = None
    if prices:
        cost = round(
            (max(0, input_tokens) * prices["input"] + max(0, output_tokens) * prices["output"]) / 1_000_000,
            6,
        )
    return UsageRecord(route.provider, route.model, role, input_tokens, output_tokens, cost)
