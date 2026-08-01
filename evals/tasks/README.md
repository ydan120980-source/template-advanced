# Eval Tasks

The executable eval harness defines eight deterministic, dependency-free cases.
Run it from the repository root:

```bash
bash evals/run-evals.sh
```

## Cases

1. `doctor-root-smoke` — run Template Doctor twice on the current checkout;
   reports must be byte-identical, sorted, contract-complete, and contain at
   least the documented rule floor.
2. `run-guard-lifecycle` — initialize a Run Guard run in an isolated temp
   directory and complete the full start/artifact/handoff/validation/review
   lifecycle; the final gate must be ready.
3. `run-guard-scope-rejection` — recording an artifact outside the declared
   allowed/ownership scope must be rejected.
4. `run-guard-case-semantics` — verify platform-aware path matching and
   artifact identity: case-insensitive on Windows, case-sensitive on POSIX.
5. `release-pollution-detection` — build a release into a temp directory and
   assert the archive contains no planning journals, runtime pointers, or
   bytecode caches.
6. `release-determinism` — build twice into separate temp directories and
   assert identical manifests, digests, and archive bytes.
7. `doctor-drift-detection` — a fixture with a leaked local path must make
   Template Doctor report the local-state drift rule as failed.
8. `clean-template-init` — extract the built archive into a fresh directory,
   run setup and Template Doctor there, and assert the only failing finding is
   the deferred Git baseline; the CodeGraph index is an optional capability
   reported as a non-blocking skip.

Every case is read-only for the repository except the release cases, which
write only to temporary directories. Temporary evidence is removed on exit.
