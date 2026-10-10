"""Contain non-production audio watermark experiments and their benchmark records.

The modules in this package measure hypotheses that have not yet earned a place
in the public encoder or detector API. ``transport_optimization`` archives the
completed oracle-aligned carrier and token experiments. ``non_oracle_reconstruction``
is an independent experimental track whose numbering restarts at iteration 001
for blind candidate-map recovery. Regression and integration tests remain
separately located in ``stegosaurus.audio.tests``.
"""
