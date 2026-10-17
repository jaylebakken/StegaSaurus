"""Contain iteration 001 of clean-audio non-oracle candidate-map reconstruction.

The experiment measures whether the decoder can regenerate a small set of
secret-keyed carrier-frame candidates from observed clean audio and select a
usable map without receiving the encoder's calibrated frame map. It preserves
the oracle map only after decoding to score map reconstruction accuracy.
"""
