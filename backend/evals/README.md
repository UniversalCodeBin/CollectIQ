# Interpretation evals

`synthetic_set.json` is a small hand-written set. `run_eval.py` runs a scripted provider over it and
writes a report with `"synthetic": true`. A synthetic report can never satisfy AIR-12:
`collectiq.ai.eval_gate.auto_snooze_available` returns False for it. Only a report built from real,
consented workspace data may turn that on, and none exists yet.
