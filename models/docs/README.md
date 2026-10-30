# `netforge.models`

Everything that crosses a boundary in NetForge is a Pydantic model: the
requests an operation accepts, the responses it returns, the metadata of an
execution, the risk level an operation is declared at, and the capability
category it belongs to.

Importing from `netforge.models` is the supported way to reach them.

---

## The base models

`NetForgeModel` is the base of every request and response. It forbids
unknown fields, so a typo in a request is an error rather than a silently
ignored key.

It does **not** strip whitespace, because a request that carries a
configuration or a certificate must arrive byte for byte.

```python
class NetForgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

`RequestModel` and `ResponseModel` specialise it for the two directions.
`ResponseModel` adds the fields every response carries:

| Field | Meaning |
|---|---|
| `operation` | the name of the operation that produced it |
| `risk_level` | the risk level it was declared at |
| `duration_ms` | how long it took |
| `warnings` | anything the operation wants to flag |

---

## The risk model

`RiskLevel` is an `IntEnum`, because risk comparison is ordinal — "is this
at or below the ceiling?" — and an integer comparison says that most
clearly.

| Level | Value | Means |
|---|---|---|
| `RiskLevel.SAFE` | 1 | it only reads |
| `RiskLevel.OBSERVABILITY` | 2 | it is visible to the other side |
| `RiskLevel.MANIPULATION` | 3 | it changes something |
| `RiskLevel.SYSTEM_MODIFICATION` | 4 | it changes the machine NetForge runs on |

`RISK_LEVEL_ORDER` is the immutable sequence in ascending order, for the
places that need to iterate over the levels.

The ceiling is enforced in three places, and all three matter: the
configuration (`NETFORGE_MAX_RISK`, the machine's policy), the context
(the caller's policy) and the operation (the declaration). The effective
ceiling is the stricter of the first two; the third is always checked.

---

## The levels of a scan

`Aggressiveness` is how hard a scan pushes, and how much of a trace it
leaves behind. A scan is loud: every probe is a packet the target, or
the equipment in front of it, can see, and a scan that comes in a hurry
is easy to tell from the traffic around it.

| Level | What it does |
|---|---|
| `paranoid` | one probe at a time, a second between them, and a long patience |
| `stealth` | one probe at a time, half a second between them, and no handshake when nmap and root allow it |
| `polite` | a few probes at a time, and a tenth of a second between them |
| `normal` | the default: the speed the operation had before the levels existed |
| `aggressive` | as many probes at once as the target will take, and no waiting |

The level is a `ScanProfile`: how many probes run at once, how patient
each one is, and how long the scan waits between them. A profile that
leaves something out means *the operation keeps its own default* — so
the normal level changes nothing at all, and a caller who wants a
particular timeout can still give one.

```python
from netforge.models.scanning import Aggressiveness, the_profile

profile = the_profile(Aggressiveness.PARANOID)
profile.the_concurrency(32)   # 1
profile.the_timeout(2.0)      # 10.0
profile.delay                 # 1.0
```

`ScanEngine` is the implementation that runs the scan: `native`, which
is NetForge itself on the standard library alone, or `nmap`, when it is
installed.

---

## The capability categories

`CapabilityCategory` is the kind of capability an operation provides. It
is what groups the catalogue, and it is one of the ten categories in the
table on the [documentation index](../../docs/README.md#the-capability-packages).

```text
CONNECTIVITY   discovery     DNS           protocols     CAPTURE
ANALYSIS       configuration SECURITY      manipulation  EMULATION
```

---

## The result envelope

`OperationResult` pairs a typed response with the metadata of the
execution that produced it.

| Field | Meaning |
|---|---|
| `data` | the response model itself, typed |
| `meta` | an `OperationMeta` |

`OperationMeta` records what happened:

| Field | Meaning |
|---|---|
| `operation` | the name of the operation |
| `category` | its category, as a string |
| `risk_level` | the level it ran at |
| `started_at`, `finished_at` | timezone-aware UTC timestamps |
| `duration_ms` | how long it took |
| `implementation` | `"python"`, or the language of a native implementation |
| `warnings` | anything the operation flagged |
| `metadata` | free-form extras |

`utcnow()` returns the current time as a timezone-aware UTC timestamp, and
is the function every model uses for its timestamps.

---

## Using it

```python
from netforge.models import CapabilityCategory, RequestModel, ResponseModel, RiskLevel


class PingRequest(RequestModel):
    host: str
    count: int = 4


class PingResponse(ResponseModel):
    reachable: bool
    avg_ms: float | None = None
```

An operation declares its models as class attributes, and the registry
publishes their JSON Schema. The REST adapter validates against it, and
the MCP and LlamaIndex adapters derive their tool signatures from it.

---

## The public API

```text
class CapabilityCategory(str, Enum)
class NetForgeModel(BaseModel)                  extra="forbid"
class OperationMeta                            (*, operation, category, risk_level,
                                                started_at, finished_at, duration_ms,
                                                implementation='python', warnings=[],
                                                metadata={})
class OperationResult(ResultT, Generic)        (*, data, meta)
class RequestModel(NetForgeModel)
class ResponseModel(NetForgeModel)             (*, operation='', risk_level='',
                                                duration_ms=0.0, warnings=[])
class RiskLevel(IntEnum)                       SAFE=1, OBSERVABILITY=2,
                                               MANIPULATION=3, SYSTEM_MODIFICATION=4

RISK_LEVEL_ORDER = (SAFE, OBSERVABILITY, MANIPULATION, SYSTEM_MODIFICATION)
utcnow() -> datetime
```

---

## Notes

* The models are the only place a schema is defined. An adapter never
  invents its own.
* `extra="forbid"` is deliberate. A request that arrives with an unknown
  key is a caller bug, and it is caught at the boundary rather than
  silently ignored.
* See also: [the architecture](../../docs/ARCHITECTURE.md#the-risk-model),
  [core.md](../../core/docs/README.md), [registry.md](../../registry/docs/README.md).
