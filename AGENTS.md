# Jort contributor and agent guide

## Public interfaces

Before proposing a new API, inspect `jort/__init__.py`,
`docs/source/public_api.rst`, and `tests/test_public_contract.py`.

Jort already has these supported notification interfaces:

- Python: `jort.track_new(command, send_email=False, send_text=False)`
- Python callbacks: `jort.EmailNotification()` and `jort.TextNotification()`
- CLI: `jort track --email [--text] <job>`

The `--email` and `--text` options are independent and may be used together.
Do not introduce a second command-running API merely to add notification
selection. Extend `track_new` or the existing callbacks unless the requested
behavior cannot be expressed through those interfaces.

## Verification checklist

When changing command execution or notifications:

1. Check the public exports in `jort/__init__.py` before designing new names.
2. Preserve the existing `track_new` and CLI options unless a breaking change
   is explicitly requested.
3. Add or update a contract test for any public interface change.
4. Test email-only, text-only, both, and neither notification paths.
5. Keep machine-specific paths, credentials, and phone numbers out of docs and
   tests.

## Agent operation

When the user explicitly asks for an email after a long-running command or
benchmark, use the existing CLI from that command's project directory. For a
job that may outlive the agent session, use the detached worker:

```bash
jort track --email 'python benchmark.py'
jort track --detach --email --json 'python benchmark.py'
```

Use `--text` only when SMS is also requested. Use `--shell` for shell syntax
such as `cd` or `&&`. Use `--json` when the result must be parsed, and use the
returned job ID with `jort status` or `jort logs`. Do not put credentials in
repository files or command arguments.

Use `--argv --` when an exact argument vector is important and the command
contains option-like arguments, for example `jort track --argv -- python -c ...`.
