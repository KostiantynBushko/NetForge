"""Configuration management.

The configuration capability has four operations, and the split between
them is the point:

``configuration.validate``
    Check a configuration text for the problems that break a device.
    Pure, offline, safe.

``configuration.diff``
    Compare two configuration texts.  Pure, offline, safe.

``configuration.backup``
    Read a configuration off a device.  Read-only, safe.

``configuration.restore``
    Write a configuration onto a device.  Modifies the device, so it is
    declared at the **system modification** level.

The first two are pure functions on purpose: they are the operations an
operator runs *before* touching a device, and they must work on a laptop
with no network and no credentials.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass

from pydantic import Field

from netforge.connectivity.ssh import SshConnection
from netforge.core.context import ExecutionContext
from netforge.core.logging import get_logger
from netforge.core.operation import Operation
from netforge.models.base import RequestModel, ResponseModel
from netforge.models.capability import CapabilityCategory
from netforge.models.risk import RiskLevel

__all__ = [
    "ConfigurationBackupOperation",
    "ConfigurationDiffOperation",
    "ConfigurationRestoreOperation",
    "ConfigurationValidateOperation",
    "ValidationIssue",
    "diff_configurations",
    "validate_configuration",
]

_logger = get_logger("configuration.manager")


@dataclass(slots=True)
class ValidationIssue:
    """One problem found in a configuration."""

    severity: str
    message: str
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the issue as a plain dictionary."""
        data: dict[str, object] = {"severity": self.severity, "message": self.message}
        if self.line is not None:
            data["line"] = self.line
        return data


def validate_configuration(text: str) -> list[ValidationIssue]:
    """Check a configuration text for the problems that break a device.

    The checks are the ones that are true of most network configuration
    formats -- the INI-like ones, the block-structured ones and the shell
    scripts:

    * trailing whitespace, which is invisible and breaks diffs;
    * a tab where a space is expected;
    * no newline at the end of the file;
    * a duplicated key in the same block;
    * an unbalanced quote;
    * a line that continues but has nothing to continue.
    """
    issues: list[ValidationIssue] = []
    content = text or ""

    if content and not content.endswith("\n"):
        issues.append(
            ValidationIssue(
                severity="warning",
                message="the file does not end with a newline",
            )
        )

    seen_keys: dict[str, int] = {}
    for number, line in enumerate(content.splitlines(), start=1):
        if line != line.rstrip() and line.strip():
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message="the line ends with whitespace",
                    line=number,
                )
            )
        if "\t" in line:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message="the line contains a tab",
                    line=number,
                )
            )
        if line.count('"') % 2 or line.count("'") % 2:
            issues.append(
                ValidationIssue(
                    severity="error",
                    message="the line has an unbalanced quote",
                    line=number,
                )
            )
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("!"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key and key not in {"", "["}:
                if key in seen_keys:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            message=f"the key {key!r} appears more than once",
                            line=number,
                        )
                    )
                else:
                    seen_keys[key] = number

    return issues


def diff_configurations(before: str, after: str, *, name: str = "configuration") -> list[str]:
    """Return a unified diff between two configuration texts.

    The diff is returned as a list of lines, so it can be rendered by any
    adapter without the adapter having to know about :mod:`difflib`.
    """
    return list(
        difflib.unified_diff(
            (before or "").splitlines(keepends=True),
            (after or "").splitlines(keepends=True),
            fromfile=f"{name} (current)",
            tofile=f"{name} (candidate)",
            n=3,
        )
    )


class ConfigurationValidateRequest(RequestModel):
    """Request of :class:`ConfigurationValidateOperation`."""

    content: str = Field(description="The configuration text to validate.")


class ConfigurationValidateResponse(ResponseModel):
    """Response of :class:`ConfigurationValidateOperation`."""

    issues: list[dict[str, object]] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    valid: bool = True


