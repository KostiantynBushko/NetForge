"""Host discovery.

Discovery answers "what is out there?".  It covers ping, ping sweeps,
traceroute, ARP and route tables, and service discovery.

The parsers are separated from the operations on purpose.  ``/proc/net/arp``
and ``/proc/net/route`` are plain text with a documented format, and their
parsers are pure functions over text -- so they can be tested against a
captured sample without a Linux kernel, and without root.
"""

from __future__ import annotations

from netforge.discovery.arp import ArpEntry, ArpTableOperation, parse_arp_table
from netforge.discovery.ping import PingOperation, PingResult
from netforge.discovery.route import RouteEntry, RouteTableOperation, parse_route_table
from netforge.discovery.service import ServiceDiscoveryOperation
from netforge.discovery.sweep import PingSweepOperation
from netforge.discovery.traceroute import TracerouteOperation

__all__ = [
    "ArpEntry",
    "ArpTableOperation",
    "parse_route_table",
    "PingOperation",
    "PingResult",
    "PingSweepOperation",
    "RouteEntry",
    "RouteTableOperation",
    "ServiceDiscoveryOperation",
    "TracerouteOperation",
    "parse_arp_table",
    "parse_route_table",
]
