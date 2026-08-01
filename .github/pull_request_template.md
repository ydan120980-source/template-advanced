## Summary

<!-- What does this change do, and why? -->

## Scope

- Task Packet: <!-- link or ID -->
- Files changed:

## Validation

- [ ] `bash scripts/setup.sh`
- [ ] `python -m unittest discover -s tests`
- [ ] `bash scripts/verify.sh`
- [ ] `bash evals/run-evals.sh`
- [ ] `python -B -m tools.template_doctor --root . --format json`
- [ ] `python scripts/build-release.py` and the archive verifier (if release
      content changed)

## Contract Impact

<!-- Public CLI arguments, exit codes, JSON/JSONL shapes, rule IDs, release
manifest fields, or documentation contracts changed? -->

## Risks And Limitations

<!-- Anything a reviewer should verify, and known limitations. -->

## Checklist

- [ ] No secrets, private paths, caches, or generated artifacts are included.
- [ ] Control documents and tests were updated when behavior changed.