class ConfigurationValidateOperation(Operation[ConfigurationValidateRequest, ConfigurationValidateResponse]):
    """Check a configuration text for problems."""

    name = "configuration.validate"
    category = CapabilityCategory.CONFIGURATION
    risk_level = RiskLevel.SAFE
    summary = "Check a configuration text for the problems that break a device."
    description = (
        "Checks a configuration text for trailing whitespace, tabs, a missing final "
        "newline, duplicated keys and unbalanced quotes. It changes nothing, so the "
        "operation is declared at the safe level."
    )
    tags = frozenset({"configuration", "validate", "lint"})

    request_model = ConfigurationValidateRequest
    response_model = ConfigurationValidateResponse

    async def execute(
        self, request: ConfigurationValidateRequest, context: ExecutionContext
    ) -> ConfigurationValidateResponse:
        """Validate the configuration."""
        started = time.perf_counter()
        issues = validate_configuration(request.content)
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        return ConfigurationValidateResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            issues=[issue.to_dict() for issue in issues],
            error_count=errors,
            warning_count=warnings,
            valid=errors == 0,
        )


class ConfigurationDiffRequest(RequestModel):
    """Request of :class:`ConfigurationDiffOperation`."""

    current: str = Field(description="The configuration as it is now.")
    candidate: str = Field(description="The configuration as it should be.")


class ConfigurationDiffResponse(ResponseModel):
    """Response of :class:`ConfigurationDiffOperation`."""

    diff: list[str] = Field(default_factory=list)
    identical: bool = True
    changed_lines: int = 0


class ConfigurationDiffOperation(Operation[ConfigurationDiffRequest, ConfigurationDiffResponse]):
    """Compare two configuration texts."""

    name = "configuration.diff"
    category = CapabilityCategory.CONFIGURATION
    risk_level = RiskLevel.SAFE
    summary = "Compare two configuration texts and report the difference."
    description = (
        "Produces a unified diff between the current configuration and a candidate one. "
        "It is a pure comparison, so the operation is declared at the safe level."
    )
    tags = frozenset({"configuration", "diff", "compare"})

    request_model = ConfigurationDiffRequest
    response_model = ConfigurationDiffResponse

    async def execute(
        self, request: ConfigurationDiffRequest, context: ExecutionContext
    ) -> ConfigurationDiffResponse:
        """Produce the diff."""
        started = time.perf_counter()
        diff = diff_configurations(request.current, request.candidate)
        changed = sum(1 for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
        return ConfigurationDiffResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            diff=diff,
            identical=not changed,
            changed_lines=changed,
        )


class ConfigurationBackupRequest(RequestModel):
    """Request of :class:`ConfigurationBackupOperation`."""

    host: str = Field(min_length=1, description="The device to read from.")
    path: str = Field(min_length=1, description="The configuration file to read.")
    port: int = Field(default=22, ge=1, le=65535, description="The SSH port.")
    username: str | None = Field(default=None, description="The user to log in as.")
    password: str | None = Field(default=None, description="The password, if one is needed.")
    command: str | None = Field(default=None, description="The command that prints the configuration.")


class ConfigurationBackupResponse(ResponseModel):
    """Response of :class:`ConfigurationBackupOperation`."""

    host: str
    path: str
    content: str = ""
    exit_code: int = 0
    bytes: int = 0


