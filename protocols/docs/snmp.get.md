# `protocols.snmp.get`

> Read a single OID from an SNMP agent.

**Risk:** Safe (level 1)  
**Category:** protocols  
**Tags:** `agent`, `get`, `oid`, `snmp`  
**Implementation:** `netforge.protocols.snmp:SnmpGetOperation`

---

## What it does

Performs an SNMP GET against an agent and returns the value of the OID. SNMPv1 and SNMPv2c are supported; SNMPv3 is not, and the operation says so rather than failing obscurely.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `host` | string | — | **Required.** The agent to query. (at least 1 character) |
| `oid` | string | — | **Required.** The OID to read. (at least 1 character) |
| `port` | integer | `161` | The agent's UDP port. (at least 1, at most 65535) |
| `community` | string | `"public"` | The community string. |
| `version` | integer | `1` | 0 for SNMPv1, 1 for SNMPv2c. (at least 0, at most 1) |
| `timeout` | number | `10.0` | Timeout in seconds. |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `host` | string | The agent that was queried. |
| `oid` | string | The OID that was read. |
| `error_status` | integer | The error status of the response. |
| `error_name` | string | The name of the error status. |
| `values` | list of object | The values that came back. |

## Using it

### From the command line

```console
$ netforge run protocols.snmp.get --request '{"host": "...", "oid": "..."}'
```

The request is a JSON object, and the values above are placeholders.

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("protocols.snmp.get")
result = await operation.run(host=..., oid=...)
```

## How it works

SNMP.

An SNMP v1/v2c GET, implemented directly on BER (ASN.1 distinguished
encoding rules).  SNMP needs no cryptography to be *read*, and the BER
encoding of a GET request is small enough to be worth having in the
framework rather than pulling in a library for it.

The message structure is::

    Message ::= SEQUENCE {
        version   INTEGER,          -- 0 for v1, 1 for v2c
        community OCTET STRING,
        pdu       GetRequest-PDU
    }

    GetRequest-PDU ::= [0] IMPLICIT SEQUENCE {
        request-id   INTEGER,
        error-status INTEGER,
        error-index  INTEGER,
        variable-bindings SEQUENCE OF VarBind
    }

    VarBind ::= SEQUENCE { name OBJECT IDENTIFIER, value ANY }

SNMP v3 is *not* implemented: it needs USM (user-based security), which
means key derivation and a message-digest algorithm.  The operation says so
rather than pretending otherwise.

## See also

* [the `protocols` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
