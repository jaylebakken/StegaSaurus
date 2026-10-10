# Iteration 020: Sixteen-Parity Registry Handle

## Goal

Determine whether shrinking a registry lookup handle from 6 bytes to 4 bytes can add two Reed--Solomon parity symbols, raise the errors-only correction radius from seven to eight symbols, and improve blind non-oracle recovery without increasing audio carrier demand.

## Method

- Covers: ten fresh seeded, 30-second synthetic music-like variants with seeds `7100-7109`, shared with iteration 019 for an allocation-only comparison.
- Attacks: unchanged `250 ms` leading and trailing crops.
- Alignment and carriers: unchanged blind keyed coarse scan, deterministic one-edge-model center phase, frozen contrastive carrier selector, `500-3800 Hz` band, `184` logical carrier bits, and `736` four-replica placements.
- Allocations: baseline 6-byte opaque handle + 14 parity and compact 4-byte versioned registry handle + 16 parity. Both retain a 20-byte protected codeword plus 3 framing/checksum bytes.
- Registry semantics: the compact value is a 32-bit external lookup handle. Issuance must use an authenticated registry record, unique allocation, collision detection, reissue, and a separately assessed namespace-capacity policy.
- Controls: independently decoded transformed unwatermarked and wrong-secret inputs for every allocation/crop/cover.

## Results

`RESULTS.json` contains the complete 40-record result set. All executions completed, and all unwatermarked and wrong-secret controls rejected the known handle.

| Allocation | Crop | Exact recovery | Center-feasible recovery | Coarse accepted | Center feasible | Median / maximum RS cost | Median carrier erasures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6-byte handle + 14 parity | trailing `250 ms` | 5/10 | 5/6 | 8/10 | 6/10 | 15 / 20 | 3 |
| 6-byte handle + 14 parity | leading `250 ms` | 6/10 | 6/6 | 9/10 | 6/10 | 11.5 / 20 | 3.5 |
| 4-byte handle + 16 parity | trailing `250 ms` | 6/10 | 6/6 | 9/10 | 6/10 | 12 / 20 | 2 |
| 4-byte handle + 16 parity | leading `250 ms` | 7/10 | 7/7 | 9/10 | 7/10 | 12 / 20 | 2 |

Both allocations retained exactly 20 protected bytes, 3 framing/checksum bytes, 184 logical carrier bits, and 736 four-replica placements. On this fixed fresh-cover fixture, the 16-parity allocation adds one exact recovery under each crop and has lower median RS cost and carrier erasures. All center-feasible 16-parity trials recovered; the baseline's one center-feasible trailing failure had RS cost 17, exceeding its 14-symbol budget.

The result is consistent with the extra two parity symbols and eighth errors-only correction symbol helping near-budget trials, but it does not isolate parity from every consequence of changing the protected handle bytes. Treat the 4-byte allocation as the candidate for a separately seeded held-out validation, not as a production selection.

## Interpretation Rules

- This is a transport-allocation experiment, not a production registry or collision-rate certification.
- A 32-bit handle is not collision-resistant and cannot reconstruct user/time information without its retained external registry record.
- A gain is informative only if it occurs at identical protected-codeword length and carrier demand, with controls continuing to reject.
- Any deployment candidate requires a capacity-bounded registry namespace, collision detection and reissue, rate-limited authenticated lookup, and retained authenticated provenance.

## Reproduce

```powershell
python -m stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_020_sixteen_parity_registry_handle.run
```
