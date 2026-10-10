# Stegosaurus: Industry and Patent Viability Overview

**Assessment date:** 2026-10-09  
**Repository status:** local experimental pilot; not a production leak-attribution system.

## Executive assessment

Stegosaurus is a promising research direction for **keyed presence detection in audio that an organization already controls**, but it is not yet an industry-ready solution for tracking leaks. Its current waveform path embeds a secret-keyed statistical pilot in STFT magnitude relationships. It also includes a bounded claimed-handle waveform attribution prototype, while a separate non-oracle decoder remains experimental and limited to named synthetic crop conditions.

The most important product distinction is:

- **Presence:** “Does this audio contain the signal for which I hold the secret and epoch?” Stegosaurus implements this experimentally.
- **Attribution:** “Which recipient, release, or transaction does this copy identify?” The repository has a claimed-handle waveform-to-token prototype with a local authenticated registry and retained private map. It does not have durable registry infrastructure, broad blind discovery, or a provenance decision for arbitrary received audio.
- **Fingerprint identification:** “Which known audio is this?” Stegosaurus does not attempt this database-search problem.

### Bottom line

| Question | Current judgment | Why |
| --- | --- | --- |
| Useful as an internal R&D pilot? | **Yes** | It is deterministic, inspectable, keyed, replayable, and explicit about oracle versus blind experiments. |
| Ready for paid leak tracing? | **No** | Blind synchronization, real-audio validation, authentication, quality evaluation, and per-copy attribution are incomplete. |
| Competitive with established fingerprints for finding leaked music? | **No** | Fingerprints require no pre-embedding and are designed to identify known content by database match. |
| Potentially complementary to forensic watermarking? | **Yes** | A private keyed presence layer could complement a stronger recipient-specific watermark or provenance registry. |
| Patentable as presently implemented? | **Unclear and presently weak** | The building blocks are heavily represented in prior art; any defensible claim would need a specific, non-obvious technical combination and evidence of a technical effect. This is not a patentability or freedom-to-operate opinion. |

## What the repository actually implements

The public pilot accepts 16-bit PCM WAV, downmixes it to mono, computes a Hann-window STFT, and modifies secret-keyed pairs of spectral magnitudes in a configured band. One expected bit is derived per frame from a shared secret, a daily epoch, and the frame index. Pseudorandom chips spread that bit over up to 16 pairs. The implementation preserves each pair’s combined magnitude and preserves phase when changing magnitudes; these are engineering controls, not a measured claim of perceptual transparency.

The detector regenerates the keyed carriers, produces soft signed pair scores, turns low-confidence observations into erasures, scans a bounded set of frame offsets, and chooses a candidate using a corrected binomial tail probability. It reports `verified`, `inconclusive`, or `absent`. This is a keyed statistical hypothesis test, not a public audio fingerprint and not a cryptographic proof of origin.

The separate attribution schema supports a fixed-length opaque token, keyed bit interleaving, framing/sync patterns, byte erasures, and Reed–Solomon correction. The v1 claimed-handle API embeds a four-byte handle with sixteen parity symbols and verifies a supplied claim through a registry-retained private carrier map. Reed–Solomon can repair bounded channel damage, but it does not authenticate a token or establish who created an audio copy; production requires durable authenticated registry policy, access control, and key management.

The benchmark layer contains named local transformations and replayable stochastic attack recipes: MP3 round trips, resampling, normalization, low-pass filtering, noise, reverb, crop, concatenation, and time scaling. A named recipe is an evaluation condition, not a general robustness guarantee.

## Evidence and limitations

The strongest evidence is useful but narrow:

