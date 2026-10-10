"""Separate application tests from archived experiment-regression checks.

``application`` exercises the current encoder, detector, schema, attacks, and
benchmark APIs as a small functional suite. ``experiment_regressions`` reruns
the archived research iterations to keep their recorded mechanics reproducible.
Neither package participates in runtime WAV encoding or detection.
"""
