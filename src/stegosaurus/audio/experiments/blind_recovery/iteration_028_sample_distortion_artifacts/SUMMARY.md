# Iteration 028 - Sample Distortion Artifacts

## Goal

Generate listening artifacts for every WAV in `samples/`: embed the product
repeated-block watermark, apply the recorded-proxy severity ladder, and save the
strongest distorted WAV that still verifies.

## Output

Artifacts are written to:

```text
samples/max_distortion_recoverable/
```

The folder also contains `manifest.json` with the preflight path, strongest
recoverable level, pooled RS cost, and block votes for each source file.

## Status

Measured run complete.

## Results

| Source | Saved artifact | Preflight | Blocks | Pooled RS cost | Status |
| --- | --- | --- | ---: | ---: | --- |
| `02. Lullaby.wav` | `02_lullaby__level_3_strong.wav` | whole-song peak normalized | 9 | 11 | written |
| `02. Sax and Violins.wav` | `02_sax_and_violins__level_1_light.wav` | whole-song peak normalized | 10 | 12 | written |
| `03. King of Sorrow.wav` | `03_king_of_sorrow__level_1_light.wav` | raw | 9 | 14 | written |
| `08. Gutta Bitch.wav` | `08_gutta_bitch__level_1_light.wav` | raw | 8 | 16 | written |
| `10. Cry Me a River.wav` | `10_cry_me_a_river__clean_no_extra_distortion.wav` | raw | 10 | 16 | clean ceiling only |
| `10. Lovers Rock.wav` | `10_lovers_rock__level_2_moderate.wav` | raw | 8 | 12 | written |
| `19. Get Low.wav` | `19_get_low__level_0_very_light.wav` | raw | 11 | 6 | written |
| `onclassical_demo_luisi_bach_partita_a-minor_bwv-827_1_small-version.wav` | none | whole-song peak normalized | 3 | 32 | no recoverable artifact |

`block_votes` stayed at zero for this run, so all recoveries came from pooled
symbol evidence rather than complete per-block votes.

The OnClassical sample has only three 30-second blocks. That left too little
usable pooled evidence for the current Reed-Solomon budget, even before adding
extra distortion, so no listening artifact was saved for it.
