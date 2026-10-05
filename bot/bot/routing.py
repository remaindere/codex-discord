from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Route(str, Enum):
    CHAT = "chat"
    CODEX = "codex"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str


@dataclass(frozen=True)
class RouteContext:
    has_attachments: bool = False
    previous_route: Route | None = None


@dataclass(frozen=True)
class RoutingWeights:
    attachment: int
    path: int
    strong_work_term: int
    realtime: int
    work_target: int
    work_action: int
    followup_reference: int
    followup_action: int
    followup_context: int
    previous_codex: int
    explanation: int


@dataclass(frozen=True)
class RoutingThresholds:
    codex: int


@dataclass(frozen=True)
class RoutingLexicon:
    work_targets: tuple[str, ...]
    work_actions: tuple[str, ...]
    strong_work_terms: tuple[str, ...]
    realtime_anchors: tuple[str, ...]
    realtime_actions: tuple[str, ...]
    realtime_modifiers: tuple[str, ...]
    followup_reference: tuple[str, ...]
    followup_action: tuple[str, ...]
    followup_context: tuple[str, ...]
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class RoutingConfig:
    thresholds: RoutingThresholds
    weights: RoutingWeights
    lexicon: RoutingLexicon


_CONFIG_PATH = Path(__file__).with_name("routing.toml")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_items(data: dict[str, Any], section: str) -> tuple[str, ...]:
    terms = data.get("terms", {})
    if not isinstance(terms, dict):
        raise TypeError("routing.toml [terms] must be a table")

    value = terms.get(section, {})
    if not isinstance(value, dict):
        raise TypeError(f"routing.toml [terms.{section}] must be a table")

    items = value.get("items", [])
    if not isinstance(items, list):
        raise TypeError(
            f"routing.toml [terms.{section}].items must be a list"
        )

    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise TypeError(
                f"routing.toml [terms.{section}].items must contain strings"
            )

        normalized = " ".join(item.casefold().split())
        if normalized:
            result.append(normalized)

    # Preserve order while removing duplicates.
    return tuple(dict.fromkeys(result))


def _load_config(path: Path = _CONFIG_PATH) -> RoutingConfig:
    with path.open("rb") as fp:
        data = tomllib.load(fp)

    threshold_data = data.get("thresholds", {})
    weight_data = data.get("weights", {})

    if not isinstance(threshold_data, dict):
        raise TypeError("routing.toml [thresholds] must be a table")
    if not isinstance(weight_data, dict):
        raise TypeError("routing.toml [weights] must be a table")

    thresholds = RoutingThresholds(
        codex=int(threshold_data["codex"]),
    )

    weights = RoutingWeights(
        attachment=int(weight_data["attachment"]),
        path=int(weight_data["path"]),
        strong_work_term=int(weight_data["strong_work_term"]),
        realtime=int(weight_data["realtime"]),
        work_target=int(weight_data["work_target"]),
        work_action=int(weight_data["work_action"]),
        followup_reference=int(weight_data["followup_reference"]),
        followup_action=int(weight_data["followup_action"]),
        followup_context=int(weight_data["followup_context"]),
        previous_codex=int(weight_data["previous_codex"]),
        explanation=int(weight_data["explanation"]),
    )

    lexicon = RoutingLexicon(
        work_targets=_load_items(data, "work_targets"),
        work_actions=_load_items(data, "work_actions"),
        strong_work_terms=_load_items(data, "strong_work_terms"),
        realtime_anchors=_load_items(data, "realtime_anchors"),
        realtime_actions=_load_items(data, "realtime_actions"),
        realtime_modifiers=_load_items(data, "realtime_modifiers"),
        followup_reference=_load_items(data, "followup_reference"),
        followup_action=_load_items(data, "followup_action"),
        followup_context=_load_items(data, "followup_context"),
        explanation=_load_items(data, "explanation"),
    )

    return RoutingConfig(
        thresholds=thresholds,
        weights=weights,
        lexicon=lexicon,
    )


_CONFIG = _load_config()


# ---------------------------------------------------------------------------
# Path detection
# ---------------------------------------------------------------------------

