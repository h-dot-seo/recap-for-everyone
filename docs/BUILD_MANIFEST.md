# Review and build a publication manifest

`build_manifest.py` makes the contributor-side byte inventory reproducible without
an unpublished maintainer script. It does not approve files for public release.
The default invocation only reports a plan; it does not change any file.

1. Edit a checked-out source tree and run the generator's default plan.
2. Review every added, removed and changed path and its contents. The limited
   publication audit is not a privacy, consent, anonymity or rights review.
3. Supply that exact `plan_sha256` to write a new candidate outside the source tree.
4. Review the candidate, then explicitly replace the repository manifest yourself
   and run `python verify_manifest.py`, `python audit_publication.py` and the full
   test suite. The generator never performs the replacement or publishes anything.

```text
python build_manifest.py --root CHECKOUT --release SUPPLIED_LABEL --date YYYY-MM-DD
python build_manifest.py --root CHECKOUT --release SUPPLIED_LABEL --date YYYY-MM-DD --write OUTSIDE_NEW_JSON --expected-plan-sha256 REVIEWED_PLAN_SHA256
```

The plan binds the original manifest bytes and the complete candidate bytes,
including supplied release/date metadata. A changed checkout, base manifest or
label invalidates the reviewed plan. Keep release/date arguments identical for
both calls. Omitted metadata retains the base values; no clock is consulted.
Existing project, license and privacy flags are copied, not inferred or approved.
The plan lists paths, so run it only on the tree you intend to inspect.

The tool requires the same tree to pass the existing limited publication audit,
refuses CR bytes and unsafe paths, and validates the candidate using the existing
verifier. Symlinks, nonregular files, prohibited assets and unreviewable path
collisions fail closed. It does not parse `.gitignore` or automatically approve
new files. A new output is staged and exclusively linked outside the checkout;
existing paths and dangling links are refused. Inspect any reported leftover
staging file. Concurrent hostile changes to directory names or files are not
sandboxed; use a stable checkout, not an actively mutating tree. This scans and
hashes complete files, not a memory or time sandbox.

## Executable fictional example

This example creates a deliberately tiny fictional checkout outside the repository,
with exactly one added, removed and changed text file. The final Python command
checks that fixed synthetic plan before using its lease. It is not a substitute
for reviewing real changes. It writes only a separate candidate and leaves the
fictional checkout's old manifest unchanged.

```sh
python examples/make_manifest_demo.py OUTPUT/manifest-demo
python build_manifest.py --root OUTPUT/manifest-demo
python -c "import json; from build_manifest import plan_manifest, build_manifest; p=plan_manifest('OUTPUT/manifest-demo'); assert p['added']==['added.txt'] and p['removed']==['removed.txt'] and p['changed']==['changed.txt']; print(json.dumps(build_manifest('OUTPUT/manifest-demo','OUTPUT/candidate.json',p['plan_sha256'])))"
```

## Release decisions remain separate

The owner decides whether each merge must get a distinct release label. Reusing a
label can otherwise identify different bytes on different commits. Tag format,
when to tag, branch deletion, repository description and licensing are not chosen
by this generator. Tags, if chosen, should refer to an exact commit whose required
CI passed; the manifest hash can be recorded with that decision. No Git command,
CI permission, package publication or deployment is added here.
