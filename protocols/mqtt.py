"""MQTT.

The MQTT client itself needs a broker library, and ``paho-mqtt`` is the
optional extra that provides one.  What is implemented *here* is the part
that has to be exactly right and is worth having on its own: the topic
filter.

MQTT topics are matched with two wildcards -- ``+`` matches one level and
``#`` matches the rest of the topic -- and the rules for them are subtle
enough that getting them wrong silently loses messages.  The matcher is a
pure function over strings, so it can be tested exhaustively.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import Field

from netforge.core.context import ExecutionContext
from netforge.core.exceptions import DependencyMissingError
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = ["MqttTopicFilter", "MqttTopicOperation", "MQTT_EXTRA"]

_logger = get_logger("protocols.mqtt")

MQTT_EXTRA = "mqtt"


@dataclass(frozen=True, slots=True)
class MqttTopicFilter:
    """An MQTT topic filter."""

    pattern: str

    def matches(self, topic: str) -> bool:
        """Return ``True`` when ``topic`` matches this filter.

        The rules, from the MQTT specification:

        * ``#`` must be the last character of the filter and matches the
          parent level and every level below it;
        * ``+`` matches exactly one level;
        * a filter without wildcards matches only that exact topic;
        * a filter beginning with ``#`` or ``+`` matches at the first level.
        """
        pattern_levels = self.pattern.split("/")
        topic_levels = topic.split("/")

        for index, pattern_level in enumerate(pattern_levels):
            if pattern_level == "#":
                # '#' matches the parent level and everything below it.
                return index <= len(topic_levels)
            if index >= len(topic_levels):
                return False
            if pattern_level == "+":
                continue
            if pattern_level != topic_levels[index]:
                return False

        return len(pattern_levels) == len(topic_levels)

    def validate(self) -> list[str]:
        """Return the problems with the filter; an empty list means it is valid."""
        problems: list[str] = []
        if not self.pattern:
            problems.append("the filter is empty")
            return problems
        levels = self.pattern.split("/")
        for index, level in enumerate(levels):
            if "#" in level and level != "#":
                problems.append(f"'#' must occupy a whole level (level {index + 1} is {level!r})")
            if "+" in level and level != "+":
                problems.append(f"'+' must occupy a whole level (level {index + 1} is {level!r})")
            if "#" in level and index != len(levels) - 1:
                problems.append("'#' must be the last level of the filter")
        return problems


class MqttTopicRequest(RequestModel):
    """Request of :class:`MqttTopicOperation`."""

    filters: list[str] = Field(min_length=1, description="The topic filters to test.")
    topics: list[str] = Field(min_length=1, description="The topics to test them against.")


class MqttTopicResponse(ResponseModel):
    """Response of :class:`MqttTopicOperation`."""

    matches: list[dict[str, object]] = Field(default_factory=list)
    unmatched_topics: list[str] = Field(default_factory=list)
    invalid_filters: list[str] = Field(default_factory=list)


class MqttTopicOperation(Operation[MqttTopicRequest, MqttTopicResponse]):
    """Match MQTT topics against a set of filters."""

    name = "protocols.mqtt.topic.match"
    category = CapabilityCategory.PROTOCOLS
    risk_level = RiskLevel.SAFE
    summary = "Match MQTT topics against wildcard filters."
    description = (
        "Tests a set of MQTT topics against a set of topic filters and reports which "
        "filter matched which topic. It follows the wildcard rules of the MQTT "
        "specification exactly, including the rule that '#' must be the last level."
    )
    tags = frozenset({"mqtt", "topic", "filter", "subscription"})

    request_model = MqttTopicRequest
    response_model = MqttTopicResponse

    async def execute(
        self, request: MqttTopicRequest, context: ExecutionContext
    ) -> MqttTopicResponse:
        """Match the topics against the filters."""
        started = time.perf_counter()
        matches: list[dict[str, object]] = []
        invalid: list[str] = []
        filters: list[MqttTopicFilter] = []

        for pattern in request.filters:
            candidate = MqttTopicFilter(pattern)
            problems = candidate.validate()
            if problems:
                invalid.append(pattern)
                continue
            filters.append(candidate)

        matched_topics: set[str] = set()
        for topic in request.topics:
            for candidate in filters:
                if candidate.matches(topic):
                    matches.append({"topic": topic, "filter": candidate.pattern})
                    matched_topics.add(topic)
                    break

        return MqttTopicResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            matches=matches,
            unmatched_topics=[topic for topic in request.topics if topic not in matched_topics],
            invalid_filters=invalid,
        )


def _load_paho():
    try:
        import paho.mqtt.client as mqtt  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DependencyMissingError(
            "paho-mqtt",
            extra="mqtt",
            feature="the MQTT broker client",
        ) from exc
    import paho.mqtt.client as mqtt

    return mqtt