_PATH_PATTERNS = (
    # Unix absolute path.
    re.compile(r"(?:^|\s)/(?:[^\s]+)"),

    # Home-relative path.
    re.compile(r"(?:^|\s)~/[^\s]+"),

    # Relative path: ./foo, ../foo.
    re.compile(r"(?:^|\s)\.{1,2}/[^\s]+"),

    # Windows drive path: C:\foo, C:/foo.
    re.compile(
        r"(?:^|\s)[a-z]:[\\/][^\s]+",
        re.IGNORECASE,
    ),

    # UNC path: \\server\share.
    re.compile(r"(?:^|\s)\\\\[^\s]+"),

    # Nested path such as bot/routing.py or src/foo/bar.
    # URLs are explicitly excluded.
    re.compile(
        r"(?:^|\s)"
        r"(?!https?://)"
        r"(?:\.{0,2}/)?"
        r"[^\s/\\]+(?:/[^\s/\\]+)+"
        r"(?=\s|$|[),.:;!?])",
        re.IGNORECASE,
    ),

    # Bare source/config/document filenames such as routing.py.
    re.compile(
        r"(?:^|\s)[^\s/\\]+\."
        r"(?:py|pyw|js|mjs|cjs|ts|tsx|jsx|java|kt|kts|go|rs|c|cc|cpp|h|hpp|"
        r"cs|rb|php|swift|sh|bash|zsh|fish|ps1|psm1|bat|cmd|"
        r"json|json5|yaml|yml|toml|ini|cfg|conf|env|"
        r"xml|html|htm|css|scss|sass|less|sql|md|rst|txt|log)"
        r"(?=\s|$|[),.:;!?])",
        re.IGNORECASE,
    ),
)


# ASCII-only terms need word-like boundaries. This prevents short terms such
# as "c", "go", "pr", or "api" from matching arbitrary words.
_ASCII_TERM_RE = re.compile(r"^[a-z0-9][a-z0-9 _./+:#-]*$")


def _contains_term(text: str, term: str) -> bool:
    if _ASCII_TERM_RE.fullmatch(term):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        return pattern.search(text) is not None

    return term in text


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_path(normalized: str) -> bool:
    return any(pattern.search(normalized) for pattern in _PATH_PATTERNS)


# ---------------------------------------------------------------------------
# Explicit route override
# ---------------------------------------------------------------------------


def _get_route_override(normalized: str) -> RouteDecision | None:
    if normalized == "!chat" or normalized.startswith("!chat "):
        return RouteDecision(Route.CHAT, "explicit:chat")

    if normalized == "!codex" or normalized.startswith("!codex "):
        return RouteDecision(Route.CODEX, "explicit:codex")

    return None


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteSignals:
    has_attachment: bool
    has_path: bool
    has_work_target: bool
    has_work_action: bool
    has_strong_work_term: bool
    has_realtime: bool
    has_followup_reference: bool
    has_followup_action: bool
    has_followup_context: bool
    has_explanation: bool


def _matches_realtime_intent(
    normalized: str,
    config: RoutingConfig,
) -> bool:
    lexicon = config.lexicon

    has_anchor = _contains_any(
        normalized,
        lexicon.realtime_anchors,
    )
    has_action = _contains_any(
        normalized,
        lexicon.realtime_actions,
    )
    has_modifier = _contains_any(
        normalized,
        lexicon.realtime_modifiers,
    )

    # Explicit web/search intent is enough.
    if has_action:
        return True

    # Realtime domain + time modifier.
    if has_anchor and has_modifier:
        return True

    # Realtime domains such as weather/news/exchange rate are inherently
    # time-sensitive enough that the anchor itself is sufficient.
    return has_anchor


