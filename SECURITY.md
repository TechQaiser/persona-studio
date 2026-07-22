# Security Policy

## Reporting a vulnerability

If you find a security issue, please **do not** open a public issue. Instead,
email the maintainer or use GitHub's private "Report a vulnerability" feature
under the Security tab. Include steps to reproduce and the potential impact.

You can expect an acknowledgement within a few days and an update on the fix
timeline after triage.

## Scope

Persona stores profile data (including proxy credentials) locally in plain JSON
under `~/.persona`. Treat that directory as sensitive. Encrypted-at-rest storage
and secret handling improvements are tracked on the roadmap — contributions
welcome.
