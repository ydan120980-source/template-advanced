# Expected Eval Outputs

All eight cases in `evals/tasks/README.md` pass only when their stated
contracts hold:

- Doctor reports are byte-identical across runs and use unique, sorted rule
  IDs with the stable result contract.
- The Run Guard lifecycle gate is ready and scope violations are rejected at
  record time.
- Windows and POSIX path semantics are exercised explicitly through platform
  simulation.
- Release archives exclude local runtime state and bytecode, and two builds are
  byte-identical.
- Doctor detects leaked local paths, and a clean extraction initializes with
  only deferred Git/CodeGraph findings.

Expected outputs describe contracts rather than store full transcripts. Do not
add secrets, private data, or machine-specific absolute paths.
