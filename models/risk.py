"""The risk model.

NetForge declares a risk level for *every* operation.  The level is part of
the operation's identity: it is published in the registry, enforced by the
execution context, and rendered by every adapter.

The four levels are the ones described in the NetForge specification:

===== ==================== ================================================
Level Name                Meaning
===== ==================== ================================================
1     SAFE                Read-only information gathering.
2     OBSERVABILITY       Monitoring and traffic observation.
3     MANIPULATION        Operations capable of affecting traffic behavior.
4     SYSTEM_MODIFICATION Operations that modify system or network state.
===== ==================== ================================================

The enum is an :class:`enum.IntEnum` on purpose.  Risk comparisons are
ordinal -- "is this operation at or below the ceiling the operator allowed?"
-- and an integer comparison is the clearest expression of that.  It also
means the level serialises as a number in JSON, which the REST adapter can
expose directly.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["RiskLevel", "RISK_LEVEL_ORDER"]


class RiskLevel(IntEnum):
    """The risk level an operation is declared at."""

    SAFE = 1
    OBSERVABILITY = 2
    MANIPULATION = 3
    SYSTEM_MODIFICATION = 4

    @property
    def label(self) -> str:
        """Return the human-readable name of the level."""
        return self.name.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Return a one-line description of what the level means."""
        return _DESCRIPTIONS[self]

    @classmethod
    def parse(cls, value: str | int | RiskLevel) -> RiskLevel:
        """Coerce ``value`` into a :class:`RiskLevel`.

        Accepts the member itself, its integer value, and the spellings an
        operator is likely to type: ``"safe"``, ``"SAFE"``, ``"level 2"``,
        ``"observability"``, ``"system_modification"``, ``"system-modification"``.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError as exc:
                raise ValueError(f"unknown risk level: {value}") from exc
        if not isinstance(value, str):
            raise TypeError(f"cannot interpret {value!r} as a risk level")

        text = value.strip().lower().replace("-", "_").replace(" ", "_")
        if text.startswith("level_"):
            text = text[len("level_") :]
        if text.isdigit():
            return cls.parse(int(text))
        try:
            return cls[text.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown risk level: {value!r}") from exc

    def allows(self, other: RiskLevel) -> bool:
        """Return ``True`` when ``other`` is at or below this level."""
        return int(other) <= int(self)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.label


_DESCRIPTIONS: dict[RiskLevel, str] = {
    RiskLevel.SAFE: "Read-only information gathering.",
    RiskLevel.OBSERVABILITY: "Monitoring and traffic observation.",
    RiskLevel.MANIPULATION: "Operations capable of affecting traffic behavior.",
    RiskLevel.SYSTEM_MODIFICATION: "Operations that modify system or network state.",
}

#: The levels in ascending order, for menus and ceilings.
RISK_LEVEL_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.SAFE,
    RiskLevel.OBSERVABILITY,
    RiskLevel.MANIPULATION,
    RiskLevel.SYSTEM_MODIFICATION,
)
