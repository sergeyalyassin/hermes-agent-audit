from agent import semantic_model_router as router
from agent.turn_api_error import _safe_api_error_message


def _caps(model, **overrides):
    values = {
        "supports_tools": True, "supports_reasoning": None,
        "context_window": 200_000, "model_family": "",
    }
    values.update(overrides)
    return values


def _patch_caps(monkeypatch, by_model):
    monkeypatch.setattr(router, "_capabilities", lambda route, _config: by_model[route["model"]])


def _config(routes):
    return {"model": {"provider": routes[0][0], "default": routes[0][1]},
            "fallback_providers": [{"provider": p, "model": m} for p, m in routes[1:]]}


def test_task_classification_covers_required_capability_classes():
    assert router.classify("Fix the Python function") == "coding"
    assert router.classify("Analyze the root cause and compare the trade-offs") == "reasoning"
    assert router.classify("Hello") == "light"
    assert router.classify("مرحبا") == "light"
    assert router.classify("Explain this topic") == "reasoning"
    assert router.classify("Analyze this entire document: " + "x" * 12_000) == "long_context"


def test_best_model_is_selected_for_coding(monkeypatch):
    _patch_caps(monkeypatch, {
        "small-general": _caps("small-general"),
        "reasoning-70b": _caps("reasoning-70b", supports_reasoning=True),
        "best-coder-70b": _caps("best-coder-70b", supports_reasoning=True),
    })
    result = router.select("Debug this Python code", _config([
        ("relay-a", "small-general"), ("relay-b", "reasoning-70b"), ("relay-c", "best-coder-70b"),
    ]))
    assert (result.provider, result.model) == ("relay-c", "best-coder-70b")


def test_best_reasoning_model_is_selected(monkeypatch):
    _patch_caps(monkeypatch, {
        "general-70b": _caps("general-70b"),
        "reasoning-pro-70b": _caps("reasoning-pro-70b", supports_reasoning=True),
    })
    result = router.select("Analyze the architecture and explain why", _config([
        ("relay-a", "general-70b"), ("relay-b", "reasoning-pro-70b"),
    ]))
    assert result.model == "reasoning-pro-70b"


def test_light_model_is_selected_for_simple_chat(monkeypatch):
    _patch_caps(monkeypatch, {
        "frontier-pro": _caps("frontier-pro", supports_reasoning=True),
        "fast-mini": _caps("fast-mini"),
    })
    result = router.select("Hello", _config([("relay-a", "frontier-pro"), ("relay-b", "fast-mini")]))
    assert result.model == "fast-mini"


def test_light_task_does_not_rank_large_reasoning_nano_above_flash(monkeypatch):
    _patch_caps(monkeypatch, {
        "gemini-2.5-flash": _caps("gemini-2.5-flash"),
        "nemotron-3-nano-omni-30b-reasoning": _caps(
            "nemotron-3-nano-omni-30b-reasoning", supports_reasoning=True,
        ),
    })
    result = router.select("مرحبا", _config([
        ("bluesminds", "nemotron-3-nano-omni-30b-reasoning"),
        ("gemini", "gemini-2.5-flash"),
    ]))
    assert result.name == "light"
    assert (result.provider, result.model) == ("gemini", "gemini-2.5-flash")


def test_provider_is_not_hard_coded_to_task(monkeypatch):
    _patch_caps(monkeypatch, {
        "small-general": _caps("small-general"),
        "acme-coder": _caps("acme-coder", supports_reasoning=True),
    })
    result = router.select("Write a Go program", _config([
        ("openrouter", "small-general"), ("custom-coder-relay", "acme-coder"),
    ]))
    assert result.provider == "custom-coder-relay"


def test_same_model_on_two_providers_is_two_capacity_routes(monkeypatch):
    _patch_caps(monkeypatch, {"reasoning-pro": _caps("reasoning-pro", supports_reasoning=True)})
    config = _config([("relay-a", "reasoning-pro"), ("relay-b", "reasoning-pro")])
    selected = router.select("Analyze this carefully", config)
    assert selected is not None
    assert len(selected.fallback_routes) == 1
    assert selected.fallback_routes[0]["provider"] != selected.provider


def test_same_provider_model_with_distinct_configured_credentials_is_distinct_route():
    one = {"provider": "shared-relay", "model": "same-model", "key_env": "FIRST_RELAY_KEY"}
    two = {"provider": "shared-relay", "model": "same-model", "key_env": "SECOND_RELAY_KEY"}
    assert router._route_key(one) != router._route_key(two)


def test_route_429_is_quarantined_then_next_suitable_route_is_selected(monkeypatch):
    _patch_caps(monkeypatch, {
        "coder-best": _caps("coder-best", supports_reasoning=True),
        "coder-next": _caps("coder-next", supports_reasoning=True),
    })
    config = _config([("relay-a", "coder-best"), ("relay-b", "coder-next")])
    first = router.select("Fix this code", config)
    router.mark_route_unavailable(first.primary_route, "rate_limit", 90)
    second = router.select("Fix this code", config)
    assert second.model == "coder-next"
    assert second.provider == "relay-b"


