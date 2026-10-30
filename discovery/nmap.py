"""The nmap engine.

nmap knows more about ports and services than any implementation could
learn in an afternoon: it probes the open ports with the service probes
of its own database and reports the product and the version behind them.
It also knows how to be quiet about it.

The engine is optional.  nmap is a system tool, not a Python package,
and the operations that can use it fall back to their own implementation
when it is not installed -- so NetForge stays installable, and usable,
with nothing but Python.

The two functions here are pure: the command line is built from the
request, and the XML that nmap writes is read back into a result.  That
is what makes the engine testable without nmap, and without a network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from netforge.models.scanning import Aggressiveness

__all__ = [
    "NmapResult",
    "parse_nmap_xml",
    "the_arguments",
    "the_warnings",
]

#: The nmap timing template of every level.  They are the same numbers
#: nmap uses: paranoid, sneaky, polite, normal and aggressive.
TEMPLATES: dict[Aggressiveness, int] = {
    Aggressiveness.PARANOID: 0,
    Aggressiveness.STEALTH: 1,
    Aggressiveness.POLITE: 2,
    Aggressiveness.NORMAL: 3,
    Aggressiveness.AGGRESSIVE: 4,
}


@dataclass(frozen=True, slots=True)
class NmapResult:
    """What nmap found."""

    ports: list[dict[str, Any]] = field(default_factory=list)
    open_ports: list[int] = field(default_factory=list)
    closed_ports: list[int] = field(default_factory=list)
    filtered_ports: list[int] = field(default_factory=list)
    scanned: int = 0
    warnings: list[str] = field(default_factory=list)

    def the_open(self) -> list[dict[str, Any]]:
        """The open ports, with the service on each of them."""
        return [port for port in self.ports if port.get("state") == "open"]


def the_warnings(level: Aggressiveness, root: bool) -> list[str]:
    """The remarks that go with the command line."""
    if level is Aggressiveness.STEALTH and not root:
        return [
            "a half-open scan needs root; the scan was a connect scan, which "
            "the target sees"
        ]
    return []


def the_arguments(
    *,
    host: str,
    ports: str | None,
    level: Aggressiveness,
    timeout: float,
    root: bool,
) -> list[str]:
    """The command line of nmap for a scan.

    The host is written after ``--``, so that a host whose name begins
    with a dash cannot become an option.
    """
    arguments = ["nmap"]

    # The kind of scan.  A half-open scan never completes the handshake,
    # so the target does not see a connection; it needs root.
    if level is Aggressiveness.STEALTH and root:
        arguments.append("-sS")
    else:
        arguments.append("-sT")

    # The service probes: what is listening on the open port.
    arguments.append("-sV")
    # The host is taken as it is; nmap should not ping it first.
    arguments.append("-Pn")
    # No name resolution: it is faster, and it asks no one.
    arguments.append("-n")
    # The timing template of the level.
    arguments.append(f"-T{TEMPLATES[level]}")
    # The result, as XML, on the standard output.
    arguments += ["-oX", "-"]

    if ports:
        arguments += ["-p", ports]

    # nmap's timeout is for the whole host, not for one port.
    arguments += ["--host-timeout", f"{max(30, int(timeout * 4))}s"]

    arguments += ["--", host]
    return arguments


def parse_nmap_xml(text: str) -> NmapResult:
    """Read the XML that nmap writes.

    nmap writes one ``host`` element per host, and one ``port`` element
    per port inside it.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"the output of nmap is not valid XML: {exc}") from exc

    ports: list[dict[str, Any]] = []
    warnings: list[str] = []

    for host in root.findall("host"):
        status = host.find("status")
        if status is not None and status.get("state") == "down":
            warnings.append("nmap reports the host as down")
            continue

        for element in host.findall("ports/port"):
            number = element.get("portid")
            if number is None:
                continue
            state_element = element.find("state")
            state = state_element.get("state", "unknown") if state_element is not None else "unknown"
            service_element = element.find("service")
            name = service_element.get("name") if service_element is not None else None
            version = None
            if service_element is not None:
                parts = [
                    service_element.get("product"),
                    service_element.get("version"),
                    service_element.get("extrainfo"),
                ]
                version = " ".join(part for part in parts if part) or None
            ports.append(
                {
                    "port": int(number),
                    "state": state,
                    "latency_ms": None,
                    "service": name,
                    "version": version,
                    "protocol": element.get("protocol", "tcp"),
                }
            )

    ports.sort(key=lambda port: port["port"])
    open_ports = [port["port"] for port in ports if port["state"] == "open"]
    closed_ports = [port["port"] for port in ports if port["state"] == "closed"]
    filtered_ports = [port["port"] for port in ports if port["state"] == "filtered"]

    return NmapResult(
        ports=ports,
        open_ports=open_ports,
        closed_ports=closed_ports,
        filtered_ports=filtered_ports,
        scanned=len(ports),
        warnings=warnings,
    )


def is_root() -> bool:
    """Whether the process may open a raw socket."""
    return hasattr(os, "geteuid") and os.geteuid() == 0
