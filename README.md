# Stegosaurus

Stegosaurus is a local experimental audio-watermarking prototype. It embeds a secret-keyed statistical presence signal in mono PCM WAV audio and includes a bounded claimed-handle attribution API. Separately, the research track measures a non-oracle candidate-map decoder under explicitly named synthetic crop conditions; it is not yet an application API.

## Status

- **Encoding:** supported experimentally through a spectral STFT pilot.
- **Detection:** supported as `verified`, `inconclusive`, or `absent` with synchronization-offset correction.
- **Attribution:** v1 supports claimed-handle verification: it embeds a 4-byte opaque registry handle with 16 Reed--Solomon parity symbols, then verifies that specific claim using a registry-retained private carrier map.
- **Non-oracle research:** iteration 032 reconstructs a bounded duration-derived leading/trailing crop-mode bank without a retained map and recovers all 20 named fresh synthetic `250 ms` crop trials within its RS budget. It remains an experiment, not a v1 capability or general robustness claim.
- **Scope:** generated or licensed non-sensitive audio only. This project does not claim imperceptibility, universal robustness, or resistance to arbitrary resynthesis.

## Process Map

```text
PCM WAV
  -> SpectralAudioEncoder
  -> secret-keyed STFT magnitude-pair modulation
  -> watermarked PCM WAV

received WAV
  -> SpectralAudioDetector
  -> STFT, offset scan, and soft frame observations
  -> corrected statistical test
  -> verified | inconclusive | absent

v1 claimed attribution API
  -> issue opaque registry handle
  -> four-replica carrier embedding plus retained private frame map
  -> claimed-handle verification through Reed--Solomon recovery
  -> authenticated local provenance lookup

experimental non-oracle crop decoder
  -> expected WAV geometry plus received length loss
  -> trailing offset 0 and leading offsets around missing_samples / STFT hop
  -> separate local candidate maps, RS recovery, and bounded result selection
```

The encoder derives one expected bit per frame from a shared secret, daily epoch, and candidate source-frame index. It distributes that bit over secret frequency-bin pairs using plus-or-minus spreading chips while preserving each pair's combined magnitude energy. The detector regenerates the same bit, pair, and chip assignments; low-confidence observations become erasures instead of guesses.

## Reading Guide

The production code is intentionally decomposed so an unfamiliar reader can follow one idea at a time:

1. Start with `encoder.py` and `detector.py` for the directional application APIs.
2. Read `pilot.py` as the detector-pilot map, then follow its five modules: PCM/WAV types, STFT helpers, keyed pair selection, frame scoring, and workflow orchestration.
3. Read `schema.py` for keyed statistical detection and opaque-token policy; `schema_models.py` holds only data records and `schema_engine.py` holds the policy logic.
4. Read `transport.py` for attribution transport: sync framing, keyed interleaving, and Reed--Solomon recovery are separate modules.
5. Read `attacks.py` and `benchmark.py` last: they define measured transformations and replayable test recipes, not a general robustness guarantee.
6. Read `attribution.py` for the separate v1 claimed-handle verifier. It requires a registry-retained `AttributionRecord`; it does not discover an unknown handle from arbitrary audio.
7. Read `experiments/non_oracle_reconstruction/iteration_032_edge_mode_coarse_bank/` only after the application path. It documents a bounded, measured no-map crop decoder and its explicit scope limits.

The three rendered process maps, their application-code citations, and their scope boundaries are in `docs/process_diagrams.md`.
The v1 attribution decision, experiment-derived profile, and explicit limits are in `docs/attribution_v1.md`.

## Layout

