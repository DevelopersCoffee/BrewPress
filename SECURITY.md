# Security Policy

## Reporting

If you discover a security issue in BrewPress, please do not open a public issue with exploit details.

Report it privately to the project maintainers first.

## Sensitive Areas

Please take extra care around:

- WordPress credentials
- application passwords
- execution-layer command handling
- artifact logging and trace storage
- content or media publishing flows

## Safe Defaults

- never commit secrets
- keep local credentials outside version control
- prefer draft-first publishing
- keep execution steps observable
- use environment variables or secure secret stores for all credentials
- redact secrets from logs, screenshots, artifacts, and failure bundles
- use standard secure WordPress REST authentication only
