# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| v1.0.0  | Yes       |

Only tagged releases are supported. The current development branch receives
security fixes before the next release.

## Reporting A Vulnerability

Use the repository's **private vulnerability reporting** channel
(GitHub > Security > Report a vulnerability) when it is enabled. Do not
disclose an unremediated vulnerability, exploit, credential, private path,
session file, or production data in a public issue or pull request.

Include:

- the affected version or commit;
- impact;
- minimal reproduction steps;
- platform and Python version;
- a suggested mitigation if you have one.

Redact secrets and personal data; attach only the minimum sanitized evidence
needed.

## Response Expectations

After a report is received privately, a maintainer should:

1. acknowledge receipt;
2. reproduce the issue in isolation;
3. assess affected contracts and scope;
4. prepare a bounded fix with regression coverage;
5. coordinate disclosure only after a remediation is available.

No response-time service level is promised; this is a small maintainer-run
project.

## What Is Not A Security Issue

- Missing optional capabilities such as a local CodeGraph index (documented as
  non-blocking).
- Host-level Codex configuration, Hooks, memory, or MCP servers outside this
  repository's control.
- GitHub repository settings that are not enabled (for example, a security
  feature gated by account type).
- General usage questions and feature requests; use Issues for those.

## Release Archive Verification

Before trusting any downloaded release:

1. Verify `SHA256SUMS`:

   ```bash
   sha256sum -c SHA256SUMS
   ```

2. Run the archive verifier:

   ```bash
   python scripts/verify-release-archive.py \
     --archive template-advanced-1.0.0.zip \
     --manifest template-advanced-1.0.0.manifest.json \
     --validate
   ```

3. Extract and re-run setup, verify, eval, and Template Doctor in the clean
   directory.

See [GitHub Release Readiness](docs/ai-workflow/GITHUB_RELEASE_READINESS.md).

## Safe Testing

- Test only systems and data you own or are authorized to assess.
- Do not access global Codex configuration, user sessions, secrets, production
  data, or external services without explicit authorization.
- Prefer sanitized fixtures and read-only probes.

Repository-specific handling guidance is documented in
`docs/security/README.md`.
