# v-flow

Move footage and photos between camera cards, long-term storage, and editing drives without ever losing track of the safe copy.

## Wait, what does it do?

v-flow is a CLI for people who shoot a lot of video and photos. It copies your camera card into a protected archive and proves the copy with checksums. It puts temporary copies on your editing SSD, saves finished videos and DaVinci Resolve backups, and deletes an editing copy only after verifying the archived original. Nothing is ever moved or deleted as a side effect of anything else.

You can drive it from the terminal, or just talk to Claude Code, Codex, or Cursor. The bundled skill teaches your agent the whole workflow.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/kaungzinye/v-flow/main/install_vflow.sh | bash
```

That installs the `v-flow` command plus the agent skill. Claude Code and Cowork users can grab the plugin instead, and the skill installs the CLI from PyPI on first use:

```
/plugin marketplace add kaungzinye/v-flow
/plugin install vflow@v-flow
```

Then point it at your drives:

```bash
v-flow make-config
```

## Use it

Ingest a card. Footage lands in a Shoot, photos in a Collection, one command:

```bash
v-flow ingest --source "/Volumes/SDCARD" --auto
```

Put a Shoot on your editing drive, and clean it up when you're done (cleanup verifies checksums and your Resolve project first):

```bash
v-flow checkout --shoot "2026-08-02_Ingest" --working-location work_ssd
v-flow cleanup  --shoot "2026-08-02_Ingest" --working-location work_ssd --project "Summer Film"
```

Or skip the flags entirely and ask your agent:

> Ingest this card, then put the footage on my SSD.

Every state-changing command supports a dry run, names the safety gate that failed, and leaves your card and archive intact on any error.

## Notes

This is a personal tool that grew documentation. It works on macOS, it's tested, and it guards your media obsessively. Still, expect sharp edges in places one person's workflow never reached.

## Docs

- [The agent skill](skills/vflow/SKILL.md): the workflow reference, branch by branch
- [Domain language](CONTEXT.md): what Shoot, Collection, Archive, and friends mean precisely
- Every command: `v-flow --help`

## Contributing

Issues and PRs welcome. Read [CONTEXT.md](CONTEXT.md) first. The vocabulary is load-bearing.
