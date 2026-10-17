"""Archive iteration 019's fixed-codeword registry-handle parity tradeoff experiment.

The study compares the existing 48-bit opaque handle with 14 Reed--Solomon
parity symbols against a 40-bit versioned registry-handle representation with
15 parity symbols. Both retain a 20-byte protected codeword and identical
audio carrier demand. The shorter representation is explicitly modeled as a
collision-checked, collision-reissuable external registry lookup value, not
self-contained provenance data or an intrinsically collision-resistant digest.
"""
