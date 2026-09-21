# Security

LabForge will eventually compile and execute generated Java code. That is a high-risk operation and must be isolated from report generation and storage.

## Generated-code Execution Risks

Generated or user-supplied code may:

- Run forever or consume excessive CPU.
- Allocate excessive memory.
- Read or write unintended files.
- Attempt network access.
- Spawn child processes.
- Print misleading output.
- Exploit local tooling or environment assumptions.

LabForge must never treat generated code as trusted.

## Local MVP Isolation

For a local MVP, execution should use temporary directories outside the source tree, strict timeouts, controlled input, and explicit cleanup. Generated Java files, class files, and execution logs should not be written into `examples/` or `templates/`.

The MVP should separate:

- Source references
- Template files
- Temporary compilation directories
- Captured output
- Final artifacts

## Future Sandbox Requirements

Production execution should use a stronger sandbox than a local temporary directory. A future sandbox should provide:

- Filesystem isolation
- CPU and memory limits
- Wall-clock timeout
- Process count limits
- Network denial by default
- Clean environment variables
- Auditable stdout, stderr, and exit status

Container, VM, or dedicated sandbox workers should be evaluated before production use.

## File-system Isolation

Execution code should receive only the files required for compilation and runtime. It should not have write access to references, templates, application code, profile data, or generated reports.

Generated artifacts should be written only to configured artifact locations.

## Timeout and Resource Limits

Each compile and run step should have explicit limits. Timeout failures should be validation failures, not partial successes. Large output should be capped and marked as truncated.

## Network Restrictions

Production execution should deny network access by default. Java lab programs for the first MVP do not require external network access. Any future exception should be explicit, audited, and scoped to the experiment.
