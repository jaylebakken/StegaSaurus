# Stegosaurus Process Diagrams

These Mermaid diagrams are source-controlled design maps for the current audio
pilot. Solid arrows describe implemented code. The v1 attribution route is a
claimed-handle verifier with a registry-retained private frame map; it does not
blindly discover unknown handles. Dashed arrows mark separate archived blind
reconstruction research. Iteration 032 adds a measured, bounded non-oracle
edge-crop experiment but does not change the v1 verifier. Render this file in a Mermaid-capable Markdown viewer;
the text and code maps remain useful if no renderer is present.

For the newer repeated-block attribution prototype, see
`docs/attribution_v2_visuals.md`. The V4 known-song workflow is documented in
section 5 below.

## 1. Encoding Scheme

```mermaid
flowchart TD
    source["PCM16 WAV or PcmAudio"] --> encode["SpectralAudioEncoder.encode"]
    secret["Shared secret + daily epoch"] --> schema["Derive expected detector bits"]
    encode --> stft["STFT: waveform -> frames x frequency bins"]
    schema --> pairs["Keyed pair + plus/minus chip selection"]
    stft --> frames["Eligible frame selection"]
    pairs --> frames
    frames --> bias["Bias pair magnitudes while preserving pair energy"]
    bias --> inverse["Inverse STFT + source-length normalization"]
    inverse --> embedding["SpectralPilotEmbedding\nwatermarked PCM, coverage, SNR"]
    embedding --> wav["Optional PCM16 WAV write"]

    classDef current fill:#d9edf7,stroke:#31708f,color:#000;
    classDef boundary fill:#fcf8e3,stroke:#8a6d3b,color:#000;
    class encode,stft,pairs,frames,bias,inverse,embedding current;
    class source,secret,wav boundary;
```

**Interpretation**

- The current encoder carries a low-rate statistical pilot, not a production attribution handle.
- One expected detector bit is derived per frame from a secret and epoch; selected bin pairs receive repeated differential evidence.
- The pair-energy safeguard helps constrain the local operation, but does not certify perceptual transparency.

| Diagram step | Application code |
| --- | --- |
| Directional encoding API | `src/stegosaurus/audio/encoder.py:22`, `src/stegosaurus/audio/encoder.py:41` |
| Pilot orchestration | `src/stegosaurus/audio/pilot_workflow.py:31`, `src/stegosaurus/audio/pilot_workflow.py:58` |
| Expected keyed detector bits | `src/stegosaurus/audio/schema_engine.py:64` |
| STFT and inverse STFT | `src/stegosaurus/audio/pilot_transform.py:22` |
| Keyed pairs and spreading chips | `src/stegosaurus/audio/pilot_pairs.py:20` |
| Frame-local modulation | `src/stegosaurus/audio/pilot_frames.py:18` |
| PCM/WAV records and I/O | `src/stegosaurus/audio/pilot_types.py:1` |

## 2. Example Attack And Benchmark Scheme

```mermaid
flowchart LR
    embedded["Watermarked PcmAudio"] --> named["Named deterministic attack"]
    named --> mp3["MP3 round trip\nbitrate is recorded"]
    named --> dsp["PCM DSP\nresample, filter, noise, crop, scale"]

    embedded --> profile["EntropicAttackProfile"]
    config["Declared bounds + root seed"] --> profile
    profile --> recipe["EntropicAttackRecipe\nparameters + child seeds"]
    recipe --> chain["Replayable ordered chain\nDSP + optional MP3"]

    mp3 --> benchmark["AudioPilotBenchmark"]
    dsp --> benchmark
    chain --> benchmark
    benchmark --> evidence["Per-attack extraction or concise failure\nrecipe retained when sampled"]

    classDef current fill:#d9edf7,stroke:#31708f,color:#000;
    classDef caution fill:#f2dede,stroke:#a94442,color:#000;
    class embedded,named,mp3,dsp,profile,recipe,chain,benchmark,evidence current;
    class config caution;
```

**Interpretation**

- A named attack is one declared transformation with explicit parameters; it is not a claim about all variants of that transformation.
- An entropic profile samples only within pre-registered bounds. Its recipe makes the random draw replayable.
- The benchmark stores evidence per attack rather than turning a small fixture into a universal robustness score.

