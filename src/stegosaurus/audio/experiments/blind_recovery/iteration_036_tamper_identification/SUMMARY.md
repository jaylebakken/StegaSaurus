# Iteration 036 - Tamper Identification

## Goal

Tie down identification before changing the encoder again. Iterations 034 and
035 showed that independent re-watermarking can make both parent and child
claims unrecoverable. This experiment asks whether that state can be identified
as overwrite/tamper-like evidence rather than treated as ordinary absence.

## Method

The suite builds five controlled scenarios from `10. Lovers Rock.wav`:

1. `clean_source`: no accepted watermark should exist.
2. `valid_parent`: one valid retained watermark should recover.
3. `overwritten_parent_child`: parent encoded, then child independently encoded
   over it.
4. `distressed_parent`: parent plus light recorded-proxy transform.
5. `cropped_parent`: parent with a 30-second leading crop.

Each scenario is verified against three retained records:

```text
parent
child
wrong
```

The first-pass classifier uses:

```text
accepted claim -> accepted
shorter geometry -> geometry_failure
near-miss competing RS costs -> tamper_suspected
otherwise -> absent
```

This is a diagnostic policy experiment, not a production detector.

## Results

| Scenario | Expected | Predicted | Best RS cost | Second RS cost | Accepted claims |
| --- | --- | --- | ---: | ---: | ---: |
| `clean_source` | absent | absent | 31 | 33 | 0 |
| `valid_parent` | accepted | accepted | 0 | 34 | 1 |
| `overwritten_parent_child` | tamper_suspected | tamper_suspected | 21 | 25 | 0 |
| `distressed_parent` | accepted | accepted | 6 | 31 | 1 |
| `cropped_parent` | geometry_failure | geometry_failure | 26 | 32 | 0 |

The overwrite case produced the useful signature:

```text
child:  RS cost 21
parent: RS cost 25
wrong:  RS cost 33
```

No claim recovered, but parent/child evidence was much closer than a clean
unwatermarked source. That supports an experimental `tamper_suspected` state.

## Interpretation

This is the first positive result for overwrite identification:

```text
no accepted event + near-threshold retained events != plain absence
```

The classifier should not accuse anyone or assert a complete chain. It should
only say that retained registry records show watermark-like evidence consistent
with overwrite or tamper.

Suggested wording:

```text
No export record was accepted. However, retained records for parent and child
events both produced near-threshold evidence. Treat this as suspected overwrite
or tamper, not as a clean absence.
```

## Limits

This result used one song, one parent/child pair, one wrong control, and retained
full-song geometry. It does not yet cover:

```text
unknown crop localization
larger registries
many wrong controls
branch controls
distressed overwrite cases
real recorded audio
```

## Next Step

Expand tamper identification before product integration:

1. Add more wrong retained records to test false tamper alarms.
2. Test parent -> child A and parent -> child B branch controls.
3. Test overwritten audio after peak normalization and light proxy transforms.
4. Test clean cropped valid watermark with V4 localization instead of retained
   full-song geometry.
5. Add a result vocabulary:

```text
accepted
absent
geometry_failure
tamper_suspected
insufficient_evidence
```

Only after those controls pass should `tamper_suspected` move into the V4/V5
application workflow.
