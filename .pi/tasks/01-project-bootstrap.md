# Task 01: Project Bootstrap

## Goal
Create the initial application skeleton for the backup agent as a modular monolith.

## Scope
- Create the base source tree aligned with `.pi/architecture.md`
- Add the main entrypoint
- Add package/build metadata for the selected implementation stack
- Add a minimal configuration for local development and test execution
- Add basic README sections needed to run the project locally

## Required structure
Create a structure equivalent to:

```text
src/
  app/
  domain/
  services/
  providers/
  infrastructure/
  interfaces/
```

## Deliverables
- Buildable project skeleton
- Main application entrypoint
- Dependency manifest
- Minimal README with local run instructions
- Placeholder modules/interfaces for:
  - scheduler
  - discovery
  - metadata resolver
  - database providers
  - storage provider

## Constraints
- Keep the implementation lightweight
- Do not implement full business logic yet
- Favor interfaces/contracts where later tasks will plug in behavior

## Acceptance criteria
- The project builds successfully
- The application starts without performing backups yet
- Module boundaries reflect the architecture document
- A coder can continue with later tasks without restructuring the project

## Suggested notes for implementer
- If no stack is mandated by the repository, choose a simple and well-supported one
- Keep file and module naming explicit and predictable
