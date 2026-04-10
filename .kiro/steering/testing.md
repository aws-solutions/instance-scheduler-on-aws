---
inclusion: auto
---

# Testing Requirements

After making changes to Python source files under `source/app/`, run the tox test suite to verify tests, formatting, and linting all pass:

```bash
cd source/app && tox
```

This runs black, isort, flake8, and the full pytest suite. All checks must pass before considering a change complete.

If isort reports import ordering errors, auto-fix them with:

```bash
cd source/app && poetry run isort --profile black .
```

If black reports formatting errors, auto-fix them with:

```bash
cd source/app && poetry run black .
```

After making changes to TypeScript/CDK files, run the npm test suite from the repo root:

```bash
npm run test
```

This includes snapshot tests for the CDK stacks. If snapshots are intentionally outdated due to your changes, update them with:

```bash
npm run test:update-snapshots
```
