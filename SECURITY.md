# Security Policy

## Supported versions

Security fixes are applied to the latest release line. As this project is in alpha,
only the most recent minor version is supported.

| Version | Supported |
|:---|:---|
| 0.1.x (latest) | ✅ |
| older | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report privately via GitHub's
[Report a vulnerability](https://github.com/mo9652962-ai/circuit-agent/security/advisories/new)
form. If you cannot use that, open a normal issue that says only *"I have a security
report, please contact me"* — with no technical detail — and a maintainer will
follow up.

Please include:

- what the issue is and where (file, function, MCP tool, or endpoint)
- how to reproduce it, ideally with the smallest prompt or payload that triggers it
- the impact you believe it has
- your Python version and OS

You can expect an acknowledgement within a few days. Please allow a reasonable
window for a fix to be released before publishing details.

## Scope

### In scope

| Area | Example |
|:---|:---|
| Netlist / prompt injection | A crafted prompt that escapes the deterministic mapper and produces an unsafe netlist |
| Denial of service | A prompt or netlist that causes unbounded CPU, memory, or recursion |
| Dependency confusion | Anything that would make `pip install circuit-agent-client` pull unintended code |
| Supply chain | Compromise of the publish workflow, release artefacts, or attestations |
| Data leakage | Any path where local files, environment variables, or credentials could be exfiltrated through a tool call |

### Out of scope

- **Outputs of the synthesiser being electrically wrong.** A generated netlist is a
  starting point, not a reviewed design. Validate before fabrication.
- **The `web/index.html` frontend having no backend in this repository.** That is
  intentional and documented in [`web/README.md`](web/README.md).
- **Third-party services.** The LCSC client queries an external public API; issues
  with that service are not in scope here, though a client-side flaw that mishandles
  its responses (for example, unvalidated data reaching the filesystem) is.
- **Findings that require an already-compromised machine.**

## Security design notes

A few properties are load-bearing and should be preserved by any change:

**Zero runtime dependencies.** `client/` imports from the Python standard library
only. This removes the entire transitive dependency attack surface. New third-party
dependencies will be rejected unless there is no reasonable alternative.

**No credentials.** This package requires no API keys, and none are stored. The LCSC
client is deliberately key-free. Do not add a code path that reads secrets.

**Network isolation by default.** Only `client/lcsc_client.py` performs network I/O,
and it degrades gracefully: hard timeouts, bounded retries with backoff, a 24-hour
disk cache, and a fallback that returns an empty list rather than raising. No other
module should gain network access.

**Untrusted input handling.** Prompts and netlists are treated as untrusted. The
synthesiser is a keyword mapper, not an evaluator — it never `eval`s, never executes
user input, and never writes to a path derived from a prompt.

**The Pro boundary.** This repository is the community layer. The Pro compiler
(multi-layer placement and routing, 3D enclosure generation, Senior EE DRC gate) is
developed separately and is not present here. Reports about Pro-only behaviour
cannot be actioned in this repository.

## A note on hardware safety

This tooling generates circuit designs that may be fabricated and powered. An
electrically incorrect design can damage equipment or cause injury. The DFX audit
engine checks manufacturing and protection rules — it is **not** a substitute for
engineering review. Always verify a generated design against the relevant
datasheets and applicable safety standards before fabrication or energisation.
