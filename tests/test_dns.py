"""The DNS capability: SPF and DMARC are parsed and evaluated offline."""

from __future__ import annotations

import pytest

from netforge.dns.diagnostics import (
    evaluate_spf,
    is_aligned,
    organisational_domain,
    parse_dmarc,
    parse_spf,
)

SPF_STRICT = "v=spf1 ip4:192.0.2.0/24 include:example.com -all"
SPF_RELAXED = "v=spf1 a mx ip4:198.51.100.7 ~all"
SPF_OPEN = "v=spf1 +all"
SPF_NONE = "v=spf1"

DMARC_NONE = "v=DMARC1; p=none; rua=mailto:dmarc@example.com; pct=100"
DMARC_REJECT = "v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s; rua=mailto:dmarc@example.com"
DMARC_BROKEN = "p=reject; rua=mailto:dmarc@example.com"


class TestSpfParsing:
    def test_the_version_is_read(self):
        assert parse_spf(SPF_STRICT).version == "spf1"

    def test_the_mechanisms_are_read(self):
        policy = parse_spf(SPF_STRICT)
        assert "ip4:192.0.2.0/24" in policy.mechanisms
        assert "include:example.com" in policy.mechanisms

    def test_the_all_mechanism_is_found(self):
        assert parse_spf(SPF_STRICT).all_mechanism == "-all"

    def test_a_quote_is_stripped(self):
        assert parse_spf('"v=spf1 -all"').version == "spf1"

    def test_an_empty_record_is_not_valid(self):
        assert parse_spf("").is_valid is False


class TestSpfEvaluation:
    def test_a_sender_inside_the_network_passes(self):
        result = evaluate_spf(SPF_STRICT, "192.0.2.55")
        assert result.result == "pass"
        assert result.matched_mechanism == "ip4:192.0.2.0/24"

    def test_a_sender_outside_the_network_fails(self):
        result = evaluate_spf(SPF_STRICT, "198.51.100.9")
        assert result.result == "fail"

    def test_a_relaxed_record_soft_fails(self):
        result = evaluate_spf(SPF_RELAXED, "203.0.113.1")
        assert result.result == "softfail"

    def test_an_open_record_passes_everybody(self):
        assert evaluate_spf(SPF_OPEN, "203.0.113.1").result == "pass"

    def test_a_missing_record_is_none(self):
        result = evaluate_spf("", "203.0.113.1")
        assert result.result == "none"
        assert "no SPF record" in result.explanation

    def test_a_record_without_a_version_tag_is_a_permanent_error(self):
        result = evaluate_spf("ip4:192.0.2.0/24 -all", "192.0.2.1")
        assert result.result == "permerror"

    def test_a_redirect_is_reported_rather_than_guessed(self):
        result = evaluate_spf("v=spf1 redirect=example.com", "203.0.113.1")
        assert result.result == "none"
        assert "redirects" in result.explanation


class TestDmarcParsing:
    def test_the_tags_are_read(self):
        policy = parse_dmarc(DMARC_NONE)
        assert policy.tags["rua"] == "mailto:dmarc@example.com"
        assert policy.policy == "none"

    def test_the_subdomain_policy_falls_back_to_the_policy(self):
        assert parse_dmarc(DMARC_NONE).subdomain_policy == "none"
        assert parse_dmarc(DMARC_REJECT).subdomain_policy == "reject"

    def test_the_alignment_is_read(self):
        policy = parse_dmarc(DMARC_REJECT)
        assert policy.alignment_adkim == "s"
        assert policy.alignment_aspf == "s"

    def test_the_percentage_is_clamped(self):
        assert parse_dmarc("v=DMARC1; p=none; pct=500").percentage == 100
        assert parse_dmarc("v=DMARC1; p=none; pct=-5").percentage == 0

    def test_a_record_without_a_version_tag_is_not_valid(self):
        assert parse_dmarc(DMARC_BROKEN).is_valid is False


class TestAlignment:
    def test_strict_alignment_requires_an_exact_match(self):
        assert is_aligned("example.com", "example.com", "s") is True
        assert is_aligned("mail.example.com", "example.com", "s") is False

    def test_relaxed_alignment_accepts_a_subdomain(self):
        assert is_aligned("mail.example.com", "example.com", "r") is True

    def test_the_organisational_domain_is_approximated(self):
        assert organisational_domain("mail.example.com") == "example.com"
        assert organisational_domain("example.com") == "example.com"


class TestDnsOperations:
    async def test_the_diagnostics_report_a_missing_spf(self, registry):
        operation = registry.create("dns.diagnostics")
        response = await operation.run_request({"domain": "example.com", "spf_record": "", "dmarc_record": ""})
        assert response.spf["valid"] is False
        assert any("no SPF record" in finding for finding in response.findings)

    async def test_the_diagnostics_report_a_missing_dmarc(self, registry):
        operation = registry.create("dns.diagnostics")
        response = await operation.run_request(
            {"domain": "example.com", "spf_record": SPF_STRICT, "dmarc_record": ""}
        )
        assert any("no DMARC record" in finding for finding in response.findings)

    async def test_the_diagnostics_score_a_good_posture(self, registry):
        operation = registry.create("dns.diagnostics")
        response = await operation.run_request(
            {"domain": "example.com", "spf_record": SPF_STRICT, "dmarc_record": DMARC_REJECT}
        )
        assert response.score == 100
        assert response.spf["valid"] is True
        assert response.dmarc["policy"] == "reject"

    async def test_the_diagnostics_warn_about_an_open_spf(self, registry):
        operation = registry.create("dns.diagnostics")
        response = await operation.run_request(
            {"domain": "example.com", "spf_record": SPF_OPEN, "dmarc_record": DMARC_NONE}
        )
        assert any("authorises every sender" in finding for finding in response.findings)
        assert response.score < 100
