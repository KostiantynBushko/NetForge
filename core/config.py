"""Framework configuration.

The configuration is a Pydantic model, so it validates like everything else
in NetForge, and it can be built from three sources, in increasing order of
precedence:

1. the defaults in this module;
2. a configuration file (JSON);
3. the environment.

The environment prefix is ``NETFORGE_``.  Every field has a matching
variable, e.g. ``NETFORGE_DEFAULT_TIMEOUT`` or ``NETFORGE_MAX_RISK``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from netforge.core.exceptions import ConfigurationError
from netforge.models.base import NetForgeModel
from netforge.models.risk import RiskLevel

__all__ = ["ENV_PREFIX", "NetForgeConfig"]

ENV_PREFIX = "NETFORGE_"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class NetForgeConfig(NetForgeModel):
    """The configuration of the NetForge framework."""

    default_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Default time budget, in seconds, for a single operation.",
    )
    max_risk: RiskLevel = Field(
        default=RiskLevel.SYSTEM_MODIFICATION,
        description="The highest risk level an operation may run at.",
    )
    log_level: str = Field(default="INFO", description="Root log level for NetForge.")
    verify_tls: bool = Field(default=True, description="Verify TLS certificates when connecting.")
    user_agent: str = Field(default="netforge/0.1.0", description="User agent sent by HTTP operations.")
    capture_directory: Path = Field(
        default=Path("./captures"),
        description="Directory captures are written to.",
    )
    allow_native: bool = Field(
        default=True,
        description="Allow native (Rust/C++) implementations to serve operations when available.",
    )

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            raise ValueError(f"unknown log level: {value!r}")
        return level

    @field_validator("capture_directory")
    @classmethod
    def _expand_capture_directory(cls, value: Path) -> Path:
        return Path(os.path.expandvars(str(value))).expanduser()

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        base: "NetForgeConfig | None" = None,
    ) -> "NetForgeConfig":
        """Build a configuration from the environment.

        ``base`` supplies the values that are not overridden by the
        environment, which lets a caller layer a file, an environment and a
        set of overrides on top of each other.
        """
        env = dict(os.environ if env is None else env)
        values: dict[str, Any] = base.model_dump() if base is not None else {}

        def _set(field: str, raw: str) -> None:
            values[field] = raw

        for field in cls.model_fields:
            key = f"{ENV_PREFIX}{field.upper()}"
            if key not in env:
                continue
            raw = env[key]
            if field == "max_risk":
                values[field] = RiskLevel.parse(raw)
            elif field == "verify_tls":
                values[field] = _parse_bool(raw, key)
            elif field == "allow_native":
                values[field] = _parse_bool(raw, key)
            elif field == "default_timeout":
                try:
                    values[field] = float(raw)
                except ValueError as exc:
                    raise ConfigurationError(f"{key} must be a number, got {raw!r}") from exc
            else:
                _set(field, raw)

        return cls(**values)

    @classmethod
    def from_file(cls, path: str | Path, *, base: "NetForgeConfig | None" = None) -> "NetForgeConfig":
        """Build a configuration from a JSON file."""
        path = Path(path).expanduser()
        if not path.is_file():
            raise ConfigurationError(f"configuration file not found: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"cannot read configuration file {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ConfigurationError(f"configuration file {path} must contain a JSON object")
        merged = {**(base.model_dump() if base is not None else {}), **payload}
        try:
            return cls(**merged)
        except Exception as exc:
            raise ConfigurationError(f"invalid configuration in {path}: {exc}") from exc

    @classmethod
    def load(cls, path: str | Path | None = None, *, env: dict[str, str] | None = None) -> "NetForgeConfig":
        """Load the configuration from an optional file and the environment.

        The environment wins over the file, because that is the layer an
        operator reaches for last and expects to be authoritative.
        """
        config = cls.from_file(path) if path else cls()
        return cls.from_env(env, base=config)


def _parse_bool(raw: str, key: str) -> bool:
    text = raw.strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ConfigurationError(f"{key} must be a boolean, got {raw!r}")