- The detector-only pilot reports clean marked detection on one deterministic synthetic fixture at approximately 40 dB sample SNR, with named transformation results and unmarked controls. The report explicitly says this is not a corpus-level false-positive estimate, perceptual evaluation, or deployment claim.
- Oracle-aligned transport experiments initially failed to recover the complete token even on clean audio. Later experiments improved the allocation and repetition strategy, but oracle results retain source-frame maps and therefore are optimistic upper bounds rather than blind-decoder evidence.
- The non-oracle reconstruction track's latest bounded crop experiment (`iteration_032_edge_mode_coarse_bank`) reports 10/10 exact recovery for each named `250 ms` leading and trailing crop direction on ten fresh synthetic 30-second covers. Every selected result has post-hoc RS cost at most 16, and the experiment's unwatermarked and wrong-secret controls have no selected outputs. This result depends on known waveform geometry and the declared single-edge crop model; it does not transfer to other crop durations, codecs, DSP, recorded audio, or open-world false-acceptance rates.
- The same study reports zero exact known-handle accepts in its limited unwatermarked and wrong-secret controls. That is valuable regression evidence, not an open-world false-positive rate.
- Reported sample SNR is a waveform diagnostic. There is no MOS, PESQ, PEAQ, listening panel, or psychoacoustic masking study in this repository.
- The evaluated covers are synthetic. There is no licensed varied speech/music corpus, independent real-world distributor pipeline, arbitrary insertion/deletion synchronizer, adversarial evaluation, or production key/registry service.

These boundaries are not incidental. A leak-tracing product must show reliable copy-specific recovery after the transformations used by its distribution pipeline, measure false accepts over a large unmarked population, authenticate the recovered identifier, and establish that the mark remains usable at an acceptable quality level.

## Industry viability

### Best near-term use case

The most credible pilot is a **closed-world internal verification service**: an organization marks controlled audio before a known workflow, retains the secret and epoch policy, and uses detection as one signal in an investigation. It could answer whether a sample is consistent with a controlled mark. It should not yet be marketed as proof that a particular person leaked the file.

A realistic product architecture would add:

1. A production waveform-to-attribution encoder and blind decoder, with one copy-specific identifier per recipient or transaction.
2. A collision-checked, authenticated registry mapping opaque handles to release events. Prefer an authenticated MAC/signature or authenticated registry response; ECC alone is insufficient.
3. Key lifecycle controls: tenant isolation, rotation, revocation, epoch policy, audit logs, and protection against an insider who has the marking key.
4. A synchronization design for crop, insertion/deletion, sample-rate drift, time-scale changes, and re-recording. The current bounded offset scans do not cover that space.
5. A licensed corpus of speech and music, unmarked controls, blinded evaluation, confidence calibration, and target false-accept/false-reject operating points.
6. Objective and subjective quality measurements, plus a clear statement of which codecs and DSP chains were tested.
7. Independent security review of detector-key exposure, replay, collusion, copy attack, token substitution, and registry authorization.

### Fit against competing approaches

| Approach | What it solves well | Leak-tracing strengths | Weaknesses relative to Stegosaurus | Industry position |
| --- | --- | --- | --- | --- |
| **Audio fingerprinting** (e.g., Shazam-style landmarks) | Identifies known content from an audio query without changing the content | Finds leaked or reposted copies even when they were never marked; mature search/database model | Does not inherently identify the recipient or release instance; requires a reference corpus and can be a poor fit for unseen/private material | Strong complement for discovery, not a substitute for recipient attribution |
| **Commercial forensic watermarking** | Embeds a copy- or viewer-specific identifier intended to survive distribution | Directly addresses “which authorized copy leaked?” and can be integrated into controlled distribution | Usually proprietary, operationally complex, and requires robust embedding, per-copy issuance, and a trusted investigation service | Closest incumbent category for the stated leak-tracking goal |
| **Learned payload watermarking** (WavMark-like) | Embeds a multi-bit message directly in short waveform regions and trains against transformations | Higher payload and end-to-end decoding are attractive for per-copy IDs; can optimize jointly for quality and named attacks | Model/data/GPU dependencies, distribution-shift risk, reproducibility and licensing questions; claims depend on the declared attack/training distribution | Strong research and product alternative; must be evaluated on the target catalog and pipeline |
| **Localized learned watermarking** (AudioSeal-like) | Detects marked fragments in long or edited audio and can expose local detection evidence | Localized detection is useful when a leak is clipped or assembled from many sources; supports optional small messages | Current Stegosaurus is not localized at sample scale and has no comparable learned robustness or detector throughput evidence | Relevant benchmark and potential complement for generated or edited audio |
| **Signed provenance** (C2PA-style) | Records signed claims, creator/tool identity, and edit history in a manifest | Strong for cooperative, provenance-preserving workflows and auditability | Metadata/manifests can be stripped; it is not a covert signal that survives arbitrary re-recording or leak redistribution | Complementary trust layer, not a replacement for forensic marking |
| **Stegosaurus today** | Interpretable keyed presence pilot with explicit statistical decisions and a separate future transport layer | Secret-controlled testing, low-level diagnostics, deterministic experiments, and a possible private beacon | Very low current payload integration, incomplete blind synchronization, synthetic-only evidence, no authentication, and no perceptual study | R&D foundation, not an incumbent replacement |

