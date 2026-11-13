# V72.6.10 offline trace verifier

Recovered from JARVIS_BLUE_V72_6_10_Trace_Verifier.zip. The original staging
branch omitted the six modules required to import the verifier. This directory
now contains that dependency closure, with its seven original test modules in
root tests/test_v72_*.py (imports adjusted to this namespace).

Run from the repository root:

```sh
python -m unittest discover -s tests -p 'test_v72_*.py' -v
```

This is an offline recording model, not a Windows native backend or sandbox.
execute_native always raises NativeExecutionUnavailable. A valid assessment
means a simulated trace is internally consistent; it does not establish that
cleanup succeeded, a process ran, or VM isolation exists. Caller-provided
capability flags are not independent attestation.

The desktop application does not call this experiment. Windows VM testing,
real handle ownership/cleanup, process-tree termination and independently
verified isolation remain prerequisites for any future native implementation.
No Windows build or native execution test is included in this merge.

Validation (Linux, Python 3.12): 61 recovered offline tests passed; combined
root suite including desktop regression tests: 121 passed with Qt offscreen.
V73.1 early-access suite: 15 passed separately. Provider calls were mocked;
these results do not establish native Windows or live-provider readiness.
