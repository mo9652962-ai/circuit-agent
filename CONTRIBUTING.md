# Contributing to CircuitAgent

Thanks for considering a contribution. This repository is the open community layer
of CircuitAgent, and it has a deliberately narrow definition of "done" — see
[the correctness bar](#the-correctness-bar) below before you start.

---

## The most valuable contribution: a new circuit block

The block catalogue is the heart of the DSL. Every block is a pre-verified
sub-circuit that the deterministic mapper can emit, so a wrong pin number here
becomes a shorted board downstream.

**A block PR is only mergeable if it ships all five of these:**

1. **The block factory** in [`client/circuit_blocks.py`](client/circuit_blocks.py),
   named `block_<something>`, returning a `CircuitBlock`.
2. **Datasheet-sourced pin numbers.** State the datasheet revision in the PR
   description. Do not infer pin numbers from a reference design.
3. **LCSC part numbers** for every component, in `C#####` form, verified to exist
   in the LCSC catalogue (the `search_lcsc_parts` tool is the intended way to check).
4. **The KiCad footprint name** for every component, in `Library:Footprint` form.
5. **A unit test** in [`tests/test_circuit_blocks.py`](tests/test_circuit_blocks.py)
   exercising the block's specific electrical intent — not just that it constructs.

Then add the factory to `BLOCK_FACTORIES` in that test file and to the `__all__`
list in `client/circuit_blocks.py`. CI enforces the rest of the invariants for you:

- designators are unique within the block
- every component declares a package and an LCSC part number
- every net endpoint resolves to a component the block actually declares
- the block ties to `/GND` (blocks that are purely mechanical or in-line may be
  exempted explicitly — see `Fiducial_Marks` and `Reverse_Polarity_Protection`)

---

## Other welcome contributions

| Area | Where | Notes |
|:---|:---|:---|
| Supported MCU / chip pin rules | `client/chip_rules.py` | Needs a datasheet citation and a test in `tests/test_sensor_and_chip_rules.py` |
| New prompt intent tokens | `client/synthesizer.py` | Must not break the determinism test |
| DFX / IPC rule additions | `client/industrial_dfx.py` | Cite the standard (section number, not just the name) |
| Reference netlists | `examples/` | Must validate against `specs/netlist_schema.json` |
| Documentation | `README.md`, `README_EN.md` | Both languages must stay in sync — see below |

---

## The correctness bar

Three rules are non-negotiable, and CI enforces all three.

**1 · Determinism.** `synthesize_from_prompt` must be a pure function. The same
prompt must always produce byte-identical output. Do not introduce iteration over
an unordered set, a timestamp, a random value, or a network call into the mapping
path. `tests/test_circuit_blocks.py` asserts this.

**2 · Zero runtime dependencies.** `client/` uses the Python standard library only.
`pip install circuit-agent-client` must not pull in a single third-party package.
If you think you need a dependency, open an issue first — the answer is usually a
smaller implementation.

**3 · No silent drops.** Anything the mapper does not understand must be reported
back to the caller. Use the two-list convention:

- `unmatched` — the caller asked for something this DSL **cannot build yet**
  (e.g. `ethernet`, `relay`, `motor_driver`). This is actionable.
- `not_requested` — optional blocks the prompt simply did not mention. Informational.

Do not conflate the two. An agent consuming this library relies on `unmatched`
being a trustworthy capability signal.

---

## Development setup

```bash
git clone https://github.com/mo9652962-ai/circuit-agent.git
cd circuit-agent
pip install -e ".[dev]"

pytest tests/ -q     # full suite, should be all green
ruff check .         # lint, must be clean
```

The suite runs in well under a second and there is no network access in CI's test
job, so run it often.

---

## Keeping the two READMEs in sync

`README.md` (Chinese) and `README_EN.md` (English) are both first-class. When you
change one, change the other in the same PR. The things that drift most often and
matter most:

- the test-count badge
- the release-version badge
- the exposed tool / resource / prompt lists
- the roadmap checkboxes

If your PR changes any of those in the code, update both READMEs. A reviewer will
check.

---

## Pull request checklist

- [ ] `pytest tests/ -q` passes locally
- [ ] `ruff check .` is clean
- [ ] New behaviour has a test that would fail without the change
- [ ] Both `README.md` and `README_EN.md` updated if counts, tools or roadmap changed
- [ ] No new runtime dependency added to `client/`
- [ ] No secrets, credentials, personal paths or private data in the diff

---

## Reporting bugs

Open an issue with:

- the exact prompt or code that reproduces it
- what you expected versus what you got
- your Python version and OS

For a block-level bug (wrong pin, wrong LCSC number, wrong footprint), please cite
the datasheet section that contradicts the current definition — that makes the fix
a one-line review instead of a research task.

---

## License

By contributing you agree your work is released under the [MIT License](LICENSE).