For music leak investigations, fingerprinting and forensic watermarking are not mutually exclusive. Fingerprinting can discover and cluster copies; a recipient-specific watermark can attribute a controlled copy; signed provenance can support an evidentiary chain when preserved. Stegosaurus would need to occupy one of those roles clearly rather than describe a presence decision as attribution.

## Research basis of the design

The following table separates established ideas from repository-specific engineering and unvalidated novelty hypotheses.

| Stegosaurus feature or decision | Research lineage / status | Assessment |
| --- | --- | --- |
| STFT/transform-domain audio modification | Transform-domain watermarking is established; spread-spectrum watermarking predates this repository. [1] | **Established building block.** The specific parameters are local choices. |
| Secret-keyed pseudorandom carrier selection and ± chips | Consistent with secure spread-spectrum watermarking and keyed watermark detection. [1] | **Established principle.** HMAC domain separation and the exact pair/chip derivation are implementation details, not automatically novel. |
| Pairwise log-magnitude modulation | A transform-domain modulation choice in a known family of magnitude/energy watermark designs. | **Engineering adaptation.** A prior-art search would be required before treating the exact formulation as novel. |
| Preserve phase and each pair’s combined magnitude | A plausible distortion/energy safeguard that keeps the change local and interpretable. | **Repository-specific combination; unvalidated.** No listening or perceptual study proves that it is inaudible or superior. |
| One keyed bit per frame plus statistical presence decision | Detection by correlation/agreement and hypothesis testing are established ideas; AudioSeal and WavMark also distinguish detection from message recovery in different ways. [2][3] | **Established architecture at a high level.** The daily epoch, binomial tail, and bounded offset correction are local design choices. |
| Low-confidence observations represented as erasures | Standard channel-coding/soft-decision engineering, made explicit in this codebase. | **Useful implementation discipline, not a clear invention.** It trades capacity for safer decisions. |
| Reed–Solomon parity, framing, sync bits, and keyed interleaving | Standard error-correcting-code and digital-channel techniques. | **Established building blocks.** They do not authenticate an identifier. |
| Separate presence and future attribution layers | Separation is technically sensible and appears in the broader watermarking design space; AudioSeal, for example, supports detection independently of an optional small message. [2] | **Good architecture, not by itself novel.** The repository’s explicit scope distinction is a strength of the engineering record. |
| Blind candidate-map reconstruction and contrastive map selection | A repository-specific response to the gap between encoder-selected carriers and a decoder without the source map. | **Most plausible research contribution, but currently unproven as patentable.** It needs a fully integrated decoder, broader baselines, and a demonstrated technical advantage. |
| Pair-energy-preserving carriers restricted to a measured band | A practical adaptation based on the repository’s low-pass experiments. | **Measured tuning, not a general invention claim.** It remains synthetic and map-dependent in important results. |
| Replayable entropic attack profiles and explicit oracle/blind separation | Reproducibility and benchmark hygiene. AudioMarkBench supports the need for systematic robustness evaluation. [4] | **Evaluation practice, not a likely patentable core.** |
| Opaque registry handle plus parity allocation | Common provenance-system pattern: keep the embedded value small and resolve it externally. | **Product architecture, not authentication.** The registry, collision policy, signatures/MACs, and access audit are still absent. |

### What is genuinely distinctive here?

The potentially distinctive research hypothesis is not “audio watermarking,” “STFT,” “Reed–Solomon,” or “secret-keyed spreading” in isolation. It is the particular combination of:

1. a keyed, epoch-scoped statistical presence beacon;
2. local, pair-energy-preserving spectral modulation;
3. erasure-aware observations and protected transport; and
4. blind reconstruction of usable carrier maps after edits.

