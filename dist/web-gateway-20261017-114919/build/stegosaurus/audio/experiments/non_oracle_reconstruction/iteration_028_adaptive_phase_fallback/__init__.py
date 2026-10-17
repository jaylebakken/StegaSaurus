"""Archive iteration 028's adaptive residual-phase fallback validation.

The decoder retains the normal duration-feasible center path and expands to a
bounded phase list only after it has no RS-successful candidate. This avoids
promoting any fixed phase bias that failed separate fresh-cover validation.
"""
