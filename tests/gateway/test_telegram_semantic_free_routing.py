"""Telegram implicit routes participate in task-aware configured model selection."""

from types import SimpleNamespace
from unittest.mock import patch

import gateway.run as gateway_run
import gateway.run_turn as gateway_run_turn
from agent import semantic_model_router as router
from gateway.config import Platform
from gateway.session import SessionSource


def _runner():
    runner = object.__new__(gateway_run.GatewayRunner)
    runner.config = None
    runner._service_tier = None
    runner._rehydrate_session_model_override = lambda _key: None
    runner._peek_session_state = lambda _key: None
    runner._session_state = lambda _key: SimpleNamespace(conversation=SimpleNamespace(last_resolved_model=""))
    return runner


def _config():
    return {
        "model": {"default": "general-model", "provider": "implicit-custom",
                  "base_url": "https://custom.invalid/v1"},
        "fallback_providers": [
            {"provider": "implicit-custom", "model": "general-model", "base_url": "https://custom.invalid/v1"},
            {"provider": "reasoning-relay", "model": "reasoning-pro"},
            {"provider": "fast-relay", "model": "fast-mini"},
        ],
        "semantic_routing": {"enabled": True},
    }


def _caps(route, _config):
    model = route["model"]
    return {
        "supports_tools": True,
        "supports_reasoning": model == "reasoning-pro",
        "context_window": 200_000,
        "model_family": "",
    }


def _telegram_runtime(runner, config):
    source = SessionSource(platform=Platform.TELEGRAM, chat_id="12345")
    with patch.object(gateway_run, "_resolve_gateway_model", return_value=config["model"]["default"]), \
         patch.object(gateway_run, "_resolve_runtime_agent_kwargs", return_value={
             "provider": "custom", "requested_provider": "implicit-custom",
             "base_url": "https://custom.invalid/v1", "api_mode": "chat_completions",
         }):
        return runner._resolve_session_agent_runtime(
            source=source, session_key="agent:main:telegram:dm:12345", user_config=config,
        )


def test_telegram_implicit_custom_route_can_be_semantically_replaced(monkeypatch):
    monkeypatch.setattr(router, "_capabilities", _caps)
    runner, config = _runner(), _config()
    model, runtime = _telegram_runtime(runner, config)
    with patch.object(gateway_run_turn, "_resolve_semantic_runtime", return_value={
        "provider": "fast-relay", "requested_provider": "fast-relay",
        "base_url": "https://fast.invalid/v1", "api_mode": "chat_completions",
        "request_overrides": {}, "capabilities": {},
    }) as resolve:
        route = runner._resolve_turn_agent_config("الو", model, runtime, routing_config=config)

    assert resolve.call_args.args[0]["provider"] == "fast-relay"
    assert resolve.call_args.args[0]["model"] == "fast-mini"
    assert route["model"] == "fast-mini"
    assert route["runtime"]["provider"] == "fast-relay"
    assert route["semantic_pool"] is True
    assert any(entry["model"] == "reasoning-pro" for entry in route["fallback_model"])


def test_telegram_reselects_after_route_rate_limit(monkeypatch):
    monkeypatch.setattr(router, "_capabilities", _caps)
    runner, config = _runner(), _config()
    model, runtime = _telegram_runtime(runner, config)
    with patch.object(gateway_run_turn, "_resolve_semantic_runtime", return_value={
        "provider": "fast-relay", "requested_provider": "fast-relay",
        "base_url": "https://fast.invalid/v1", "api_mode": "chat_completions",
        "request_overrides": {}, "capabilities": {},
    }):
        route = runner._resolve_turn_agent_config("الو", model, runtime, routing_config=config)
    router.mark_route_unavailable(route["primary_route"], "rate_limit", 60)
    result = router.select("الو", config, primary_route={
        "provider": "implicit-custom", "model": "small-chat", "base_url": "https://custom.invalid/v1",
    })
    assert result.model != "fast-mini"


def test_explicit_session_or_channel_route_remains_authoritative():
    runner, config = _runner(), _config()
    model, runtime = _telegram_runtime(runner, config)
    with patch.object(gateway_run, "_resolve_runtime_agent_kwargs_for_provider") as resolve:
        route = runner._resolve_turn_agent_config(
            "الو", "explicit-model", {**runtime, "provider": "bluesminds"},
            allow_semantic_routing=False, routing_config=config,
        )
    resolve.assert_not_called()
    assert route["model"] == "explicit-model"
    assert route["runtime"]["provider"] == "bluesminds"
    assert "fallback_model" not in route


def test_no_available_telegram_route_returns_pool_exhausted(monkeypatch):
    monkeypatch.setattr(router, "_capabilities", _caps)
    runner, config = _runner(), _config()
    routes = router._configured_routes(config, {
        "provider": "implicit-custom", "model": "general-model", "base_url": "https://custom.invalid/v1",
    })
    for route in routes:
        router.mark_route_unavailable(route, "rate_limit", 180)
    model, runtime = _telegram_runtime(runner, config)
    route = runner._resolve_turn_agent_config("الو", model, runtime, routing_config=config)
    assert route["pool_exhausted"] is True
