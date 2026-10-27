# Contributing

1. Open a focused issue describing the user problem, expected observation and an evidence-based acceptance test.
2. Keep public demo fixtures synthetic and visibly labeled. Never add real account data, keys, screenshots containing secrets, or fabricated outage/security claims.
3. Keep network I/O in adapters and deterministic rules in the intelligence layer. New provider rules need false-positive tests and evidence attribution.
4. Add tests for tenant isolation, unknown/partial results, resource limits and explicit failure states when changing those behaviors.
5. Run the verification commands in the README. Keep changes scoped; do not reformat unrelated projects.
6. Submit a pull request describing the behavior change, tests run, limits and migration/rollback considerations.

For private-data exposure concerns, avoid posting credentials or customer evidence in a public issue. Contact the repository owner privately.
