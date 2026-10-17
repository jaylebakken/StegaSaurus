"""Contain iteration 005 of contrastive local-pilot calibration.

The experiment measures whether encoder-side calibration can predict the
decoder's actual two-candidate local-pilot choice by rewarding a selected
candidate only when its expected pilot score exceeds its rival's score after a
complete spectral round trip.
"""
