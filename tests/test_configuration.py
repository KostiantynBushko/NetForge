"""The configuration capability: the offline operations are pure functions."""

from __future__ import annotations

from netforge.configuration.manager import diff_configurations, validate_configuration

GOOD = """[interface]
name = eth0
address = 10.0.0.1/24
"""

MESSY = """[interface]
name = eth0
address = 10.0.0.1/24
mtu = 1500
name = eth1
description = "an unbalanced quote
trailing = value
"""


class TestValidation:
    def test_a_clean_configuration_has_no_problems(self):
        assert validate_configuration(GOOD) == []

    def test_a_duplicate_key_is_reported(self):
        issues = validate_configuration(MESSY)
        assert any("appears more than once" in issue.message for issue in issues)

    def test_an_unbalanced_quote_is_an_error(self):
        issues = validate_configuration(MESSY)
        errors = [issue for issue in issues if issue.severity == "error"]
        assert any("unbalanced quote" in issue.message for issue in errors)

    def test_trailing_whitespace_is_reported_with_its_line(self):
        issues = validate_configuration("a = 1   \n")
        trailing = [issue for issue in issues if "whitespace" in issue.message]
        assert trailing
        assert trailing[0].line == 1

    def test_a_tab_is_reported(self):
        issues = validate_configuration("a\t= 1\n")
        assert any("tab" in issue.message for issue in issues)

    def test_a_missing_final_newline_is_reported(self):
        issues = validate_configuration("a = 1")
        assert any("does not end with a newline" in issue.message for issue in issues)

    def test_a_comment_is_ignored(self):
        assert validate_configuration("# a = 1\n! b = 2\n") == []

    def test_an_empty_configuration_is_fine(self):
        assert validate_configuration("") == []


class TestDiff:
    def test_identical_configurations_have_no_diff(self):
        assert diff_configurations(GOOD, GOOD) == []

    def test_a_change_is_reported(self):
        diff = diff_configurations(GOOD, GOOD.replace("10.0.0.1", "10.0.0.2"))
        assert diff
        assert any(line.startswith("+") for line in diff)
        assert any(line.startswith("-") for line in diff)

    def test_the_diff_names_both_sides(self):
        diff = diff_configurations(GOOD, GOOD + "mtu = 1500\n")
        assert any("current" in line for line in diff)
        assert any("candidate" in line for line in diff)


class TestConfigurationOperations:
    async def test_the_validate_operation_counts_the_problems(self, registry):
        operation = registry.create("configuration.validate")
        response = await operation.run_request({"content": MESSY})
        assert response.error_count >= 1
        assert response.valid is False

    async def test_the_validate_operation_accepts_a_clean_configuration(self, registry):
        operation = registry.create("configuration.validate")
        response = await operation.run_request({"content": GOOD})
        assert response.valid is True
        assert response.issues == []

    async def test_the_diff_operation_counts_the_changed_lines(self, registry):
        operation = registry.create("configuration.diff")
        response = await operation.run_request(
            {"current": GOOD, "candidate": GOOD.replace("10.0.0.1", "10.0.0.2")}
        )
        assert response.identical is False
        assert response.changed_lines == 2

    async def test_the_restore_operation_is_declared_at_the_top_level(self, registry):
        descriptor = registry.get("configuration.restore")
        assert descriptor.risk_level == 4
        assert descriptor.requires_privilege is False

    async def test_the_backup_operation_reports_a_transport_failure(self, registry):
        operation = registry.create("configuration.backup")
        response = await operation.run_request(
            {"host": "127.0.0.1", "path": "/etc/config", "port": 1}
        )
        assert response.exit_code == -1
        assert response.warnings