```text
Stegosaurus/
|- GOALS.md                    # project goals, current assessment, and adversarial-evaluation workflow
|- README.md
|- pyproject.toml
`- src/stegosaurus/
   |- __init__.py
   `- audio/
      |- encoder.py      # WAV -> watermarked WAV public entry point
      |- detector.py     # WAV -> detection decision public entry point
      |- encoder.py / detector.py  # directional public application APIs
      |- pilot.py                  # facade for PCM, STFT, pairs, frames, workflow
      |- pilot_types.py            # PCM/WAV values and result records
      |- pilot_transform.py        # STFT bridge and signal metrics
      |- pilot_pairs.py            # keyed pair selection and modulation
      |- pilot_frames.py           # frame-local embed/extract scoring
      |- pilot_workflow.py         # offset scan and detector orchestration
      |- schema.py                 # facade for keyed detection/attribution policy
      |- schema_models.py          # schema configuration and decision records
      |- schema_engine.py          # keyed bits and statistical test logic
      |- ecc.py                    # Reed--Solomon validation boundary
      |- transport.py              # facade for attribution transport
      |- transport_*.py            # models, framing, interleaving, channel steps
      |- attacks.py                # facade for named evaluation transformations
      |- attack_*.py               # codec, PCM, entropy-model, and profile steps
      |- benchmark.py              # one-result-per-attack benchmark runner
      |- attribution.py            # v1 claimed-handle attribution facade
      |- attribution_*.py          # v1 records, registry, replicas, encoder, decoder
      |- demo_samples.py            # deterministic local covers for manual attribution testing
      |- demo_controller.py         # UI-independent local registry, transforms, and verification flow
      |- demo_app.py                # optional green Tkinter manual attribution lab
      |- experiments/
      |  |- transport_optimization/      # completed oracle-aligned iterations 001-011 and 013
      |  `- non_oracle_reconstruction/   # fresh numbering, beginning at iteration 001
      `- tests/
         |- application/             # current encoder, detector, schema, and benchmark APIs
         `- experiment_regressions/  # archived research-iteration reproducibility checks
```

## Install And Run

```powershell
python -m pip install -e ".[audio,test]"
```

```powershell
# Optional local manual lab: synthetic or PCM16 WAV source, local registry claim,
# named transformations, claimed-handle verification, and WAV export.
python -m stegosaurus.audio.demo_app
```

```powershell
# Fast current-application validation.
python -m pytest -q src/stegosaurus/audio/tests/application

# Archived experiment reproducibility checks.
python -m pytest -q src/stegosaurus/audio/tests/experiment_regressions

# Both suites (the default configured test paths).
python -m pytest -q
```

```python
from datetime import date

from stegosaurus.audio.detector import SpectralAudioDetector
from stegosaurus.audio.encoder import SpectralAudioEncoder
from stegosaurus.audio.pilot import read_pcm16_wav, write_pcm16_wav

secret = b"replace-with-private-key-material"
encoder = SpectralAudioEncoder(secret)
detector = SpectralAudioDetector(secret)
source = read_pcm16_wav("speech.wav")
embedding = encoder.encode(source, date.today())
write_pcm16_wav("speech-watermarked.wav", embedding.audio)
result = detector.detect(embedding.audio, date.today())
print(result.detection.status, result.detection.tail_probability)
```

```python
from stegosaurus.audio.attribution import (
    InMemoryAttributionRegistry,
    SpectralAttributionDecoder,
    SpectralAttributionEncoder,
)

