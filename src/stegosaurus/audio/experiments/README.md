# Audio Experiment Archive

Each numbered subdirectory is one reproducible experiment iteration:

```text
iteration_NNN_short_name/
|- __init__.py
|- run.py      # exact experiment script
|- SUMMARY.md  # measured findings and next decision
`- RESULTS.json  # optional machine-readable output for a large sweep
```

`run.py` begins with its goal and the pipeline state that existed when the experiment was conducted. Do not overwrite a completed iteration to test a new idea; add the next numbered directory so prior measurements remain traceable. Regression and integration tests intentionally remain in `../tests/`.
