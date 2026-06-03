# Task 10: GitHub Actions CI, Docker Build, and Release

## Goal
Add GitHub Actions automation that validates the project on every pull request / push, builds the Docker image, and creates a release when a version tag is pushed.

## Scope
- Add GitHub Actions workflow files under `.github/workflows/`.
- Run Python tests in CI.
- Build the Docker image in CI.
- On version tags, publish the Docker image to GitHub Container Registry (GHCR).
- On version tags, create a GitHub Release.
- Document the workflow behavior in `README.md` or a short repository docs section.

## Recommended workflow behavior

### Pull requests and normal branch pushes

Trigger on:

- `pull_request`
- `push` to main branches such as `main` and/or `master`

Steps:

1. Check out repository.
2. Set up Python 3.13.
3. Install the package in editable mode.
4. Run tests:
   - `python -m unittest discover -s tests`
5. Build the Docker image without pushing it:
   - validate that the Dockerfile builds successfully
   - use a deterministic local image tag such as `backup-agent:ci`

### Version tag pushes

Trigger on tags such as:

- `v*`

Steps:

1. Run the same test suite.
2. Build the Docker image.
3. Push image to GHCR:
   - `ghcr.io/<owner>/<repo>:<tag>`
   - optionally also push `latest` for stable tags if desired
4. Create a GitHub Release for the tag.

## Required GitHub Actions permissions

The release/tag workflow will likely need:

```yaml
permissions:
  contents: write
  packages: write
```

Use the built-in `GITHUB_TOKEN` where possible. Do not require custom secrets unless strictly necessary.

## Suggested actions

Use well-supported official/community actions:

- `actions/checkout`
- `actions/setup-python`
- `docker/setup-buildx-action`
- `docker/login-action`
- `docker/metadata-action`
- `docker/build-push-action`
- `softprops/action-gh-release` or GitHub CLI-based release creation

## Deliverables

- `.github/workflows/ci.yml` or equivalent for tests and Docker build.
- Optional separate `.github/workflows/release.yml` if clearer than one combined workflow.
- README documentation describing:
  - CI triggers
  - tag/release flow
  - resulting GHCR image name
  - expected tag format

## Constraints

- Do not hardcode secrets.
- Do not publish images from pull requests.
- Keep workflows minimal and maintainable.
- The Docker image build must use the repository `Dockerfile`.
- Release creation must happen only for tag pushes.
- CI must fail if tests fail or the Docker image cannot be built.

## Acceptance criteria

- Pull requests run Python tests and Docker build validation.
- Pushes to the main branch run Python tests and Docker build validation.
- Tag push, for example `v0.1.0`, runs tests, builds the Docker image, pushes it to GHCR, and creates a GitHub Release.
- Workflow uses GitHub-native authentication (`GITHUB_TOKEN`) for GHCR and release creation.
- README documents how to create a release tag and where the container image is published.

## Suggested verification

After implementation, verify locally as much as possible:

- `python -m unittest discover -s tests`
- `docker build -t backup-agent:ci .`

For GitHub Actions syntax, use one of:

- review workflow YAML manually
- `gh workflow` / GitHub UI validation if available
- `act` if available in the environment

## Notes for coder

The current repository uses Python 3.13 and standard-library `unittest`; no additional CI dependency manager is required for test execution.
