# Historical evidence

`generated_traces.json` and `results.json` predate the security-routing fixes.
The grades are saved model-judge results, not a fresh test or independent audit.
Known SSN/card patterns were redacted **after capture** during remediation.
This cleanup does not prove that the original run prevented disclosure and does
not erase Git history. The old judge inferred model exposure from SSN-related
wording rather than capturing the outbound model request.

`baseline_reproduction_summary.json` was created during remediation. It records
fresh offline boundary reproductions of that original source using the current
locked SDK and a recording stub, not historical live inference.

See `SECURITY_REMEDIATION_REPORT.md` in the repository root.
