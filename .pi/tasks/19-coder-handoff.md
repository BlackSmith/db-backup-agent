# Coder Handoff for Task 19

## Objective
Update the runtime image so it ships the newest practical packaged `pg_dump` / `pg_dumpall` version available for the selected image strategy, fixing the confirmed PostgreSQL client/server version mismatch.

Confirmed failure:

```text
pg_dump: error: aborting because of server version mismatch
pg_dump: detail: server version: 17.10; pg_dump version: 15.18 (Debian 15.18-0+deb12u1)
```

## Root cause summary

The image currently installs Debian bookworm's default `postgresql-client`, which provides `pg_dump` 15.x. That is too old for PostgreSQL 17 targets.

This is primarily a packaging/runtime dependency issue.

## Primary target

Update the runtime image and any directly related documentation so the backup agent includes the newest practical packaged PostgreSQL client toolchain, with explicit compatibility for PostgreSQL 17.

## Recommended implementation order

1. Update `Dockerfile`
2. Update `README.md` runtime image notes if needed
3. Update any deployment comments or examples that would otherwise become misleading
4. Run focused verification plus the full test suite
5. Write `.pi/done/19-postgresql-client-version-compatibility.md`

## Preferred implementation direction

Choose the smallest reliable packaging fix.

Good options include:

- install `postgresql-client-17` directly if that is the newest practical packaged option in the chosen base image environment
- or add the PostgreSQL upstream APT repository and install the newest practical explicit client package there
- or adopt another minimal packaging strategy that guarantees a sufficiently new `pg_dump`

## Constraints

- Keep changes localized.
- Do not redesign the PostgreSQL provider unless packaging alone cannot solve the issue.
- Preserve secret-safe execution.
- Do not break MariaDB or rsync runtime dependencies.
- Keep the container build reproducible.

## Acceptance criteria

- [ ] `pg_dump` in the runtime is the newest practical packaged version for the chosen strategy and is compatible with PostgreSQL 17
- [ ] The reported version-mismatch failure is resolved
- [ ] Documentation reflects the packaging/runtime dependency choice
- [ ] Full suite passes with `python -m unittest discover -s tests`
- [ ] A done note is written under `.pi/done/19-postgresql-client-version-compatibility.md`

## Suggested verification

At minimum:

```bash
python -m unittest discover -s tests
```

If the environment allows it, also verify the client version directly, for example:

```bash
docker run --rm <image> pg_dump --version
```

And ideally re-run a real PostgreSQL backup against the affected PostgreSQL 17 target.

## Design caveat

Do not treat this as a metadata problem. The metadata and provider invocation can be correct while the runtime still fails because the packaged client is too old.