registry = InMemoryAttributionRegistry(b"registry-authentication-secret")
entry, attribution = SpectralAttributionEncoder(secret).issue_and_encode(
    source,
    registry,
    b"local provenance record",
)
# issue_and_encode retries opaque handles until the clean encoded claim verifies,
# then retains the private record. Persist that record in a real registry.
verification = SpectralAttributionDecoder(secret).verify(
    attribution.audio,
    registry.record_for(entry.handle),  # A claimant supplies the asserted handle.
)
print(verification.status, verification.recovered_handle)
```

`PcmAudio` represents normalized mono samples. WAV input is downmixed to mono and must be 16-bit PCM; WAV output is deterministic PCM16. Install the `audio` extra for NumPy, SciPy, and the bundled FFmpeg path used by MP3 evaluation.

The v1 attribution record is private registry state, not public metadata. It is a usable claimed-handle verifier on the clean synthetic 30-second fixture exercised by the application test. It is not blind discovery, a persistent registry implementation, or a claim of robustness to codecs, DSP, crops, recorded audio, or arbitrary resynthesis.

### Key And Registry Boundary

The watermark master secret derives spectral pairs, local pilots, and the transport interleaver. The current attribution interleaver uses the domain-separated key `HMAC-SHA256(master_secret, b"stegosaurus-audio-v1|attribution")` and a deterministic HMAC-driven Fisher--Yates permutation for each codeword-bit length. The registry authentication secret is separate: it authenticates local handle/provenance records and must not expose or substitute for the watermark master secret. A deployment should keep watermark key access in an encoder/decoder service or KMS/HSM boundary; registry lookup supplies authenticated claim metadata and, for v1, the private retained map.

The experimental edge-mode decoder additionally assumes the expected original sample rate and sample count are available as authenticated claim/profile geometry. It uses received-length loss only to construct its bounded one-edge timing hypotheses; it does not receive the retained carrier-frame map or expected handle when selecting a hypothesis.

The Tkinter lab is a local display and manual-testing surface for that same claimed-handle flow. “Issue Calibrated Handle” retries opaque handles until its clean local claim verifies; “Encode Supplied Handle” intentionally exposes an exploratory fixed-handle path and reports its clean result. Its toggles apply named, fixed-parameter transformations to the displayed audio. They are test inputs, not a robustness claim.

## Evaluation Boundaries

The attack harness includes clean decoding, MP3 round trips, resampling, peak normalization, low-pass filtering, additive noise, trim/crop, concatenation, and time scaling. A benchmark records an extraction result or a concise transformation failure for every named attack.

`EntropicAttackProfile` adds bounded Monte Carlo variation over realistic processing chains: sample-rate round trips, bandwidth limits, synthetic room response, timing changes, leading trims, additive noise, gain normalization, and optional MP3 transcoding. Call `AudioPilotBenchmark.evaluate_entropic()` with a declared profile, trial count, and root seed. Each result retains its complete `EntropicAttackRecipe`, including every sampled parameter and child seed, so any trial can be reproduced exactly.

Before interpreting a resilience result, pre-register the profile bounds, corpus, control set, trial count, root seed, and success metric. Entropy supplies diverse but replayable test cases; it does not prove resistance to attacks outside those declared bounds.

```python
from stegosaurus.audio.attacks import EntropicAttackProfile
from stegosaurus.audio.benchmark import AudioPilotBenchmark
from stegosaurus.audio.pilot import SpectralAudioPilot

benchmark = AudioPilotBenchmark(SpectralAudioPilot(secret))
result = benchmark.evaluate_entropic(
    source,
    date.today(),
    EntropicAttackProfile(),
    trial_count=100,
    seed=20261008,
)
for trial in result.attacks:
    status = trial.extraction.detection.status if trial.extraction else trial.error
    print(trial.name, status, trial.recipe)
