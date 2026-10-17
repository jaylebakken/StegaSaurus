"""Contain non-production audio watermark experiments and their benchmark records.

The modules in this package measure hypotheses that have not yet earned a place
in the public encoder or detector API. ``transport_optimization`` archives the
completed oracle-aligned carrier and token experiments. ``non_oracle_reconstruction``
is an independent experimental track whose numbering restarts at iteration 001
for blind candidate-map recovery. ``blind_recovery`` restarts numbering again
for experiments that reduce the original-geometry assumptions needed for
attribution recovery. Regression and integration tests remain separately
located in ``stegosaurus.audio.tests``.
"""
