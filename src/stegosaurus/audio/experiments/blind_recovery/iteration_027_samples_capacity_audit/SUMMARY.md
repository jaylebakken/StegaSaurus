# Iteration 027 - Samples Capacity Audit

## Goal

Audit the WAV files in `samples/` from a music-producer workflow perspective.
The desired workflow is simple: load a song, embed repeated attribution blocks,
and keep the song order intact. The primary gate is therefore raw sequential
30-second block capacity.

## Method

- Read each PCM16 WAV in `samples/`.
- Split into complete 30-second blocks.
- Try the product `BlockAttributionCodec` on each raw block.
- Retry a peak-normalized copy only as a diagnostic.
- Report whether the whole song is:
  - `producer_ready_raw`,
  - `requires_level_preprocessing`,
  - `partial_song_only`,
  - `not_embeddable_current_profile`.

## Current Result

All eight sample WAVs have a viable path under the current product
`BlockAttributionCodec`.

| File | Complete 30s blocks | Raw embeddable blocks | Whole-song normalized blocks | Workflow status |
| --- | ---: | ---: | ---: | --- |
| `02. Lullaby.wav` | 9 | 7 | 9 | `requires_whole_song_level_preprocessing` |
| `02. Sax and Violins.wav` | 10 | 9 | 10 | `requires_whole_song_level_preprocessing` |
| `03. King of Sorrow.wav` | 9 | 9 | 9 | `producer_ready_raw` |
| `08. Gutta Bitch.wav` | 8 | 8 | 8 | `producer_ready_raw` |
| `10. Cry Me a River.wav` | 10 | 10 | 10 | `producer_ready_raw` |
| `10. Lovers Rock.wav` | 8 | 8 | 8 | `producer_ready_raw` |
| `19. Get Low.wav` | 11 | 11 | 11 | `producer_ready_raw` |
| `onclassical_demo_luisi_bach_partita_a-minor_bwv-827_1_small-version.wav` | 3 | 0 | 3 | `requires_whole_song_level_preprocessing` |

Aggregate:

- 8 files tested,
- 5 files are raw producer-ready,
- 3 files require only a whole-song peak-normalization pass,
- 0 files require excerpt hunting,
- 0 files are unembeddable under the current product profile after whole-song
  level normalization.

## Interpretation

This is a much better producer-facing result than the earlier experimental
contrastive-capacity checks suggested. The product `BlockAttributionCodec`
can embed these real tracks in-place by sequential complete 30-second blocks.

The remaining friction is level sensitivity:

- `02. Lullaby.wav` fails raw capacity in the intro and late outro blocks but
  passes after one whole-song peak normalization.
- `02. Sax and Violins.wav` fails raw capacity in the first block but passes
  after one whole-song peak normalization.
- The OnClassical piano sample fails all raw blocks but passes after one
  whole-song peak normalization.

From a minimally invasive music-producer workflow perspective, the next product
step should be an automatic preflight:

1. Try raw sequential embedding.
2. If raw capacity fails, preview a single whole-song gain normalization.
3. Tell the user which path will be used before writing the watermarked file.

This avoids asking producers to manually hunt for excerpts or alter song
arrangement. It also avoids per-block gain changes, which would be more
musically intrusive.
