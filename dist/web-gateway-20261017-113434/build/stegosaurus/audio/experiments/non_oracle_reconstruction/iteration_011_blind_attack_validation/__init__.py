"""Archive iteration 011's blind attack validation of the selected compact handle plan.

The experiment applies named compression, DSP, resampling, normalization, noise,
and bounded crop transformations to the 6-byte-handle / 14-parity allocation.
It preserves a fully blind carrier-map reconstruction path: source frame maps
remain unavailable to the decoder and are used only for separately labelled
post-hoc diagnostics where a transformed timeline is still comparable.
"""