def _collect_signals(
    normalized: str,
    context: RouteContext,
    config: RoutingConfig,
) -> RouteSignals:
    lexicon = config.lexicon

    return RouteSignals(
        has_attachment=context.has_attachments,
        has_path=_contains_path(normalized),
        has_work_target=_contains_any(
            normalized,
            lexicon.work_targets,
        ),
        has_work_action=_contains_any(
            normalized,
            lexicon.work_actions,
        ),
        has_strong_work_term=_contains_any(
            normalized,
            lexicon.strong_work_terms,
        ),
        has_realtime=_matches_realtime_intent(
            normalized,
            config,
        ),
        has_followup_reference=_contains_any(
            normalized,
            lexicon.followup_reference,
        ),
        has_followup_action=_contains_any(
            normalized,
            lexicon.followup_action,
        ),
        has_followup_context=_contains_any(
            normalized,
            lexicon.followup_context,
        ),
        has_explanation=_contains_any(
            normalized,
            lexicon.explanation,
        ),
    )


# ---------------------------------------------------------------------------
# Intent classification helpers
# ---------------------------------------------------------------------------


def _is_work_intent(signals: RouteSignals) -> bool:
    return signals.has_work_target and signals.has_work_action


def _is_followup(
    signals: RouteSignals,
    context: RouteContext,
) -> bool:
    if context.previous_route is not Route.CODEX:
        return False

    return (
        signals.has_followup_reference
        or signals.has_followup_action
        or signals.has_followup_context
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_codex(
    signals: RouteSignals,
    context: RouteContext,
    config: RoutingConfig,
) -> int:
    weights = config.weights
    score = 0

    if signals.has_attachment:
        score += weights.attachment

    if signals.has_path:
        score += weights.path

    if signals.has_strong_work_term:
        score += weights.strong_work_term

    if signals.has_realtime:
        score += weights.realtime

    if signals.has_work_target:
        score += weights.work_target

    if signals.has_work_action:
        score += weights.work_action

    if context.previous_route is Route.CODEX:
        followup_detected = (
            signals.has_followup_reference
            or signals.has_followup_action
            or signals.has_followup_context
        )

        if followup_detected:
            score += weights.previous_codex

            if signals.has_followup_reference:
                score += weights.followup_reference

            if signals.has_followup_action:
                score += weights.followup_action

            if signals.has_followup_context:
                score += weights.followup_context

    # Explanation wording is a weak counter-signal only. Hard signals and
    # direct work intent are handled earlier and therefore remain dominant.
    if signals.has_explanation:
        score += weights.explanation

    return score


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


def route_request(
    question: str,
    context: RouteContext,
) -> RouteDecision:
    normalized = " ".join(question.casefold().split())

    if not normalized:
        return RouteDecision(Route.CHAT, "fallback:chat")

    # 1. Explicit override always wins.
    override = _get_route_override(normalized)
    if override is not None:
        return override

    signals = _collect_signals(
        normalized,
        context,
        _CONFIG,
    )

    # 2. Hard local signals.
    if signals.has_attachment:
        return RouteDecision(Route.CODEX, "attachment")

    if signals.has_path:
        return RouteDecision(Route.CODEX, "filesystem:path")

    # 3. Clear realtime intent is a new request and overrides previous Codex
    # context. Generic words such as "today" or "current" do not trigger it
    # by themselves; they need a realtime domain or explicit search action.
    if signals.has_realtime:
        return RouteDecision(Route.CODEX, "realtime")

    # 4. When previous Codex context exists, explicit continuation wins over
    # generic work/technical signals so the reason remains contextual.
    if _is_followup(signals, context):
        return RouteDecision(Route.CODEX, "followup:codex")

    # 5. Strong explicit technical/dev terms.
    # These are more specific than the generic target + action combination.
    if signals.has_strong_work_term:
        return RouteDecision(Route.CODEX, "technical_term")

    # 6. Direct work intent.
    if _is_work_intent(signals):
        return RouteDecision(Route.CODEX, "work_intent")

    # 7. Remaining ambiguous cases use the configurable score threshold.
    score = _score_codex(
        signals,
        context,
        _CONFIG,
    )

    if score >= _CONFIG.thresholds.codex:
        return RouteDecision(Route.CODEX, f"scored:codex:{score}")

    # 8. Conservative fallback.
    return RouteDecision(Route.CHAT, "fallback:chat")
