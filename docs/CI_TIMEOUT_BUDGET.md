# CI job timeout budget

The job ceiling changes from 10 to 20 minutes. Test commands, six-row OS/Python
matrix, action commit pins, triggers, contents: read permission and credential
persistence setting are unchanged. There is no automatic retry or extra job.
Product ZIP/member/JSON bounds and product tests are unchanged. Only the CI
contract test expectations are updated to require exactly the new timeout; its
original ten-minute baseline remains preserved. This is scheduling
headroom, not a speed improvement, pass guarantee or reason to ignore failures.

## Observed evidence (2026-11-15 UTC)

GitHub job/step timestamps below are rounded to seconds. Carried-forward jobs
reissued with new IDs by a rerun are deduplicated by name/start time, rather than
counted as fresh work. Two actual cancellations occurred near the 600-second
job ceiling; logs ended with KeyboardInterrupt, not a test assertion failure.
A cancelled job is not a pass. Its audit/manifest steps were skipped.

| Run / job | Matrix row | Status | Job seconds | Checkout | Python setup | Tests | Audit | Manifest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 43655457055 / 132632857244 | test (windows-latest, 3.12) | cancelled | 604 | 10 | 0 | 589 cancelled | skipped | skipped |
| 43655457055 / 132632857453 | test (ubuntu-latest, 3.10) | success | 118 | 1 | 6 | 107 | 1 | 0 |
| 43655457055 / 132632857463 | test (ubuntu-latest, 3.12) | success | 85 | 3 | 1 | 76 | 0 | 0 |
| 43655457055 / 132632857512 | test (windows-latest, 3.15) | success | 398 | 7 | 0 | 385 | 1 | 0 |
| 43655457055 / 132632857516 | test (ubuntu-latest, 3.15) | success | 113 | 1 | 0 | 108 | 1 | 0 |
| 43655457055 / 132632857563 | test (windows-latest, 3.10) | success | 404 | 6 | 33 | 360 | 0 | 1 |
| 43655457055 / 132636030005 | test (windows-latest, 3.12) | success | 429 | 7 | 0 | 417 | 0 | 1 |
| 43657342885 / 132638702906 | test (windows-latest, 3.10) | success | 405 | 9 | 43 | 345 | 1 | 0 |
| 43657342885 / 132638703034 | test (ubuntu-latest, 3.10) | success | 109 | 0 | 6 | 98 | 0 | 0 |
| 43657342885 / 132638703082 | test (ubuntu-latest, 3.12) | success | 89 | 1 | 0 | 84 | 0 | 0 |
| 43657342885 / 132638703121 | test (ubuntu-latest, 3.15) | success | 131 | 1 | 0 | 127 | 0 | 0 |
| 43657342885 / 132638703170 | test (windows-latest, 3.15) | cancelled | 605 | 8 | 0 | 591 cancelled | skipped | skipped |
| 43657342885 / 132638703193 | test (windows-latest, 3.12) | success | 459 | 16 | 0 | 436 | 1 | 1 |
| 43657342885 / 132641382606 | test (windows-latest, 3.15) | success | 286 | 5 | 0 | 276 | 1 | 0 |

The first cancelled job spent 589 seconds in tests, the second 591; setup and
cleanup also consume job time. Among completed successful rows in this observation,
the longest test step was 436 seconds and job 459 seconds. The earlier Windows
3.12 retry completed in 429 seconds, demonstrating run-to-run variation, not
proof of an infrastructure cause. The later Windows 3.15 retry completed in
286 seconds (276-second test step). Cancellation locations differed (ZIP reading
versus title-review provenance); no product change is inferred from these timings.

This public repository uses standard ubuntu-latest/windows-latest runners.
[GitHub billing documentation](https://docs.github.com/en/actions/concepts/billing-and-usage)
states standard hosted runners in public repositories are free. No paid runner,
billing setting, subscription or permission is added. A higher ceiling can consume
more compute before a stuck job is stopped. These observations are not a general
billing promise for other repository visibility or runner configurations.
