# portfoliost-contracts

Monorepo containing two independently-published `@marx-org` packages:

| Package | Description | Workflow |
|---------|-------------|----------|
| `contracts/` | `@marx-org/contracts` — OpenAPI spec, FX helpers, currencies | `release-contracts.yml` |
| `otel/` | `@marx-org/otel` — shared OpenTelemetry bootstrap helpers for Hono services | `release-otel.yml` |

Each subfolder has its own `package.json`, `tsconfig.json`, semver version, and CI workflow.

## Development

```bash
# contracts
cd contracts && npm install && npm run build && npm test

# otel
cd otel && npm install && npm run build
```

## Publishing

Push to `main` — CI auto-bumps the patch version, commits, tags, and publishes to GitHub Packages.

- `contracts/**` changes → `@marx-org/contracts` (tagged `v*`)
- `otel/**` changes → `@marx-org/otel` (tagged `otel-v*`)

## Structure

- `.npmrc` — shared GitHub Packages registry config (both packages use `@marx-org` scope)
- `.gitignore` — shared ignore rules
