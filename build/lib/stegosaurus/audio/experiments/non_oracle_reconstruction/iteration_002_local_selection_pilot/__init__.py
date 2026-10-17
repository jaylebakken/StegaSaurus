"""Contain iteration 002 of local-pilot non-oracle carrier-map reconstruction.

The experiment splits each selected frame's keyed spectral pairs into a
decoder-known local selection-pilot group and an opaque payload-bit group. It
tests whether pilot-guided frame selection can replace iteration 001's
unreliable data-bit consensus rule without using the encoder's frame map.
"""
