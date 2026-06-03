# Task 10 - GitHub Actions CI, Docker Build, and Release: implementation record

## Implemented

- Added a CI workflow at `.github/workflows/ci.yml`.
- Added a release workflow at `.github/workflows/release.yml`.
- CI workflow triggers on pull requests and pushes to `main` / `master`.
- CI workflow runs:
  - Python package installation in editable mode
  - Python test suite
  - Docker image build validation with `backup-agent:ci`
- Release workflow triggers on version tag pushes matching `v*`.
- Release workflow runs the test suite, builds the Docker image, pushes it to GHCR, and creates a GitHub Release.
- Updated `README.md` with a short CI/release section describing:
  - workflow triggers
  - the GHCR image name
  - the version tag format

## Changed files

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `README.md`

## Verification

- Ran the Python test suite successfully:
  - `python -m unittest discover -s tests`
- Attempted to run a local Docker build validation:
  - `docker build -t backup-agent:ci .`
  - This could not be executed in the current environment because the `docker` CLI is not available here.

## Open issues / follow-ups

- The release workflow assumes GitHub Actions runners have Docker access, which is normally true for `ubuntu-latest`.
- The CI workflow uses `permissions: {}` because it does not need write access; the release workflow uses `contents: write` and `packages: write`.
- If the project later switches the default branch name, the branch filters should be updated accordingly.
