# Configuring the model / provider

oss-steward runs through the `claude` CLI, so it uses whatever model that CLI is
configured to use. Configuration lives in the **target repo's**
`.claude/settings.json` (created by `/oss-steward:ops-setup` from
`templates/settings.json`) plus one credential supplied as an environment
variable / CI secret.

## How it resolves

Claude Code reads model settings from two places. **Process environment wins
over `settings.json`.** So:

- Non-secret model selection (endpoint, model names, timeouts) → commit it in
  `.claude/settings.json` under `"env"`. Version-controlled, reviewable.
- The secret credential → never commit it. Provide it as a process env var
  (locally `export …`, in CI a repo **secret**).

The credential variable depends on the endpoint's auth scheme:

| Variable | Header sent | Use for |
|---|---|---|
| `ANTHROPIC_API_KEY` | `x-api-key` | the official Anthropic API |
| `ANTHROPIC_AUTH_TOKEN` | `Authorization: Bearer …` | most third-party Anthropic-compatible gateways |

## Default (official Anthropic API)

`.claude/settings.json`:

```json
{
  "permissions": { "allow": ["Bash", "Read", "Write", "Edit", "Glob", "Grep"] },
  "env": {
    "ANTHROPIC_MODEL": "claude-sonnet-4-6",
    "API_TIMEOUT_MS": "600000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

Credential: set `ANTHROPIC_API_KEY` (repo secret `ANTHROPIC_API_KEY`).

## Third-party endpoint (example: MiniMax)

Point at any Anthropic-compatible endpoint by adding `ANTHROPIC_BASE_URL` and the
model name(s) to the committed `"env"` block. The four `ANTHROPIC_*_MODEL` keys
cover the model tiers Claude Code may request, so set them all to your endpoint's
model when it offers a single model:

```json
{
  "permissions": { "allow": ["Bash", "Read", "Write", "Edit", "Glob", "Grep"] },
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.minimaxi.com/anthropic",
    "ANTHROPIC_MODEL": "MiniMax-M3",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "MiniMax-M3",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "MiniMax-M3",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "MiniMax-M3",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "512000"
  }
}
```

Credential: the MiniMax API key goes in `ANTHROPIC_AUTH_TOKEN` (repo secret
`ANTHROPIC_AUTH_TOKEN`) — **not** in the committed file.

## Variable reference

| Variable | Meaning |
|---|---|
| `ANTHROPIC_BASE_URL` | Override the API endpoint (the gateway/proxy base URL). Omit for the official API. |
| `ANTHROPIC_MODEL` | Primary model id used for the main agent loop. |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` / `…_OPUS_MODEL` / `…_HAIKU_MODEL` | Model id Claude Code uses when it asks for a sonnet/opus/haiku-class model (background tasks, subagents). Set to your endpoint's model when it has one tier. |
| `API_TIMEOUT_MS` | Per-request timeout. Raise it for slower third-party endpoints. |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` | `"1"` disables non-essential network calls — recommended for unattended CI runs. |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | Token window at which the conversation auto-compacts; match it to your model's context size. |

The CI workflow (`templates/ops-run.yml`) passes through both
`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` secrets and exports only the one
that is set, so the same workflow works for either auth scheme without edits.