def test_daily_quota_quarantines_only_the_failed_route(monkeypatch):
    _patch_caps(monkeypatch, {
        "model-a": _caps("model-a"), "model-b": _caps("model-b"),
    })
    config = _config([("provider-a", "model-a"), ("provider-b", "model-b")])
    first = router.select("Explain the result", config)
    router.mark_route_unavailable(first.primary_route, "billing", 120)
    assert router.select("Explain the result", config).model == "model-b"


def test_auth_failure_quarantines_route_and_does_not_print_credentials(monkeypatch, caplog):
    route = {"provider": "relay-auth", "model": "auth-model", "key_env": "RELAY_AUTH_KEY"}
    router.mark_route_unavailable(route, "auth")
    assert not router.route_available(route)
    assert "sensitive-test-value" not in repr(router.SemanticRoute("coding", "relay-auth", "auth-model", (route,)))
    assert "RELAY_AUTH_KEY" not in caplog.text


def test_api_error_hook_message_redacts_current_route_credential():
    credential = "test-only-credential-sentinel"
    agent = type("Agent", (), {
        "api_key": credential, "_fallback_chain": [], "_availability_route_entry": None,
        "_primary_runtime": {}, "_clean_error_message": staticmethod(lambda message: message),
    })()
    cleaned = _safe_api_error_message(agent, RuntimeError(f"401 rejected {credential}"))
    assert credential not in cleaned
    assert "[REDACTED]" in cleaned


def test_cooldown_prevents_hammering_and_route_recovers_automatically(monkeypatch):
    now = 500.0
    monkeypatch.setattr(router.time, "monotonic", lambda: now)
    route = {"provider": "relay-cooldown", "model": "cooldown-model"}
    router.mark_route_unavailable(route, "rate_limit", 10)
    assert not router.route_available(route)
    assert router.route_available(route, now=511.0)


def test_model_capability_order_has_suitable_degradation(monkeypatch):
    _patch_caps(monkeypatch, {
        "coder-ideal": _caps("coder-ideal", supports_reasoning=True),
        "reasoning-next": _caps("reasoning-next", supports_reasoning=True),
        "general-last": _caps("general-last"),
    })
    config = _config([("p1", "coder-ideal"), ("p2", "reasoning-next"), ("p3", "general-last")])
    ideal = router.select("Debug the function", config)
    router.mark_route_unavailable(ideal.primary_route, "overloaded")
    assert router.select("Debug the function", config).model == "reasoning-next"


def test_long_context_prefers_largest_suitable_context(monkeypatch):
    _patch_caps(monkeypatch, {
        "ctx-200k": _caps("ctx-200k", context_window=200_000, supports_reasoning=True),
        "ctx-1m": _caps("ctx-1m", context_window=1_000_000, supports_reasoning=True),
    })
    result = router.select("Analyze this entire document: " + "x" * 12_000,
                           _config([("p1", "ctx-200k"), ("p2", "ctx-1m")]))
    assert result.model == "ctx-1m"


def test_anti_starvation_spreads_equivalent_requests(monkeypatch):
    _patch_caps(monkeypatch, {"fast-a": _caps("fast-a"), "fast-b": _caps("fast-b")})
    config = _config([("p1", "fast-a"), ("p2", "fast-b")])
    first = router.select("Hello", config)
    second = router.select("Hello", config)
    assert second.model != first.model


def test_only_configured_routes_are_eligible_and_paid_fallback_is_not_added():
    route = {"provider": "configured-custom", "model": "configured-model"}
    result = router.select("General conversation", {}, primary_route=route)
    assert (result.provider, result.model) == ("configured-custom", "configured-model")
    assert result.fallback_routes == ()


def test_all_configured_routes_can_be_quarantined():
    config = _config([("p1", "exhaust-a"), ("p2", "exhaust-b")])
    for route in router._configured_routes(config, None):
        router.mark_route_unavailable(route, "rate_limit", 300)
    assert router.select("Explain this", config) is None


def test_router_hot_path_caches_route_capabilities_and_exposes_phase_timings(monkeypatch):
    from types import SimpleNamespace

    provider_calls = []
    route = {"provider": "timing-cache-provider", "model": "timing-cache-model"}
    config = {"model": route}
    router._CAPABILITY_CACHE.clear()
    router._ROUTE_POOL_CACHE.clear()
    def read_capabilities(*_args, **kwargs):
        assert kwargs["allow_network"] is False
        provider_calls.append(1)
        return SimpleNamespace(
            supports_tools=True, supports_reasoning=False, context_window=32_000, model_family=""
        )

    monkeypatch.setattr("agent.models_dev.get_model_capabilities", read_capabilities)

    first = router.select("مرحبا", config)
    second = router.select("مرحبا", config)

    assert first is not None and second is not None
    assert first.name == second.name == "light"
    assert provider_calls == [1]
    assert second.timings_ms["classification_ms"] >= 0
    assert second.timings_ms["route_pool_ms"] >= 0
    assert second.timings_ms["route_health_ms"] >= 0
    assert second.timings_ms["ranking_ms"] >= 0
    assert second.timings_ms["pool_cache_hit"] == 1
