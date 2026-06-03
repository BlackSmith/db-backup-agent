# Task 11 - CI Nightly GHCR Push: implementation record

## Implemented

- Updated `.github/workflows/ci.yml` so branch pushes build and push the Docker image to GitHub Container Registry with the `nightly` tag.
- Kept pull requests as build/test validation only, without pushing images.
- Updated the README CI section to document the `nightly` image name.

## Changed files

- `.github/workflows/ci.yml`
- `README.md`

## Verification

- Reviewed workflow YAML for the push vs pull request split.
- No local Docker build was run here because the environment does not provide the `docker` CLI.

## Open issues / follow-ups

- The CI workflow now requires GitHub Actions to have package write permissions on branch push events.
- The repository owner must enable GitHub Actions package publishing for GHCR in repository settings.
- If a stricter release strategy is desired later, the nightly tag can be changed to a branch-specific tag or a timestamped tag.