```

The current reproducible detector benchmark is recorded in `src/stegosaurus/audio/experiments/transport_optimization/iteration_001_detector_pilot/SUMMARY.md`; completed oracle-aligned transport experiments are archived in the `transport_optimization` track through iterations 001-011 and 013. Iteration 010 passes named MP3, resampling, normalization, noise, and trailing-crop conditions across ten synthetic variants; iteration 011 additionally recovers a bounded 250 ms leading crop through a sync-only oracle-map offset scan. Iteration 013 restores the named 4 kHz low-pass condition across the same synthetic fixture by restricting carriers to `500-3800 Hz`, but still relies on retained encoder source maps. Non-oracle iterations 004-008 establish a blind contrastive gap policy with 8/10 held-out recovery; iteration 009 finds that lengthening a fixed 8-byte token plan to add parity does not improve the bounded fixture. Iteration 010 instead holds the 20-byte protected codeword and 184-carrier plan fixed: a 6-byte registry handle plus 14 parity recovers 10/10 fresh clean synthetic variants, compared with 7/10 for 8-byte token plus 12 parity. Non-oracle iterations 011-015 establish crop alignment and deterministic center-phase reframing, but coarse synchronization and marginal RS damage still limit fresh-cover recovery. Iteration 018's paired same-input comparison finds the fixed median combiner produces no recovery transitions versus center-only, despite small RS-cost shifts, so it is frozen rather than further optimized. Iteration 019 keeps that 20-byte codeword and carrier plan fixed while comparing 6-byte/14-parity and 5-byte/15-parity registry allocations under fresh bounded crops: both recover 5/10 trailing crops, while the compact allocation recovers 5/10 leading crops versus 6/10 for the baseline. Fifteen parity symbols retain the same seven-symbol errors-only correction radius as fourteen, so the extra mixed error/erasure budget did not create a net gain. A compact external handle requires unique issuance, collision checks, reissue, and authenticated retained provenance; it is not collision-resistant by itself. Each summary has its exact `run.py` in the same iteration folder. These results remain smoke evidence only, not speech-corpus, adversarial, codec-generalization, or perceptual-quality evidence.

Iteration 020 tests a more aggressive fixed-codeword reallocation: a 4-byte external registry handle plus 16 parity symbols retains the same 20-byte codeword, 184 carriers, and four replicas while increasing the errors-only Reed--Solomon radius from seven to eight byte symbols. On the same ten fresh synthetic crop fixtures, it recovers 6/10 trailing and 7/10 leading crops versus the 6-byte/14-parity baseline's 5/10 and 6/10, with no known-handle matches from controls. This is a candidate for separately seeded validation only. A 32-bit lookup value is not collision-resistant; any deployment would require a capacity-bounded authenticated registry, unique issuance, collision checks and reissue, retained provenance, and rate-limited lookup.

Iterations 021-029 continue the non-oracle crop study. The important result is iteration 021's duration-feasible top-three coarse hypothesis bank: on fresh seeds it reaches 9/10 trailing and 10/10 leading recovery, and every selected result has a post-hoc RS cost at most 16 with no selected negative controls. The later phase audits show that individual abstentions can have nearby low-cost recovery ridges, but fixed phase biases do not generalize; an adaptive phase fallback reaches 9/10 trailing and 10/10 leading, then gap relaxation fails to rescue the last trailing abstention. The current bottleneck is therefore carrier-map/payload reliability on rare covers, not further RS allocation, simple phase shifts, or the local pilot-gap threshold. These remain bounded synthetic smoke results, not an application robustness claim.

Iteration 030 separates those two reliability hypotheses on one failed/recovered trailing pair. The failed case has no retained-frame-map agreement and `82` observed bit errors, while the recovered case has `99.3%` map agreement and only `5` bit errors. Future work should improve blind local candidate-map selection before changing payload strength or parity again.

Iteration 031 localizes that map failure further: the failed replay uses coarse offset `+15` and generates every candidate frame `15` frames away from the encoder map, so the true frame is absent from all candidate pairs. The next bounded study should improve coarse-hypothesis coverage before changing local payload scoring.

Iteration 032 tests that correction directly with a duration-derived one-edge mode bank: offset `0` for the trailing-crop hypothesis and offsets `15`/`16` for the leading-crop hypothesis. On ten new synthetic covers under the named `250 ms` crops, it recovers `10/10` trailing and `10/10` leading cases; every selected result has post-hoc RS cost at most `16`, and no unwatermarked or wrong-secret control selects a result. This is bounded smoke evidence for those declared transforms only, not a general robustness claim.

The next evaluation should use a licensed varied speech corpus, unwatermarked controls, pre-registered false-positive and true-positive rates, objective quality metrics, and blinded listening. Arbitrary sample-offset edits, crop/insertion/deletion, and time-scale drift need stronger synchronization before they can be claimed as supported.

## Research Basis

- Chen et al., [WavMark: A Robust Audio Watermarking System Using Transformer](https://arxiv.org/abs/2308.12770) (2023): demonstrates multi-bit audio watermark evaluation under common transformations.
- San Roman et al., [AudioSeal: Proactive Localization and Watermarking of Machine-Generated Speech](https://arxiv.org/abs/2401.17264) (2024): motivates keeping low-rate detection separate from dense attribution.
- Kuo et al., [AudioMarkBench: Benchmarking Robustness of Audio Watermarking](https://arxiv.org/abs/2406.06979) (2024): motivates independent adversarial evaluation rather than treating a single MP3 result as a robustness claim.
- Shivakumar and Mallya, [SilentCipher: Deep Audio Watermarking](https://arxiv.org/abs/2406.03822) (2024): motivates local spectral-energy safeguards instead of one fixed high-frequency carrier.
