"""Configuration management.

Reading a configuration, checking it, comparing it with a candidate and
writing it back.  The operations are split by risk: the first three are
read-only, the last one changes the device and is declared at the system
modification level.
"""

from __future__ import annotations

from netforge.configuration.manager import (
    ConfigurationBackupOperation,
    ConfigurationDiffOperation,
    ConfigurationRestoreOperation,
    ConfigurationValidateOperation,
    ValidationIssue,
    diff_configurations,
    validate_configuration,
)

__all__ = [
    "ConfigurationBackupOperation",
    "ConfigurationDiffOperation",
    "ConfigurationRestoreOperation",
    "ConfigurationValidateOperation",
    "ValidationIssue",
    "diff_configurations",
    "validate_configuration",
]
