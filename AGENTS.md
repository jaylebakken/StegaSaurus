# Stegosaurus Audio Instructions

This is a local experimental audio-watermarking repository with no remote.

Ground rules:

- Keep the file structure minimal and nested.
- Maintain one concise `README.md` under 400 lines that describes the audio pilot and its layout.
- Begin every Python module with a verbose module description and give every method a docstring.
- Preserve the distinction between audio encoding, statistical detection, and future attribution decoding.
- Do not claim compression, DSP, or perceptual robustness beyond named measured evaluations.
- For routine validation, run only the current application suite: `python -m pytest -q src/stegosaurus/audio/tests/application`.
- Run `src/stegosaurus/audio/tests/experiment_regressions` only when the user explicitly requests archived experiment reproducibility validation or when a change directly affects an archived experiment contract.

## Application Code Style

- Keep production modules focused and under 250 lines. Split by one research concept at a time, then retain the established public import path as a small documented facade with explicit `__all__` exports.
- Follow the existing application boundaries: pilot code separates PCM/WAV types, transforms, keyed pairs, frame scoring, and workflow; schema code separates records from policy; transport separates models, framing, interleaving, and channel recovery; attacks separate codecs, PCM transforms, recipe models, and profiles.
- Open modules with a teaching-oriented docstring: background and intent, a short pseudocode or toy flow when useful, and any scope boundary that prevents an unsupported robustness or production claim.
- Use `from __future__ import annotations`, complete type hints, descriptive names, and small single-purpose functions. Prefer immutable result/config records as `@dataclass(frozen=True, slots=True)` when they represent declared inputs or observed outputs.
- Keep public orchestration methods readable as process maps. Put low-level math, serialization, or transform details in focused helpers rather than growing a facade into a monolith.
- Make deterministic inputs explicit: secret material, epoch, configuration, seeds, transform parameters, and replay recipes must be passed or recorded rather than inferred from ambient state.
- Validate public inputs at module boundaries with clear `TypeError` or `ValueError` messages. Preserve uncertainty as an explicit value (for example carrier-bit erasures) instead of silently coercing it into a confident decision.
- Prefer recorded diagnostics and structured result objects over printing, implicit global state, or broad exception suppression. Benchmark transformations may capture concise per-attack failures, but core encode/decode paths should surface invalid inputs.
- Keep current application tests in `tests/application`; add or update an archived regression only when the corresponding experiment contract intentionally changes.
