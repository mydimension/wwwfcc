"""Throwaway diagnostic - print the raw grwave() output so we can see
every column and a spread of distance/field-strength values, to check
units and column meaning before trusting am_groundwave.py's assumptions.
Delete this once the AM groundwave model is verified.
"""
from grwave import grwave

df = grwave({
    "freqMHz": 0.770,
    "sigma": 3e-3,
    "epslon": 15,
    "dmax": 500,
    "hrr": 2,
    "htt": 0,
    "dstep": 5,
    "txwatt": 1000,
})
print("columns:", list(df.columns))
print(df.to_string())
