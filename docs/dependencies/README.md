# Advanced Dependency Policy

This document defines dependency handling rules for Advanced template projects.

## When Dependencies May Be Added

Add a dependency only when the Task Packet explicitly allows dependency changes or when the User approves the exact package, purpose, and scope.
Prefer standard library, existing project dependencies, or local helpers when they are sufficient.

## Lockfile Policy

- Lockfiles must stay consistent with dependency manifests.
- Do not hand-edit lockfiles unless the package manager officially supports that workflow.
- If a dependency manifest changes, run the appropriate package manager command to regenerate lockfiles.
- Report lockfile changes in the Evidence Ledger.

## Package Manager Policy

- Use the package manager already established by the repository.
- Do not introduce a second package manager without explicit approval.
- Do not upgrade package manager versions, runtimes, or registries unless the task authorizes it.

## Dependency Review Requirements

Before accepting dependency changes, reviewer should check:

- why the dependency is needed;
- whether an existing dependency can satisfy the need;
- license and maintenance risk;
- security advisories or known vulnerabilities;
- bundle/runtime impact;
- transitive dependency risk;
- whether tests and lockfiles were updated.

## Generated Dependency Files

Generated dependency files include lockfiles, vendored metadata, package manager caches, generated SBOMs, and tool-managed manifests.
Modify them only through the expected toolchain unless the task explicitly requests a manual correction.

## Forbidden Dependency Changes Without Explicit Approval

- Adding, removing, or upgrading dependencies.
- Changing lockfiles.
- Changing package manager configuration.
- Changing registries, mirrors, or auth settings.
- Vendoring external code.
- Altering Docker, CI, or deployment dependency installation steps.
- Replacing established runtime versions.
