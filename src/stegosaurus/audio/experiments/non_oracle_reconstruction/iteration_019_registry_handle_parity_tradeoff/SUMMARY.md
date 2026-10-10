# Iteration 019: Registry Handle Parity Tradeoff

## Goal

Measure whether reducing an opaque registry lookup handle from 6 bytes to 5 bytes can add one Reed--Solomon parity symbol while preserving the 20-byte codeword and all audio carrier demand.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `7100-7109`, unused by prior crop experiments.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Alignment: unchanged blind keyed coarse scan plus deterministic one-edge-model center phase. The median combiner is frozen and not used.
- Allocations: baseline 6-byte opaque handle + 14 parity; compact 5-byte versioned registry handle + 15 parity. Both use 20 protected bytes, 3 framing/checksum bytes, 184 logical carrier bits, and four replicas.
- Registry semantics: the compact value is a 40-bit random/keyed external lookup handle. A production registry must enforce uniqueness, store full provenance plus authentication material, and regenerate a handle before embedding if issuance collides.
- Controls: independently decoded transformed unwatermarked and wrong-secret inputs for every allocation/crop/cover.

## Results

`RESULTS.json` contains the complete 40-record result set. All executions completed, and all unwatermarked and wrong-secret controls rejected the known handle.

| Allocation | Crop | Exact recovery | Center-feasible recovery | Coarse accepted | Center feasible | Median / maximum RS cost | Median carrier erasures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6-byte handle + 14 parity | trailing `250 ms` | 5/10 | 5/6 | 8/10 | 6/10 | 15 / 20 | 3 |
| 6-byte handle + 14 parity | leading `250 ms` | 6/10 | 6/6 | 9/10 | 6/10 | 11.5 / 20 | 3.5 |
| 5-byte handle + 15 parity | trailing `250 ms` | 5/10 | 5/6 | 8/10 | 6/10 | 15 / 20 | 3 |
| 5-byte handle + 15 parity | leading `250 ms` | 5/10 | 5/6 | 9/10 | 6/10 | 13.5 / 20 | 3 |

Both allocations retained exactly 20 protected bytes, 3 framing/checksum bytes, 184 logical carrier bits, and 736 four-replica placements. Thus the compact form purchased the additional parity symbol without increasing waveform capacity demand.

The one-symbol increase did not produce a net fresh-cover recovery improvement: the compact allocation matched the baseline on trailing crops and recovered one fewer leading-crop cover. This is expected to be a weak change for unknown byte errors: Reed--Solomon's errors-only radius remains seven symbols for both 14 and 15 parity symbols. The extra symbol can only absorb one additional unit of the mixed `2 * errors + erasures` budget. The failed center-feasible compact trials at RS cost 16 exceeded its 15-symbol budget.

## Interpretation Rules

- This is a transport tradeoff experiment, not a production registry implementation or collision-rate certification.
- The compact handle is not self-describing and cannot reconstruct user/time information without its external registry record.
- A 40-bit handle is not collision-resistant by itself. The issuer must ensure unique allocation, persist the authenticated provenance record, check every collision, and reissue before embedding.
- Report codeword length and carrier count alongside recovery; adding parity is useful here only because payload bytes shrink by the same amount.
- A future 4-byte handle plus 16 parity experiment would increase the errors-only radius from seven to eight symbols, but requires a separately justified registry namespace, collision/reissue analysis, and authentication design.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run
```
