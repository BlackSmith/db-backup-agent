# Task 08: Containerization and Example Deployment

## Goal
Prepare the application for containerized execution and provide an example deployment configuration.

## Scope
- Add a production-oriented Dockerfile
- Ensure required backup tools are present in the image
- Document mounted volumes, Docker socket access, and environment variables
- Provide an example Docker Compose deployment

## Deliverables
- Dockerfile
- `.dockerignore` if appropriate
- example `docker-compose.yml` or equivalent deployment example
- deployment documentation section in README

## Required runtime capabilities
- access to Docker socket for discovery
- network access to database containers
- writable local backup directory / volume
- availability of:
  - `pg_dump`
  - `pg_dumpall`
  - `mariadb-dump`
  - `rsync`

## Constraints
- The image should be as small and simple as practical
- Do not hardcode secrets into image or example deployment files
- Example deployment must reflect the architecture assumptions

## Acceptance criteria
- The container image builds successfully
- The example deployment shows all required mounts and environment variables
- The runtime image contains the required backup tools
- Documentation is sufficient for a developer to run the agent in a local Docker environment

## Suggested notes for implementer
- If tool installation differs by base image, document the chosen trade-off
- Keep the example deployment minimal but realistic
