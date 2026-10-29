"""The risk model and the risk policy."""

from __future__ import annotations

import pytest

from netforge.core.config import NetForgeConfig
from netforge.core.context import ExecutionContext
from netforge.core.exceptions import ConfigurationError, RiskPolicyError
from netforge.models.risk import RISK_LEVEL_ORDER, RiskLevel


class TestRiskLevel:
    def test_the_four_levels_are_ordered(self):
        assert RiskLevel.SAFE < RiskLevel.OBSERVABILITY
        assert RiskLevel.OBSERVABILITY < RiskLevel.MANIPULATION
        assert RiskLevel.MANIPULATION < RiskLevel.SYSTEM_MODIFICATION
        assert len(RISK_LEVEL_ORDER) == 4

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("safe", RiskLevel.SAFE),
            ("SAFE", RiskLevel.SAFE),
            ("Level 2", RiskLevel.OBSERVABILITY),
            ("level_3", RiskLevel.MANIPULATION),
            ("system-modification", RiskLevel.SYSTEM_MODIFICATION),
            ("system_modification", RiskLevel.SYSTEM_MODIFICATION),
            (2, RiskLevel.OBSERVABILITY),
            (RiskLevel.SAFE, RiskLevel.SAFE),
        ],
    )
    def test_a_level_is_parsed_from_the_spellings_an_operator_types(self, text, expected):
        assert RiskLevel.parse(text) is expected

    def test_an_unknown_level_is_refused(self):
        with pytest.raises(ValueError):
            RiskLevel.parse("catastrophic")

    def test_allows_compares_by_ordinal(self):
        assert RiskLevel.SYSTEM_MODIFICATION.allows(RiskLevel.SAFE)
        assert not RiskLevel.SAFE.allows(RiskLevel.MANIPULATION)

    def test_the_label_is_readable(self):
        assert RiskLevel.SYSTEM_MODIFICATION.label == "System Modification"


class TestRiskPolicy:
    def test_an_operation_above_the_ceiling_is_refused(self):
        context = ExecutionContext(max_risk=RiskLevel.OBSERVABILITY)
        with pytest.raises(RiskPolicyError) as info:
            context.check_risk("configuration.restore", RiskLevel.SYSTEM_MODIFICATION)
        assert "configuration.restore" in str(info.value)

    def test_an_operation_at_the_ceiling_is_allowed(self):
        context = ExecutionContext(max_risk=RiskLevel.OBSERVABILITY)
        context.check_risk("security.portscan", RiskLevel.OBSERVABILITY)

    def test_the_ceiling_never_exceeds_the_configuration(self):
        config = NetForgeConfig(max_risk=RiskLevel.SAFE)
        context = ExecutionContext(config=config, max_risk=RiskLevel.SYSTEM_MODIFICATION)
        assert context.max_risk == RiskLevel.SAFE


class TestConfiguration:
    def test_the_environment_overrides_the_defaults(self):
        config = NetForgeConfig.from_env({"NETFORGE_DEFAULT_TIMEOUT": "12.5"})
        assert config.default_timeout == 12.5

    def test_the_environment_can_lower_the_risk_ceiling(self):
        config = NetForgeConfig.from_env({"NETFORGE_MAX_RISK": "2"})
        assert config.max_risk == RiskLevel.OBSERVABILITY

    def test_a_non_numeric_timeout_is_refused(self):
        with pytest.raises(ConfigurationError):
            NetForgeConfig.from_env({"NETFORGE_DEFAULT_TIMEOUT": "soon"})

    def test_a_boolean_is_parsed(self):
        config = NetForgeConfig.from_env({"NETFORGE_VERIFY_TLS": "no"})
        assert config.verify_tls is False

    def test_an_unknown_log_level_is_refused(self):
        with pytest.raises(ValueError):
            NetForgeConfig(log_level="chatty")

    def test_the_environment_wins_over_the_file(self, tmp_path):
        path = tmp_path / "netforge.json"
        path.write_text('{"default_timeout": 5.0}', encoding="utf-8")
        config = NetForgeConfig.load(path, env={"NETFORGE_DEFAULT_TIMEOUT": "9.0"})
        assert config.default_timeout == 9.0

    def test_a_missing_file_is_reported(self, tmp_path):
        with pytest.raises(ConfigurationError, match="not found"):
            NetForgeConfig.from_file(tmp_path / "absent.json")
