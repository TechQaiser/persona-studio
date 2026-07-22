# Security Policy

## Reporting a vulnerability

If you find a security issue, please **do not** open a public issue. Instead,
email the maintainer or use GitHub's private "Report a vulnerability" feature
under the Security tab. Include steps to reproduce and the potential impact.

You can expect an acknowledgement within a few days and an update on the fix
timeline after triage.

## Scope

Persona stores profile data locally as JSON under `~/.persona`. Treat that
directory as sensitive.

**Encrypting secrets:** proxy passwords can be encrypted at rest with a master
password — run `pip install -e ".[secure]"` then `persona vault enable`. Secrets
are stored as Fernet tokens (AES) with the key derived via PBKDF2-HMAC-SHA256;
supply the password at use time through `PERSONA_PASSWORD` or `--password`, so it
never touches disk. The rest of each profile stays readable. There is no password
recovery — losing it means losing the encrypted secrets.

Not yet covered: the dashboard's own profile store, cookies (Chromium keeps those
in its own OS-encrypted store), and full-profile encryption. Contributions welcome.
