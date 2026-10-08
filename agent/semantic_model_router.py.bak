"""Deterministic semantic model routing for gateway turns.

No extra LLM classifier call is made. Explicit session/channel model choices
remain authoritative; the gateway uses its normal OpenRouter credential and
fallback machinery after a route is selected.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

@dataclass(frozen=True)
class SemanticRoute:
    name: str
    model: str

DEFAULT_ROUTES = {
    "light": "google/gemma-4-26b-a4b-it:free",
    "coding": "qwen/qwen3-coder:free",
    "reasoning": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "general": "google/gemma-4-26b-a4b-it:free",
}

_LIGHT = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|yes|no|good morning|good evening|"
    r"what(?:'s| is) your name|who are you|مرحبا|أهلا|اهلا|شكرا|نعم|لا)\b", re.I)
_CODING = re.compile(
    r"(?:\b(?:code|coding|program|programming|debug|debugging|bug|exception|stack trace|"
    r"python|javascript|typescript|java|rust|go|sql|bash|shell|yaml|json|api|sdk|repository|"
    r"repo|github|git|commit|branch|pull request|docker|kubernetes|function|class|method|"
    r"module|import|package|dependency|regex|terminal|command|script|compile|compiler|test|"
    r"pytest|unittest|refactor|patch|diff)\b|Traceback \(most recent call last\)|"
    r"(?:^|\s)(?:/workspaces/|~/|\.\.?/)[^\s]+)", re.I)
_REASONING = re.compile(
    r"(?:\b(?:analy[sz]e|analysis|architecture|architectural|investigate|investigation|"
    r"root cause|deep dive|deeply|complex|complicated|compare|comparison|trade[- ]?off|"
    r"design|strategy|strategic|why|explain why|review|audit|diagnose|diagnosis|reasoning|"
    r"logic|evaluate|evaluation|plan|roadmap|research|comprehensive|thorough|critique|"
    r"optimi[sz]e|security|threat model|performance|bottleneck)\b|حلل|تحليل|راجع|مراجعة|"
    r"سبب|جذر المشكلة|لماذا|قارن|مقارنة|معمارية|تصميم|استقص|تحقيق|بالتفصيل|شامل|"
    r"استراتيجية|خطة|تشخيص|منطق|أداء|أمن)", re.I)

def _configured_routes(config: Optional[Mapping[str, Any]]) -> dict[str, str]:
    routes = dict(DEFAULT_ROUTES)
    if isinstance(config, Mapping):
        section = config.get("semantic_routing")
        configured = section.get("routes") if isinstance(section, Mapping) else None
        if isinstance(configured, Mapping):
            for name in routes:
                value = configured.get(name)
                if isinstance(value, str) and value.strip():
                    routes[name] = value.strip()
    return routes

def enabled(config: Optional[Mapping[str, Any]]) -> bool:
    flag = os.environ.get("HERMES_SEMANTIC_ROUTING", "").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if flag in {"1", "true", "on", "yes"}:
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    if isinstance(config, Mapping):
        section = config.get("semantic_routing")
        if isinstance(section, Mapping) and section.get("enabled") is False:
            return False
    return bool(os.environ.get("OPENROUTER_API_KEY"))

def classify(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return "general"
    if _CODING.search(text):
        return "coding"
    if _REASONING.search(text):
        return "reasoning"
    if len(text) <= 180 and _LIGHT.search(text):
        return "light"
    if len(text) <= 320 and text.count("?") <= 1 and len(text.split()) <= 55:
        return "light"
    return "general"

def select(message: str, config: Optional[Mapping[str, Any]] = None) -> Optional[SemanticRoute]:
    if not enabled(config):
        return None
    kind = classify(message)
    routes = _configured_routes(config)
    return SemanticRoute(kind, routes.get(kind, routes["general"]))
