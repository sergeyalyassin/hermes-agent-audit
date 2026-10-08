"""Task-aware ranking of configured model routes for gateway turns.

Only routes present in the user's model, fallback, or named-provider configuration are
considered. Provider credentials remain in the route dictionaries in memory and are never
included in reprs or routing diagnostics.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping, Optional

_ROUTE_LOCK = threading.RLock()
_ROUTE_HEALTH: dict[tuple[str, ...], dict[str, Any]] = {}
_CAPABILITY_CACHE: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
_ROUTE_POOL_CACHE: OrderedDict[str, tuple[dict[str, Any], ...]] = OrderedDict()
_METADATA_CACHE_LIMIT = 2048

_CODING = re.compile(
    r"\b(?:code|coding|program|programming|debug|debugging|bug|exception|stack trace|"
    r"python|javascript|typescript|java|rust|go|sql|bash|shell|yaml|json|api|sdk|repository|"
    r"repo|github|git|commit|branch|pull request|docker|kubernetes|function|class|method|"
    r"module|import|package|dependency|regex|terminal|command|script|compile|compiler|test|"
    r"pytest|unittest|refactor|patch|diff)\b|Traceback \(most recent call last\)|"
    r"(?:^|\s)(?:/workspaces/|~/|\.\.?/)[^\s]+", re.I)
_REASONING = re.compile(
    r"\b(?:analy[sz]e|analysis|architecture|architectural|investigate|investigation|"
    r"root cause|deep dive|deeply|complex|complicated|compare|comparison|trade[- ]?off|"
    r"design|strategy|strategic|why|explain|review|audit|diagnose|diagnosis|reasoning|"
    r"logic|evaluate|evaluation|plan|roadmap|research|comprehensive|thorough|critique|"
    r"optimi[sz]e|security|threat model|performance|bottleneck|long context|large document)\b|"
    r"حلل|تحليل|راجع|مراجعة|سبب|جذر المشكلة|لماذا|قارن|مقارنة|معمارية|تصميم|"
    r"استقص|تحقيق|بالتفصيل|شامل|استراتيجية|خطة|تشخيص|منطق|أداء|أمن", re.I)
_LIGHT = re.compile(
    r"^(?:hi|hello|hey|thanks|thank you|ok|okay|yes|no|good morning|good evening|"
    r"what(?:'s| is) your name|who are you|translate|translation|classify|classification|"
    r"مرحبا|أهلا|اهلا|شكرا|نعم|لا)\b", re.I)
_TRANSIENT_REASONS = frozenset({
    "auth", "auth_permanent", "billing", "rate_limit", "upstream_rate_limit",
    "overloaded", "server_error", "timeout", "upstream_blocked", "model_not_found",
    "model_entitlement",
})


@dataclass(frozen=True)
class SemanticRoute:
    name: str
    provider: str
    model: str
    fallback_routes: tuple[dict[str, Any], ...] = field(default=(), repr=False)
    primary_route: dict[str, Any] = field(default_factory=dict, repr=False)
    timings_ms: dict[str, float] = field(default_factory=dict, repr=False)


def classify(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return "general"
    if len(text) >= 12_000 or re.search(r"\b(?:entire|whole|full) (?:codebase|document|transcript)\b", text, re.I):
        return "long_context"
    if _CODING.search(text):
        return "coding"
    if _REASONING.search(text):
        return "reasoning"
    if len(text) <= 180 and _LIGHT.search(text):
        return "light"
    if len(text) <= 100 and text.count("?") <= 1 and len(text.split()) <= 18:
        return "light"
    return "general"


def enabled(config: Optional[Mapping[str, Any]]) -> bool:
    try:
        from agent.secret_scope import get_secret_str
        flag = get_secret_str("HERMES_SEMANTIC_ROUTING", "").strip().lower()
    except Exception:
        flag = ""
    if flag in {"0", "false", "off", "no"}:
        return False
    section = config.get("semantic_routing") if isinstance(config, Mapping) else None
    return not (isinstance(section, Mapping) and section.get("enabled") is False)


def _route_key(route: Mapping[str, Any]) -> tuple[str, ...]:
    api_key = route.get("api_key")
    key_ref = str(route.get("key_env") or route.get("api_key_env") or "")
    if not key_ref and isinstance(api_key, str) and api_key:
        key_ref = hashlib.sha256(api_key.encode("utf-8", "replace")).hexdigest()
    key_cmd = route.get("key_cmd")
    if key_cmd:
        key_ref = hashlib.sha256(str(key_cmd).encode("utf-8", "replace")).hexdigest()
    return (
        str(route.get("provider") or "").strip().lower(),
        str(route.get("model") or "").strip().lower(),
        str(route.get("base_url") or "").strip().rstrip("/").lower(),
        key_ref,
    )


def _pool_fingerprint(config: Optional[Mapping[str, Any]], primary_route: Optional[Mapping[str, Any]]) -> str:
    """Fingerprint only route-bearing config sections; digest inline keys without retaining/logging them."""
    if not isinstance(config, Mapping):
        config = {}
    payload = {
        name: config.get(name) for name in (
            "model", "fallback_providers", "fallback_chain", "semantic_routing", "providers", "custom_providers",
        )
    }
    payload["primary_route"] = dict(primary_route or {})
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


@lru_cache(maxsize=256)
def _cached_provider_base_url(provider: str) -> str:
    try:
        from hermes_cli.providers import get_provider
        definition = get_provider(provider, allow_network=False)
        return str(definition.base_url or "") if definition else ""
    except Exception:
        return ""


def route_available(route: Mapping[str, Any], now: Optional[float] = None) -> bool:
    key = _route_key(route)
    with _ROUTE_LOCK:
        state = _ROUTE_HEALTH.get(key)
        if not state:
            return True
        if state["cooldown_until"] <= (time.monotonic() if now is None else now):
            state["available"] = True
            state["cooldown_until"] = 0.0
            return True
        return False


def mark_route_unavailable(route: Mapping[str, Any], reason: Any, retry_after: Any = None) -> None:
    reason_name = getattr(reason, "value", reason)
    reason_name = str(reason_name or "temporary_failure").lower()
    if reason_name not in _TRANSIENT_REASONS:
        return
    try:
        seconds = max(0.0, float(retry_after)) if retry_after is not None else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    key = _route_key(route)
    with _ROUTE_LOCK:
        previous = _ROUTE_HEALTH.get(key, {})
        failures = int(previous.get("failures", 0)) + 1
        if seconds <= 0:
            base = 900.0 if reason_name in {"auth", "auth_permanent"} else 60.0
            seconds = min(base * (2 ** min(failures - 1, 6)), 3600.0)
        _ROUTE_HEALTH[key] = {
            "available": False,
            "cooldown_until": time.monotonic() + seconds,
            "last_failure": time.time(),
            "failure_type": reason_name,
            "retry_after": seconds,
            "failures": failures,
            "last_used": previous.get("last_used", 0.0),
        }


def mark_route_success(route: Mapping[str, Any]) -> None:
    key = _route_key(route)
    with _ROUTE_LOCK:
        previous = _ROUTE_HEALTH.get(key, {})
        _ROUTE_HEALTH[key] = {
            "available": True, "cooldown_until": 0.0, "last_failure": None,
            "failure_type": None, "retry_after": None, "failures": 0,
            "last_used": time.monotonic(),
            "successes": int(previous.get("successes", 0)) + 1,
        }


def _configured_routes(config: Optional[Mapping[str, Any]], primary_route: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    routes, _, _, _ = _configured_routes_timed(config, primary_route)
    return routes


def _configured_routes_timed(
    config: Optional[Mapping[str, Any]], primary_route: Optional[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], float, float, bool]:
    started = time.perf_counter()
    fingerprint = _pool_fingerprint(config, primary_route)
    with _ROUTE_LOCK:
        cached = _ROUTE_POOL_CACHE.get(fingerprint)
        if cached is not None:
            _ROUTE_POOL_CACHE.move_to_end(fingerprint)
            raw_routes = cached
        else:
            raw_routes = None
    if raw_routes is None:
        raw_routes = tuple(_build_configured_routes(config, primary_route))
        with _ROUTE_LOCK:
            _ROUTE_POOL_CACHE[fingerprint] = raw_routes
            _ROUTE_POOL_CACHE.move_to_end(fingerprint)
            while len(_ROUTE_POOL_CACHE) > 32:
                _ROUTE_POOL_CACHE.popitem(last=False)
    pool_ms = (time.perf_counter() - started) * 1000
    # Cooldowns are consulted on every request; route/config/provider discovery is cached.
    health_started = time.perf_counter()
    available = [route for route in raw_routes if route_available(route)]
    health_ms = (time.perf_counter() - health_started) * 1000
    return available, pool_ms, health_ms, cached is not None


def _build_configured_routes(config: Optional[Mapping[str, Any]], primary_route: Optional[Mapping[str, Any]]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    provider_settings = config.get("providers") if isinstance(config, Mapping) else None

    def add(entry: Any) -> None:
        if not isinstance(entry, Mapping):
            return
        provider = str(entry.get("provider") or "").strip()
        model = str(entry.get("model") or "").strip()
        if not provider or not model:
            return
        route = dict(entry)
        settings = provider_settings.get(provider) if isinstance(provider_settings, Mapping) else None
        if isinstance(settings, Mapping):
            for field_name in ("base_url", "api", "url", "api_key", "key_env", "api_key_env", "key_cmd", "api_mode", "transport"):
                if not route.get(field_name) and settings.get(field_name):
                    route[field_name] = settings[field_name]
        if not route.get("base_url"):
            # Use the same canonical endpoint in route-health identity before and
            # after runtime resolution, so cooldowns persist across turns.
            try:
                route["base_url"] = _cached_provider_base_url(provider)
            except Exception:
                pass
        route["provider"] = provider
        route["model"] = model
        key = _route_key(route)
        if key not in seen:
            seen.add(key)
            routes.append(route)

    add(primary_route)
    if isinstance(config, Mapping):
        model = config.get("model")
        if isinstance(model, Mapping):
            add({"provider": model.get("provider"), "model": model.get("default") or model.get("model"),
                 "base_url": model.get("base_url"), "key_env": model.get("key_env"),
                 "api_key": model.get("api_key"), "api_mode": model.get("api_mode")})
        try:
            from hermes_cli.fallback_config import get_fallback_chain
            for entry in get_fallback_chain(dict(config)):
                add(entry)
        except Exception:
            pass
        semantic = config.get("semantic_routing")
        if isinstance(semantic, Mapping):
            semantic_routes = semantic.get("routes")
            if isinstance(semantic_routes, Mapping):
                for route_value in semantic_routes.values():
                    if isinstance(route_value, Mapping):
                        add(route_value)
                    elif isinstance(route_value, str):
                        add({"provider": semantic.get("provider") or "", "model": route_value})
            semantic_fallbacks = semantic.get("fallbacks")
            if isinstance(semantic_fallbacks, Mapping):
                for route_list in semantic_fallbacks.values():
                    if isinstance(route_list, list):
                        for entry in route_list:
                            add(entry)
        for section_name in ("providers",):
            providers = config.get(section_name)
            if not isinstance(providers, Mapping):
                continue
            for provider, settings in providers.items():
                if not isinstance(settings, Mapping):
                    continue
                base = {
                    "provider": provider,
                    "base_url": settings.get("base_url") or settings.get("api") or settings.get("url"),
                    "api_key": settings.get("api_key"),
                    "key_env": settings.get("key_env") or settings.get("api_key_env"),
                    "key_cmd": settings.get("key_cmd"),
                    "api_mode": settings.get("api_mode") or settings.get("transport"),
                }
                add({**base, "model": settings.get("default_model") or settings.get("model")})
                models = settings.get("models")
                if isinstance(models, Mapping):
                    for model_name in models:
                        add({**base, "model": model_name})
                elif isinstance(models, list):
                    for model_entry in models:
                        add({**base, "model": model_entry.get("id") or model_entry.get("name")
                             if isinstance(model_entry, Mapping) else model_entry})
        legacy = config.get("custom_providers")
        if isinstance(legacy, list):
            for settings in legacy:
                if not isinstance(settings, Mapping):
                    continue
                provider = settings.get("name") or settings.get("provider")
                base = {"provider": provider,
                        "base_url": settings.get("base_url") or settings.get("api") or settings.get("url"),
                        "api_key": settings.get("api_key"),
                        "key_env": settings.get("key_env") or settings.get("api_key_env"),
                        "api_mode": settings.get("api_mode") or settings.get("transport")}
                add({**base, "model": settings.get("default_model") or settings.get("model")})
                models = settings.get("models")
                if isinstance(models, Mapping):
                    for model_name in models:
                        add({**base, "model": model_name})
                elif isinstance(models, list):
                    for model_name in models:
                        add({**base, "model": model_name})
    return routes


def _capabilities(route: Mapping[str, Any], config: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    from_config = config.get("model_overrides") if isinstance(config, Mapping) else None
    try:
        override_fingerprint = hashlib.sha256(
            json.dumps(from_config or {}, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8", "replace")
        ).hexdigest()
    except (TypeError, ValueError):
        override_fingerprint = ""
    key = (str(route["provider"]).lower(), str(route["model"]).lower(), override_fingerprint)
    with _ROUTE_LOCK:
        cached = _CAPABILITY_CACHE.get(key)
        if cached is not None:
            _CAPABILITY_CACHE.move_to_end(key)
            return dict(cached)
    try:
        from agent.models_dev import get_model_capabilities
        caps = get_model_capabilities(
            str(route["provider"]), str(route["model"]), allow_network=False,
            config=dict(config) if isinstance(config, Mapping) else None,
        )
        if caps is not None:
            result = {
                "supports_tools": bool(caps.supports_tools),
                "supports_reasoning": caps.supports_reasoning,
                "context_window": int(caps.context_window or 0),
                "model_family": str(caps.model_family or "").lower(),
            }
            _remember_capabilities(key, result)
            return result
    except Exception:
        pass
    result = {"supports_tools": True, "supports_reasoning": None, "context_window": 0, "model_family": ""}
    _remember_capabilities(key, result)
    return result


def _remember_capabilities(key: tuple[str, str, str], value: dict[str, Any]) -> None:
    with _ROUTE_LOCK:
        _CAPABILITY_CACHE[key] = dict(value)
        _CAPABILITY_CACHE.move_to_end(key)
        while len(_CAPABILITY_CACHE) > _METADATA_CACHE_LIMIT:
            _CAPABILITY_CACHE.popitem(last=False)


def _quality_score(model: str, caps: Mapping[str, Any], task: str) -> float:
    value = model.lower()
    family = str(caps.get("model_family") or "").lower()
    value = f"{value} {family}"
    score = 0.0
    if task == "coding":
        score += 55 if re.search(r"\b(?:coder|coding|code)\b", value) else 0
        score += 30 if caps.get("supports_reasoning") is True else 8 if caps.get("supports_reasoning") is None else 0
    elif task == "reasoning":
        score += 55 if caps.get("supports_reasoning") is True else 8 if caps.get("supports_reasoning") is None else -20
        score += 25 if re.search(r"reason|think|opus|pro|ultra|deep", value) else 0
    elif task == "long_context":
        score += min(float(caps.get("context_window") or 0) / 20_000, 60)
        score += 15 if caps.get("supports_reasoning") is True else 0
    elif task == "light":
        score += 45 if re.search(r"flash|mini|small|haiku|nano|lite|fast|lightning", value) else 0
        score -= 30 if re.search(r"reason(?:ing)?|think(?:ing)?|\br1\b|opus|ultra|pro", value) else 0
        size = re.search(r"(?:^|[^\d])(\d{1,3})\s*b(?:\W|$)", value)
        if size:
            score -= min(max(float(size.group(1)) - 8, 0) * 2, 40)
    else:
        score += 25 if caps.get("supports_reasoning") is True else 5 if caps.get("supports_reasoning") is None else 0
        score += 20 if re.search(r"opus|pro|ultra|70b|72b|110b|405b", value) else 0
    scale = re.search(r"(?:^|[^\d])(\d{1,3})\s*b(?:\W|$)", value)
    if scale and task != "light":
        score += min(float(scale.group(1)), 120) / 5
    return score


def _route_score(route: Mapping[str, Any], task: str, config: Optional[Mapping[str, Any]]) -> tuple[float, float]:
    caps = _capabilities(route, config)
    if not caps["supports_tools"]:
        return -10000, 0.0
    quality = _quality_score(str(route["model"]), caps, task)
    state = _ROUTE_HEALTH.get(_route_key(route), {})
    last_used = float(state.get("last_used") or 0.0)
    age = time.monotonic() - last_used if last_used else float("inf")
    load_balance = min(max(age, 0.0), 90.0) / 90.0
    return quality, load_balance


def select(
    message: str, config: Optional[Mapping[str, Any]] = None, *,
    primary_route: Optional[Mapping[str, Any]] = None,
) -> Optional[SemanticRoute]:
    if not enabled(config):
        return None
    started = time.perf_counter()
    classify_started = time.perf_counter()
    task = classify(message)
    classify_ms = (time.perf_counter() - classify_started) * 1000
    candidates, pool_ms, health_ms, pool_cache_hit = _configured_routes_timed(config, primary_route)
    if not candidates:
        return None
    rank_started = time.perf_counter()
    with _ROUTE_LOCK:
        scored = [(route, _route_score(route, task, config)) for route in candidates]
        ranked = [route for route, score in sorted(scored, key=lambda item: item[1], reverse=True)
                  if score[0] > -1000]
    if not ranked:
        return None
    rank_ms = (time.perf_counter() - rank_started) * 1000
    selected = ranked[0]
    state = _ROUTE_HEALTH.setdefault(_route_key(selected), {
        "available": True, "cooldown_until": 0.0, "last_failure": None,
        "failure_type": None, "retry_after": None, "failures": 0, "last_used": 0.0,
    })
    state["last_used"] = time.monotonic()
    return SemanticRoute(
        name=task,
        provider=str(selected["provider"]),
        model=str(selected["model"]),
        fallback_routes=tuple(ranked[1:]),
        primary_route=selected,
        timings_ms={
            "classification_ms": classify_ms,
            "route_pool_ms": pool_ms,
            "route_health_ms": health_ms,
            "ranking_ms": rank_ms,
            "candidate_count": float(len(candidates)),
            "pool_cache_hit": float(pool_cache_hit),
            "total_ms": (time.perf_counter() - started) * 1000,
        },
    )


def route_failure_reason(reason: Any) -> bool:
    return str(getattr(reason, "value", reason) or "").lower() in _TRANSIENT_REASONS
