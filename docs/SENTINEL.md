# Testing the sentinel with two machines

The sentinel watches; `discovery.service.enumerate` probes. This guide
runs both, on **two machines on the same local network**, and shows the
sentinel reporting the scan.

It is the whole loop in five minutes:

```
machine A (the watcher)          machine B (the scanner)
------------------------         ------------------------
sentinel.network.monitor  <----   discovery.service.enumerate
        |                                    |
        |--------- the alert ----------------|
```

---

## What you need

| | |
|---|---|
| Two machines on the same local network | a laptop and a desktop; two virtual machines on a host-only network will do |
| NetForge on the watcher | `pip install netforge` — or run it from a checkout |
| NetForge on the scanner | the same |
| Root on the watcher | the monitor opens a raw socket |

The privilege on the watcher can be given to the capture tool instead of
to the whole run:

```bash
sudo setcap cap_net_raw,cap_net_admin=ep "$(command -v tcpdump)"
```

---

## 1. Note the two addresses

On **machine A** (the watcher):

```bash
ip -br addr | grep -v DOWN
```

On **machine B** (the scanner):

```bash
ip -br addr | grep -v DOWN
```

Write down the address of machine A — the watcher — and the address of
machine B — the scanner. The commands below use `192.168.0.10` for A and
`192.168.0.20` for B; use your own.

---

## 2. Start the watcher on machine A

```bash
sudo netforge run sentinel.network.monitor \
  --interface wlo1 \
  --duration 300 \
  --output ~/sentinel.pcap \
  --sink ~/alerts.jsonl
```

| Flag | Why |
|---|---|
| `--interface wlo1` | the interface to watch; `any` watches all of them |
| `--duration 300` | how long to watch, in seconds |
| `--output ~/sentinel.pcap` | the capture to write, so the same traffic can be read again afterwards |
| `--sink ~/alerts.jsonl` | where the alerts are appended, one JSON object per line |

The watcher prints nothing while it runs — it is watching. Leave it
running.

---

## 3. Scan from machine B

On **machine B**, against the address of machine A:

```bash
netforge run discovery.service.enumerate \
  --host 192.168.0.10 \
  --ports 1-1000
```

That is a connect scan: it opens a connection to every port, and closes
it again, saying nothing on any of them. The native scanner of
NetForge does exactly that, and it is the signature
`sentinel.network.monitor` is looking for.

To try the other engines, run the same command with:

```bash
# nmap, which names the product and the version behind each open port
netforge run discovery.service.enumerate --host 192.168.0.10 --engine nmap

# nmap without root: a half-open scan that never completes the handshake
netforge run discovery.service.enumerate --host 192.168.0.10 \
  --engine nmap --aggressiveness stealth
```

And to try the five levels of quietness, which change how fast the scan
runs and how visible it is:

```bash
netforge run discovery.service.enumerate --host 192.168.0.10 --aggressiveness polite
```

`paranoid` spreads the probes over seconds, `aggressive` packs them into
a burst. **The quieter the scan, the longer the window the sentinel
needs** — see [The window and the levels](#the-window-and-the-levels).

---

## 4. Read the alerts

On **machine A**, while the watcher is still running, or after it has
stopped:

```bash
netforge run sentinel.alert.list --path ~/alerts.jsonl
```

You should see something of the shape:

```json
{
  "alerts": [
    {
      "rule": "port-sweep",
      "severity": "high",
      "summary": "One address touched many ports of another in a short time.",
      "source": "192.168.0.20",
      "destination": "192.168.0.10",
      "timestamp": 1700000123.4,
      "evidence": {
        "distinct_ports": 1000,
        "ports": [1, 2, 3, "..."],
        "attempts": 1000,
        "window_seconds": 12.4
      }
    }
  ],
  "total": 1,
  "by_severity": { "high": 1 },
  "by_rule": { "port-sweep": 1 }
}
```

The `source` is the scanner and the `destination` is the machine that
was scanned — so the alert says who did it, and to whom.

Filter it down when there is a lot of it:

```bash
netforge run sentinel.alert.list --path ~/alerts.jsonl --severity high
netforge run sentinel.alert.list --path ~/alerts.jsonl --rule port-sweep
```

---

## 5. Read the capture afterwards

The monitor is a convenience; the analyser is the truth. The capture it
wrote can be read again, as many times as you like, with no privilege
and no monitor running:

```bash
netforge run sentinel.network.analyse --path ~/sentinel.pcap
```

The same alerts come back, computed from the file rather than from the
live traffic — which is what makes them auditable.

---

## 6. The log half

The log half needs no capture and no privilege, because the machine
being scanned usually wrote the scan down itself.

On **machine A**, with a firewall that logs:

```bash
sudo netforge run sentinel.log.analyse --path /var/log/ufw.log
```

A burst of rejected connections towards many ports from one address
shows up as `firewall-port-sweep`. With the authentication log:

```bash
netforge run sentinel.log.analyse --path /var/log/auth.log
```

A password spray shows up as `ssh-failure-burst`.

---

## The window and the levels

The rules look at a **window**, and the window is the parameter that
decides what the sentinel can see.

```bash
netforge run sentinel.network.analyse --path ~/sentinel.pcap --window-seconds 300
```

| The scan | How long it lasts | The window it needs |
|---|---|---|
| `--aggressiveness aggressive` | a second or two | 10 seconds is plenty |
| `--aggressiveness normal` | a few seconds | 30 seconds |
| `--aggressiveness polite` | tens of seconds | a minute or two |
| `--aggressiveness paranoid` | minutes | **the whole scan** |

A `paranoid` scan spreads one probe per second, so a ten-second window
sees ten ports and a rule that wants ten will fire — but a rule that
wants fifty will not. The window has to be chosen against the quietest
scan you intend to catch.

The thresholds are parameters too:

```bash
netforge run sentinel.network.analyse --path ~/sentinel.pcap \
  --distinct-ports 5 --window-seconds 300
```

---

## If nothing is reported

| The cause | What to do |
|---|---|
| the watcher watched the wrong interface | check `ip -br addr`, and watch the one that carries the network |
| the scan was too quiet for the window | raise `--window-seconds`, or lower `--distinct-ports` |
| the scan was too quick for the interval | the rules run once a second while the monitor watches; a scan that lasts less than that may be missed — use `--aggressiveness polite` to make it last |
| the traffic never reached the machine | check the firewall between the two machines |
| the watcher had no privilege | `sudo`, or `setcap` on tcpdump |
| the scan was made from the watcher itself | the sentinel sees its own traffic; run the scan from the other machine |

---

## What to look at afterwards

```bash
# what the machine was asked for
netforge run sentinel.alert.list --path ~/alerts.jsonl

# the same traffic, read from the file
netforge run sentinel.network.analyse --path ~/sentinel.pcap

# the scan from the other side, for comparison
netforge run discovery.service.enumerate --host 192.168.0.10 --ports 1-1000
```

The last one is the scan itself, from the scanner's point of view. The
first two are the same event, from the watcher's — which is the point
of the exercise.
