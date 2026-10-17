"""Contain iteration 007 of offline non-oracle pilot-score telemetry.

The experiment records blind local-pilot candidate evidence at physical carrier,
logical carrier, and Reed--Solomon byte layers. Retained encoder maps and token
bits are consulted only after reconstruction to label the data for future
threshold-policy design; they are never passed to the decoder.
"""
