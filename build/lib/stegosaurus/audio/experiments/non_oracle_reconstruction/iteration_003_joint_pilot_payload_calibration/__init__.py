"""Contain iteration 003 of joint local-pilot and payload-margin calibration.

The experiment evaluates whether the encoder can make local selection pilots
usable by selecting each candidate frame from the weaker of its measured pilot
and payload margins after the complete STFT round trip. It retains the oracle
map only for post-hoc scoring after non-oracle decoding.
"""
