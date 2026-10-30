# `protocols.mqtt.topic.match`

> Match MQTT topics against wildcard filters.

**Risk:** Safe (level 1)  
**Category:** protocols  
**Tags:** `filter`, `mqtt`, `subscription`, `topic`  
**Implementation:** `netforge.protocols.mqtt:MqttTopicOperation`

---

## What it does

Tests a set of MQTT topics against a set of topic filters and reports which filter matched which topic. It follows the wildcard rules of the MQTT specification exactly, including the rule that '#' must be the last level.

## The request

| Parameter | Type | Default | What it is |
|---|---|---|---|
| `filters` | list of string | — | **Required.** The topic filters to test. (at least 1 items) |
| `topics` | list of string | — | **Required.** The topics to test them against. (at least 1 items) |

## The response

| Field | Type | What it is |
|---|---|---|
| `operation` | string | Name of the operation that produced this response. |
| `risk_level` | string | Risk level the operation was declared at. |
| `duration_ms` | number | Wall-clock duration of the operation. |
| `warnings` | list of string | Non-fatal remarks about the result. |
| `matches` | list of object | The topics that matched a filter. |
| `unmatched_topics` | list of string | The topics that matched no filter. |
| `invalid_filters` | list of string | The filters that are not valid. |

## Using it

### From the command line

```console
$ netforge run protocols.mqtt.topic.match --filters [] --topics []
```

The values above are placeholders.  The request may also be given as a JSON object, which the flags are laid over:

```console
$ netforge run protocols.mqtt.topic.match --request '{"filters": [], "topics": []}'
```

### From Python

```python
from netforge.core.bootstrap import builtin_registry

registry = builtin_registry()
operation = registry.create("protocols.mqtt.topic.match")
result = await operation.run(filters=..., topics=...)
```

## How it works

MQTT.

The MQTT client itself needs a broker library, and ``paho-mqtt`` is the
optional extra that provides one.  What is implemented *here* is the part
that has to be exactly right and is worth having on its own: the topic
filter.

MQTT topics are matched with two wildcards -- ``+`` matches one level and
``#`` matches the rest of the topic -- and the rules for them are subtle
enough that getting them wrong silently loses messages.  The matcher is a
pure function over strings, so it can be tested exhaustively.

## See also

* [the `protocols` package](README.md) — every operation it publishes
* [the architecture](../../docs/ARCHITECTURE.md) — how the pieces fit together
* [the documentation index](../../docs/README.md)
