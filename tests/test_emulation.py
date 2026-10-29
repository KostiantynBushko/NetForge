"""The emulation capability: the profiles are data, and the command is a string."""

from __future__ import annotations

from netforge.core.context import ExecutionContext
from netforge.emulation.netem import build_netem_command, parse_qdisc
from netforge.emulation.profile import PROFILE_PRESETS, NetworkProfile, grade_profile


class TestProfiles:
    def test_the_four_presets_of_the_specification_are_there(self):
        assert "bad_wifi" in PROFILE_PRESETS
        assert "cellular" in PROFILE_PRESETS
        assert "satellite" in PROFILE_PRESETS
        assert "constrained_iot" in PROFILE_PRESETS

    def test_a_preset_is_internally_consistent(self):
        for name, profile in PROFILE_PRESETS.items():
            assert grade_profile(profile) == [], f"{name} is inconsistent"

    def test_the_severity_is_derived_from_the_conditions(self):
        assert NetworkProfile("mild", latency_ms=10).severity == "mild"
        assert NetworkProfile("moderate", latency_ms=200).severity == "moderate"
        assert NetworkProfile("severe", loss_percent=20).severity == "severe"

    def test_a_negative_latency_is_refused(self):
        assert grade_profile(NetworkProfile("bad", latency_ms=-1))

    def test_a_loss_above_a_hundred_is_refused(self):
        assert grade_profile(NetworkProfile("bad", loss_percent=101))

    def test_a_jitter_above_the_latency_is_refused(self):
        assert grade_profile(NetworkProfile("bad", latency_ms=10, jitter_ms=50))

    def test_a_zero_bandwidth_is_refused(self):
        assert grade_profile(NetworkProfile("bad", bandwidth_mbps=0))


class TestNetemCommand:
    def test_the_delay_and_the_loss_are_in_the_command(self):
        command = build_netem_command(
            "eth0", NetworkProfile("custom", latency_ms=100, jitter_ms=10, loss_percent=2)
        )
        assert command[:5] == ["tc", "qdisc", "replace", "dev", "eth0"]
        assert any("delay 100.000ms 10.000ms" in part for part in command)
        assert any(part.startswith("loss ") for part in command)

    def test_the_bandwidth_is_in_the_command(self):
        command = build_netem_command(
            "eth0", NetworkProfile("custom", latency_ms=10, bandwidth_mbps=8)
        )
        assert "rate" in command
        assert "8.000mbit" in command

    def test_a_profile_without_jitter_has_a_single_delay(self):
        command = build_netem_command("eth0", NetworkProfile("custom", latency_ms=50))
        delays = [part for part in command if part.startswith("delay")]
        assert delays == ["delay 50.000ms"]


class TestQdiscParsing:
    def test_the_queue_disciplines_are_parsed(self):
        entries = parse_qdisc(
            "qdisc noqueue 0: root refcnt 2\n"
            "qdisc netem 8001: root refcnt 2 limit 1000 delay 100ms\n"
        )
        assert len(entries) == 2
        assert entries[1]["kind"] == "netem"


class TestEmulationOperations:
    async def test_the_profile_operation_lists_the_presets(self, registry):
        operation = registry.create("emulation.profile")
        response = await operation.run_request({"name": "satellite"})
        assert response.profile["name"] == "satellite"
        assert response.profile["latency_ms"] == 650.0
        assert response.problems == []

    async def test_the_profile_operation_reports_an_unknown_preset(self, registry):
        operation = registry.create("emulation.profile")
        response = await operation.run_request({"name": "dial-up"})
        assert response.profile == {}
        assert response.problems

    async def test_the_netem_operation_dry_runs(self, registry):
        operation = registry.create("emulation.netem")
        response = await operation.run_request(
            {"interface": "eth0", "profile": "bad_wifi", "dry_run": True}
        )
        assert response.applied is False
        assert response.command[0] == "tc"
        assert response.profile["name"] == "bad_wifi"

    async def test_the_netem_operation_applies_through_the_runner(self, registry, fake_runner):
        from tests.conftest import result

        fake_runner.default = result("")
        operation = registry.create("emulation.netem")
        context = ExecutionContext(command_runner=fake_runner)

        response = await operation.run_request(
            {"interface": "eth0", "profile": "cellular"}, context
        )
        assert response.applied is True
        assert fake_runner.calls[0][0] == "tc"

    async def test_the_netem_operation_reports_a_failure(self, registry, fake_runner):
        from tests.conftest import result

        fake_runner.default = result("", returncode=1, stderr="permission denied")
        operation = registry.create("emulation.netem")
        context = ExecutionContext(command_runner=fake_runner)

        response = await operation.run_request(
            {"interface": "eth0", "profile": "cellular"}, context
        )
        assert response.applied is False
        assert response.warnings