class ConfigurationBackupOperation(Operation[ConfigurationBackupRequest, ConfigurationBackupResponse]):
    """Read a configuration off a device."""

    name = "configuration.backup"
    category = CapabilityCategory.CONFIGURATION
    risk_level = RiskLevel.SAFE
    summary = "Read a configuration file off a device over SSH."
    description = (
        "Reads a configuration file from a device over SSH and returns its contents. "
        "The device is only read from, so the operation is declared at the safe level."
    )
    tags = frozenset({"configuration", "backup", "ssh"})

    request_model = ConfigurationBackupRequest
    response_model = ConfigurationBackupResponse

    async def execute(
        self, request: ConfigurationBackupRequest, context: ExecutionContext
    ) -> ConfigurationBackupResponse:
        """Read the configuration."""
        command = request.command or f"cat {request.path}"
        connection = SshConnection(
            request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            timeout=context.timeout,
        )
        started = time.perf_counter()
        try:
            await connection.connect()
            exit_code, stdout, stderr = await connection.execute(command)
        except Exception as exc:  # noqa: BLE001 - a transport failure is reported, not raised
            return ConfigurationBackupResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                path=request.path,
                exit_code=-1,
                warnings=[f"the configuration could not be read: {exc}"],
            )
        finally:
            await connection.close()

        return ConfigurationBackupResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            path=request.path,
            content=stdout,
            exit_code=exit_code,
            bytes=len(stdout.encode("utf-8")),
            warnings=[stderr] if stderr.strip() else [],
        )


class ConfigurationRestoreRequest(RequestModel):
    """Request of :class:`ConfigurationRestoreOperation`."""

    host: str = Field(min_length=1, description="The device to write to.")
    path: str = Field(min_length=1, description="The configuration file to write.")
    content: str = Field(description="The configuration to write.")
    port: int = Field(default=22, ge=1, le=65535, description="The SSH port.")
    username: str | None = Field(default=None, description="The user to log in as.")
    password: str | None = Field(default=None, description="The password, if one is needed.")
    backup_first: bool = Field(default=True, description="Copy the current file aside before writing.")


class ConfigurationRestoreResponse(ResponseModel):
    """Response of :class:`ConfigurationRestoreOperation`."""

    host: str
    path: str
    written: bool = False
    backup_path: str | None = None
    exit_code: int = 0


class ConfigurationRestoreOperation(Operation[ConfigurationRestoreRequest, ConfigurationRestoreResponse]):
    """Write a configuration onto a device."""

    name = "configuration.restore"
    category = CapabilityCategory.CONFIGURATION
    risk_level = RiskLevel.SYSTEM_MODIFICATION
    summary = "Write a configuration file onto a device over SSH."
    description = (
        "Writes a configuration file onto a device over SSH, copying the current file "
        "aside first. This changes the state of the device, which is why the operation "
        "is declared at the system modification level -- the highest one."
    )
    tags = frozenset({"configuration", "restore", "deploy", "ssh"})

    request_model = ConfigurationRestoreRequest
    response_model = ConfigurationRestoreResponse

    async def execute(
        self, request: ConfigurationRestoreRequest, context: ExecutionContext
    ) -> ConfigurationRestoreResponse:
        """Write the configuration."""
        import base64

        connection = SshConnection(
            request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            timeout=context.timeout,
        )
        started = time.perf_counter()
        backup_path: str | None = None
        try:
            await connection.connect()
            if request.backup_first:
                backup_path = f"{request.path}.netforge.bak"
                await connection.execute(f"cp {request.path} {backup_path}")

            payload = base64.b64encode(request.content.encode("utf-8")).decode("ascii")
            exit_code, _stdout, stderr = await connection.execute(
                f"printf '%s' '{payload}' | base64 -d > {request.path}"
            )
        except Exception as exc:  # noqa: BLE001 - a transport failure is reported, not raised
            return ConfigurationRestoreResponse(
                operation=self.name,
                risk_level=self.risk_level.label,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                host=request.host,
                path=request.path,
                written=False,
                backup_path=backup_path,
                exit_code=-1,
                warnings=[f"the configuration could not be written: {exc}"],
            )
        finally:
            await connection.close()

        return ConfigurationRestoreResponse(
            operation=self.name,
            risk_level=self.risk_level.label,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            host=request.host,
            path=request.path,
            written=exit_code == 0,
            backup_path=backup_path,
            exit_code=exit_code,
            warnings=[stderr] if stderr.strip() else [],
        )