Even that combination should currently be described as a **design hypothesis**, not a proven novel invention. The repository does not include a systematic prior-art search, claim chart, recorded-audio advantage over alternatives, or a complete end-to-end implementation. “Novel in this repository” means only that the combination was developed here; it does not mean novel under patent law.

## Preliminary patent viability

### Technical screen

A patent claim normally needs more than a list of known components. In broad terms, novelty asks whether a single prior-art reference discloses the claimed subject matter, while obviousness/non-obviousness asks whether the claimed combination would have been an obvious modification to a skilled person. The USPTO’s MPEP sections on anticipation and obviousness are useful starting points, but jurisdiction, claim wording, filing dates, and the full prior-art record control. [5][6]

**Broad claims look vulnerable.** Claims such as “embed a secret message in audio using an STFT,” “use pseudorandom spectral carriers,” “use error correction,” or “detect a watermark statistically” overlap mature watermarking and communications literature. Claims to generic audio attribution, copy identification, or a registry-backed token also face fingerprinting, forensic watermarking, DRM, and provenance prior art.

**A narrower claim may be worth investigating.** A candidate claim could focus on a concrete end-to-end mechanism in which a secret/epoch derives frame-specific disjoint spectral pairs and chips, modulation preserves a defined pair statistic, the decoder uses confidence erasures and a bounded blind candidate-map/synchronization procedure, and the resulting transport meets a specified technical performance condition under a defined class of edits. Whether this is non-obvious depends on the references and evidence, not on the elegance of the implementation.

**The present evidence is insufficient.** The experiments show feasibility signals, but the most favorable transport results are tied to synthetic covers, selected attacks, fixed fixtures, or retained oracle maps. The failed crop results and lack of real-audio/perceptual evidence make it difficult to argue a surprising technical effect over established methods.

### Patent versus trade-secret strategy

Patent protection requires disclosing the claimed mechanism and does not protect the secret key or operational know-how by itself. A leak-tracing operator may instead keep carrier-key derivation, threshold calibration, registry mappings, attack recipes, and deployment telemetry as trade secrets. A hybrid strategy could patent a narrow technical mechanism while protecting keys, corpus-specific calibration, and registry operations as confidential information. That decision should be made with patent counsel before public disclosure or filing.

Commercial freedom to operate is a separate question from whether Stegosaurus could obtain a patent. Existing patents and licenses around forensic watermarking, audio codecs, neural models, and content-identification services must be searched separately. This overview does not perform an exhaustive patent search or provide legal advice.

### Recommended invention-readiness work

Before spending materially on prosecution, the team should:

1. Freeze a dated invention disclosure describing the exact algorithm, alternatives considered, and the blind synchronization contribution.
2. Run a professional patent search and claim chart across spread-spectrum audio watermarking, transform-domain pair/magnitude methods, statistical keyed detection, synchronization, neural audio watermarking, forensic watermarking, and provenance tokens.
3. Build an end-to-end waveform encoder/decoder with authenticated, copy-specific identifiers; document which parts are essential and which are optional.
4. Compare against at least one classical watermark, WavMark, AudioSeal or a comparable localized learned system, and a fingerprint baseline on the same licensed corpus and attack matrix.
5. Measure detection and exact-token recovery with confidence intervals, open-world false accepts, wrong-secret controls, collusion/copy attacks, and realistic distributor transformations.
6. Measure quality with objective metrics and blinded listening. A reported sample SNR is not enough.
7. Ask counsel to assess novelty, non-obviousness, enablement/written description, inventorship, public-disclosure timing, and freedom to operate in each target jurisdiction.

## Recommended industry path

**Phase 1 — research gate:** retain the current pilot as an interpretable presence detector; add real speech/music data, negative populations, calibrated operating points, and perceptual tests. Do not call results attribution.

**Phase 2 — attribution gate:** harden the existing claimed-handle waveform path, replace the local registry with authenticated durable resolution, and validate the experimental edge-mode synchronization policy across broader pre-registered geometry and attack conditions. Require exact recovery and zero unauthorized registry accepts under defined evaluation conditions.

