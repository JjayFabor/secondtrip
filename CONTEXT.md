# SecondTrip Domain Language

SecondTrip identifies plausible repeat service work while keeping machine evidence separate from
human-confirmed truth.

## Detection

**Rework candidate**:
A stable, canonically ordered pair of service jobs that the detection engine has evaluated as a
possible callback or other repeat work.
_Avoid_: Callback, confirmed callback

**Signal**:
A named, code-owned test that contributes evidence about a rework candidate under a versioned
rule configuration.
_Avoid_: Rule, detector

**Signal outcome**:
The result of evaluating a signal: `matched`, `not_matched`, or `not_evaluable`.
_Avoid_: Match boolean

**Not evaluable**:
The signal could not be tested because required evidence is absent; it is excluded from both the
score numerator and denominator.
_Avoid_: No match, failed

**Review**:
A human judgement about a rework candidate, stored as append-only truth independently of machine
scores and AI suggestions.
_Avoid_: Detection result, AI classification