| Diagram step | Application code |
| --- | --- |
| MP3 codec boundary | `src/stegosaurus/audio/attack_core/codec.py` |
| Deterministic signal transforms | `src/stegosaurus/audio/attack_core/signal.py` |
| Entropic configuration and recipes | `src/stegosaurus/audio/attack_core/models.py` |
| Sampling and replaying a profile | `src/stegosaurus/audio/attack_core/profile.py` |
| Benchmark evidence records | `src/stegosaurus/audio/benchmark.py:67` |

## 3. Decoding Scheme

```mermaid
flowchart TD
    received["Received PCM16 WAV or PcmAudio"] --> detect["SpectralAudioDetector.detect"]
    secret["Shared secret + epoch"] --> expected["Regenerate expected detector bits"]
    detect --> stft["STFT"]
    stft --> offsets["Bounded candidate frame offsets"]
    offsets --> score["Keyed pair scores per frame"]
    score --> decisionbits["0 / 1 / erasure\nfrom confidence threshold"]
    expected --> test["Compare expected vs observed bits"]
    decisionbits --> test
    test --> corrected["Bonferroni-corrected binomial tail"]
    corrected --> status["verified | inconclusive | absent"]

    claim["Claimed registry handle\nlookup private AttributionRecord"] --> frame["V1 retained carrier-frame map"]
    received --> frame
    frame --> scores["Four replica soft scores\nweighted combine"]
    scores --> erasures["Carrier bits or erasures"]
    erasures --> rs["ReedSolomonCodec.decode"]
    rs --> handle["Recovered handle equals claim?\nthen authenticate local provenance"]

    decisionbits -. "archived blind reconstruction research" .-> blind["Coarse scan + local-pilot candidate maps"]

    classDef current fill:#d9edf7,stroke:#31708f,color:#000;
    classDef future fill:#e8e8e8,stroke:#666,color:#000,stroke-dasharray: 5 5;
    class detect,stft,offsets,score,decisionbits,expected,test,corrected,status current;
    class blind future;
    class claim,frame,scores,erasures,rs,handle current;
```

**Interpretation**

- Current detector decoding scans bounded offsets, produces soft frame evidence, and returns a corrected statistical status.
- Low-confidence frame observations become erasures rather than guessed bits.
- V1 attribution verifies a supplied registry-handle claim with a retained private frame map. It is not blind discovery and requires authenticated registry lookup outside the waveform.
- The dashed branch documents archived blind reconstruction research; its named synthetic crop measurements do not yet justify a v1 blind-decoding claim.
- Reed--Solomon can recover when `2 * unknown_symbol_errors + known_symbol_erasures <= parity_symbols`; the transport code reports erasures and correction diagnostics.

| Diagram step | Application code |
| --- | --- |
| Directional detection API | `src/stegosaurus/audio/detector.py:22`, `src/stegosaurus/audio/detector.py:41` |
| Offset scan and pilot extraction | `src/stegosaurus/audio/pilot_workflow.py:81` |
| Frame confidence and erasure decision | `src/stegosaurus/audio/pilot_frames.py:18` |
| Statistical decision and correction | `src/stegosaurus/audio/schema_engine.py:87` |
| V1 attribution encoder and decoder | `src/stegosaurus/audio/attribution_core/encoder.py`, `src/stegosaurus/audio/attribution_core/decoder.py` |
| Retained claim record and diagnostics | `src/stegosaurus/audio/attribution_core/models.py` |
| Local authenticated registry | `src/stegosaurus/audio/attribution_core/registry.py` |
| Four-replica carrier map and combine | `src/stegosaurus/audio/attribution_core/repetition.py` |
| Sync framing and interleaving transport | `src/stegosaurus/audio/transport_framing.py:20`, `src/stegosaurus/audio/transport_interleaving.py:17` |

## 4. Experimental Edge-Mode Non-Oracle Reconstruction