**Phase 3 — product comparison:** benchmark against a classical forensic watermark, a learned payload watermark, and an audio fingerprint service. Choose a hybrid if the use case needs both discovery and per-copy attribution.

**Phase 4 — protection decision:** after the prior-art search and reproducible technical advantage are documented, decide among patent filing, defensive publication, trade secret, or a combination. Do not delay key and registry security while waiting for a patent decision.

## References

1. D. K. H. Cox, J. Kilian, T. Leighton, and T. Shamoon, “Secure Spread Spectrum Watermarking for Multimedia,” *IEEE Transactions on Image Processing* (1997), DOI: [10.1109/83.650120](https://doi.org/10.1109/83.650120). Foundational spread-spectrum watermarking reference.
2. Robin San Roman et al., “Proactive Detection of Voice Cloning with Localized Watermarking,” ICML 2024 / [AudioSeal paper record](https://arxiv.org/abs/2401.17264), with the [official implementation](https://github.com/facebookresearch/AudioSeal). The implementation documents localized detection and an optional small message separate from the high-level detection result.
3. Guangyu Chen et al., “WavMark: Watermarking for Audio Generation,” 2023, [paper record](https://arxiv.org/abs/2308.12770) and [official implementation](https://github.com/wavmark/wavmark). The project documents a learned 16-bit payload workflow and evaluation against named audio attacks; its reported metrics are not transferred to Stegosaurus.
4. “AudioMarkBench: Benchmarking Robustness of Audio Watermarking,” [arXiv record](https://arxiv.org/abs/2406.06979). Used here as support for systematic, attack-matrix-based comparison rather than single-condition robustness claims.
5. United States Patent and Trademark Office, MPEP § 2131, “[Anticipation—Application of the Prior Art](https://www.uspto.gov/web/offices/pac/mpep/s2131.html).”
6. United States Patent and Trademark Office, MPEP § 2141, “[The Legal Concept of Obviousness](https://www.uspto.gov/web/offices/pac/mpep/s2141.html).” See also WIPO’s [patent overview](https://www.wipo.int/en/web/patents) for general international context.
7. Coalition for Content Provenance and Authenticity, [C2PA specifications](https://c2pa.org/specifications/specifications/2.2/index.html) and the [C2PA Rust SDK](https://github.com/contentauth/c2pa-rs). The SDK documents signing, validating, and embedding provenance manifests; this is complementary to a covert audio signal.
8. Haitsma and Kalker, “A Highly Robust Audio Fingerprinting System,” ISMIR 2002, [proceedings record](https://ismir2002.ismir.net/proceedings/02-FP04-2.pdf).
9. Avery Wang, “An Industrial Strength Audio Search Algorithm,” ISMIR 2003, [paper record](https://www.ee.columbia.edu/~dpwe/papers/Wang03-shazam.pdf).
10. Commercial category examples for further diligence: [NAGRA forensic watermarking](https://www.nagra.com/forensic-watermarking) and [Audible Magic content identification](https://www.audiblemagic.com/content-identification/). These links identify market categories, not independent performance validation.

## Repository sources reviewed

- `README.md`
- `src/stegosaurus/audio/pilot.py`
- `src/stegosaurus/audio/schema.py`
- `src/stegosaurus/audio/transport.py`
- `src/stegosaurus/audio/ecc.py`
- `src/stegosaurus/audio/attacks.py`
- `src/stegosaurus/audio/benchmark.py`
- `src/stegosaurus/audio/experiments/transport_optimization/iteration_001_detector_pilot/SUMMARY.md`
- `src/stegosaurus/audio/experiments/transport_optimization/iteration_005_duration_parity_budget/SUMMARY.md`
- `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_008_held_out_gap_validation/SUMMARY.md`
- `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_011_blind_attack_validation/SUMMARY.md`
- `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_018_paired_median_confirmation/SUMMARY.md`
- `src/stegosaurus/audio/experiments/non_oracle_reconstruction/iteration_032_edge_mode_coarse_bank/SUMMARY.md`

The repository evidence and this overview intentionally preserve the distinction between audio encoding, statistical detection, claimed-handle attribution verification, and experimental non-oracle reconstruction. No compression, DSP, or perceptual robustness is claimed beyond the named measured evaluations.
