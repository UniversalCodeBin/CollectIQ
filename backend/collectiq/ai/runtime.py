"""The process-wide gateway, built from settings. Tests replace it with `use_gateway`."""

from django.conf import settings

from .agents import AgentRunner
from .gateway import AIConfig, Gateway, build_provider

_gateway: Gateway | None = None


def get_gateway() -> Gateway:
    global _gateway
    if _gateway is None:
        provider = build_provider(settings.AI_PROVIDER, production=_is_production())
        _gateway = Gateway(provider, AIConfig(kill_switch=bool(getattr(settings, "AI_KILL_SWITCH", False))))
    return _gateway


def get_agent_runner() -> AgentRunner:
    """Agents share the gateway's provider and kill switch, so one setting governs every AI call."""
    gateway = get_gateway()
    return AgentRunner(gateway.provider, gateway.config)


def use_gateway(gateway: Gateway | None) -> None:
    global _gateway
    _gateway = gateway


def _is_production() -> bool:
    return settings.SETTINGS_MODULE.endswith(".production")