```mermaid
flowchart TD
    received["Received PCM WAV\nknown expected sample rate + sample count"] --> loss["Compute received-length loss"]
    loss --> modes["Declare one-edge modes\ntrailing: offset 0\nleading: floor/ceil(loss / STFT hop)"]
    secret["Watermark master secret"] --> maps["Generate keyed local candidate maps\nfor each feasible mode"]
    modes --> maps
    maps --> local["Select local frame candidates\nfrom keyed pilot evidence"]
    local --> payload["Combine four replica payload scores\ninto bits or erasures"]
    payload --> transport["Unframe -> deinterleave -> RS recovery"]
    transport --> select["Choose unique decoder-visible\nRS-successful result or abstain"]
    select --> result["Experimental recovered handle\nor explicit uncertainty"]

    classDef research fill:#fcf8e3,stroke:#8a6d3b,color:#000;
    classDef boundary fill:#f2dede,stroke:#a94442,color:#000;
    class received,loss,modes,maps,local,payload,transport,select,result research;
    class secret boundary;
```

**Interpretation**

- This diagram describes `iteration_032_edge_mode_coarse_bank`, not the v1 application decoder.
- The expected waveform geometry supplies a bounded timing model; the decoder does not receive the retained carrier-frame map or expected handle while choosing a mode.
- The result applies only to the named 30-second synthetic fixture and `250 ms` single-edge leading/trailing crops measured in that experiment.

| Diagram step | Experiment code |
| --- | --- |
| Duration-derived edge modes and local reconstruction | `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_032_edge_mode_coarse_bank/run.py:55` |
| Transport deinterleaving and RS recovery | `src/stegosaurus/audio/transport_channel.py:53`, `src/stegosaurus/audio/transport_interleaving.py:17` |
| Measured result and limits | `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_032_edge_mode_coarse_bank/SUMMARY.md:1` |
| Channel recovery | `src/stegosaurus/audio/transport_channel.py:20` |
| Reed--Solomon boundary | `src/stegosaurus/audio/ecc.py:37` |

## Design Rules Captured Here

- Keep statistical presence detection separate from opaque attribution recovery.
- Record named transformations and replayable entropy recipes before interpreting resilience.
- Treat the v1 verifier as a claimed-handle prototype with a retained map. Keep the edge-mode no-map decoder experimental until broader independent validation covers waveform geometry errors, other edit models, and open-world controls.
- Do not interpret any diagram as a claim of codec, DSP, perceptual, corpus, or adversarial robustness beyond documented experiments.

## 5. V4 Known-Song Clean Leak Workflow

```mermaid
flowchart TD
    source["Registered source song"] --> fp["Cached source block fingerprints"]
    source --> exports["Recipient/export watermarked records"]
    excerpt["Suspicious clean WAV excerpt"] --> localize["Source-audio crop localization"]
    fp --> localize
    localize --> candidates["Top crop-local candidate windows"]
    candidates --> phase["Fine phase search around each candidate"]
    exports --> phase
    phase --> pool["Pool carrier evidence per export"]
    pool --> rank["Rank export records"]
    rank --> decision["accepted match or no accepted export"]

    classDef current fill:#d9edf7,stroke:#31708f,color:#000;
    classDef boundary fill:#fcf8e3,stroke:#8a6d3b,color:#000;
    class source,excerpt boundary;
    class fp,exports,localize,candidates,phase,pool,rank,decision current;
```

**Interpretation**

- This is the V4 clean-file product workflow, not unknown-song discovery.
- Source localization is shared once per selected song; only the top candidate
  windows fan out across recipient/export records.
- The measured release boundary is clean suspicious WAV excerpts. Recorded
  audio, normalization, lossy codec, platform processing, and resynthesis remain
  experimental.

| Diagram step | Application code |
| --- | --- |
| Song/export records | `src/stegosaurus/audio/attribution_workflow/models.py` |
| Source block fingerprints and excerpt localization | `src/stegosaurus/audio/attribution_workflow/fingerprints.py` |
| Phase-refined export fanout | `src/stegosaurus/audio/attribution_workflow/fanout.py` |
| Workflow facade | `src/stegosaurus/audio/attribution_workflow/workflow.py` |
| Tkinter demo controller | `src/stegosaurus/audio/demo_v4_controller.py` |
