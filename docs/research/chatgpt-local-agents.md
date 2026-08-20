# Can ChatGPT users drive a local CLI tool (v-flow) against their local files in 2026?

Research date: 2026-08-20. All sources accessed 2026-08-20 unless noted.

---

## 1. What "ChatGPT working on local files" means in 2026

OpenAI ships several distinct surfaces that get conflated in casual conversation. As of mid-2026 they are:

### a) ChatGPT desktop app (Mac/Windows/Linux) — three modes: Chat, Work, Codex

- OpenAI merged the standalone "Codex" desktop app into the main ChatGPT desktop app in July 2026. The unified app exposes three modes — **Chat**, **Work**, and **Codex** — "available on every plan, including Free." (VERIFIED FACT — [Coursiv: Codex Merged With ChatGPT App](https://coursiv.io/blog/codex-merged-with-chatgpt-app), accessed 2026-08-20; corroborated by [TechRepublic: OpenAI Brings ChatGPT, Work, and Codex to Linux in Desktop Preview](https://www.techrepublic.com/article/news-openai-chatgpt-codex-linux-desktop-preview/), accessed 2026-08-20)
- **Work with Apps** (macOS, originally launched late 2024): lets ChatGPT *read* content from designated local apps (VS Code, Xcode, Terminal, iTerm2, Notes, Notion, and others) for context, "with your permission." This is a context-injection feature, not command execution — OpenAI's own framing was that it is "far from an AI agent" but "a key building block" toward one. (VERIFIED FACT, secondary corroboration — [TechCrunch, Nov 2024](https://techcrunch.com/2024/11/14/chatgpt-can-now-read-some-of-your-macs-desktop-apps), accessed 2026-08-20; primary doc at help.openai.com/en/articles/10119604 returned HTTP 403 to automated fetch, so treat the Work-with-Apps *scope* claim as secondary-sourced only)
- **Codex mode** in the desktop app is the one that matters for v-flow: it "can reach local projects, codebases, the file system, and the terminal" — i.e., it links a local project folder and can edit files, run git, and **execute terminal commands** directly on the user's machine. (VERIFIED FACT — [BigGo Finance: ChatGPT Desktop App Arrives on Linux](https://finance.biggo.com/news/d64b4625-6df8-474d-ab4b-a84999d8410b), accessed 2026-08-20, secondary but consistent with the underlying Codex CLI docs below, which is primary)
- Codex-in-desktop is a GUI wrapper around the same underlying **Codex CLI/engine** documented at developers.openai.com/codex (redirects to learn.chatgpt.com/docs/*) — same sandbox, same approval model. (INFERENCE, based on architecture described across OpenAI's Codex docs pages, all under the same `learn.chatgpt.com/docs/*` documentation set)

### b) Codex CLI (`openai/codex` on GitHub) — terminal-native agent

- "Codex CLI is a coding agent from OpenAI that runs locally on your computer," available for Mac, Linux, and Windows. Install via curl script, npm (`npm install -g @openai/codex`), Homebrew (`brew install --cask codex`), or GitHub Releases. (VERIFIED FACT — [github.com/openai/codex](https://github.com/openai/codex), accessed 2026-08-20)
- It **executes arbitrary local shell commands** by design — this is its core function. Access is gated by a two-layer model: a **sandbox** (what it's technically allowed to touch) and an **approval policy** (when it must ask first). (VERIFIED FACT — [learn.chatgpt.com/docs/sandboxing](https://learn.chatgpt.com/docs/sandboxing) and [learn.chatgpt.com/docs/agent-approvals-security](https://learn.chatgpt.com/docs/agent-approvals-security), accessed 2026-08-20)
- Sign-in via a ChatGPT account is the primary path; it works with **Plus, Pro, Business, Edu, or Enterprise** plans, or with a separate API key. (VERIFIED FACT — [github.com/openai/codex README](https://github.com/openai/codex), accessed 2026-08-20). Separately, OpenAI's pricing writeups for 2026 report Codex is also included at a reduced allowance in the **Free** tier and a **Go** tier ($8/mo), with Plus at $20/mo giving "10-60 cloud tasks and 20-50 code reviews per 5-hour rolling window." (VERIFIED FACT re: tiers existing, secondary source — [morphllm.com: Codex Pricing 2026](https://www.morphllm.com/codex-pricing), accessed 2026-08-20; exact numeric limits are not published by OpenAI per that same source, so treat quotas as approximate)

### c) ChatGPT Agent (formerly Operator) — cloud sandbox, NOT local

- When a user starts an "Agent" task in ChatGPT, OpenAI spins up an **isolated, OpenAI-managed cloud sandbox** — a virtual computer with its own browser, terminal, and filesystem. "Agent Mode runs in the cloud, not on your machine. It cannot touch your local files unless you upload them, and its outputs come back to you as downloads and results in the chat." (VERIFIED FACT, secondary but well-corroborated — [agensi.io: ChatGPT Agent Mode Explained](https://www.agensi.io/learn/chatgpt-agent-mode), accessed 2026-08-20)
- The underlying browsing agent "cannot access the file system, local applications, or other network services — only the webpage visible in its browser window." (VERIFIED FACT, secondary — same source, and corroborated by [OpenAI Operator Wikipedia summary of OpenAI's own containment design](https://en.wikipedia.org/wiki/OpenAI_Operator), accessed 2026-08-20)
- This means **ChatGPT Agent cannot drive v-flow at all** — it has no path to `/Volumes/...` or any local shell. It is architecturally the wrong surface for this task, full stop.
- Selectable from the composer on paid plans, Plus ($20/mo) and up (i.e., not Free). (VERIFIED FACT, secondary — same agensi.io source, accessed 2026-08-20)

### d) Anything else new in 2025–2026

- No new first-party OpenAI surface was found beyond the above that executes local shell commands. The "Agents SDK" (developers.openai.com/api/docs/guides/agents) is a **developer SDK for building custom agents**, not an end-user ChatGPT surface — irrelevant to a non-technical v-flow user. (VERIFIED FACT — [openai.com/index/the-next-evolution-of-the-agents-sdk](https://openai.com/index/the-next-evolution-of-the-agents-sdk/), accessed 2026-08-20)
- Third-party/community MCP servers (e.g., "GPT Filesystem," "chatgpt2codex" on GitHub) exist that bolt local file access onto ChatGPT via custom MCP connectors, but these are **not first-party OpenAI products**, require the user to install and run a local server themselves, and are out of scope for "what OpenAI ships." (VERIFIED FACT that such projects exist — [mcpmarket.com/server/gpt-filesystem](https://mcpmarket.com/server/gpt-filesystem), [github.com/ezBuilder/chatgpt2codex](https://github.com/ezBuilder/chatgpt2codex), accessed 2026-08-20 — flagged as out-of-scope/non-primary, not evaluated further)

### Summary table

| Surface | Local shell exec? | Reaches /Volumes/external drives? | Tier needed |
|---|---|---|---|
| ChatGPT desktop — Chat mode | No | No | Free+ |
| ChatGPT desktop — Work with Apps | No (read-only context from whitelisted apps) | Not applicable | Free+ (macOS) |
| ChatGPT desktop — Codex mode | **Yes** | Yes, if explicitly granted (see §3) | Free+ (per July 2026 merge), quota scales with plan |
| Codex CLI (terminal) | **Yes** | Yes, if explicitly granted (see §3) | Free/Go/Plus/Pro/Business/Enterprise, or API key |
| ChatGPT Agent (cloud) | No (cloud-sandboxed, no local FS) | **No — architecturally impossible** | Plus+ |

---

## 2. Reusable instruction files: does Codex support v-flow's agent-skill format?

- **Yes — Codex CLI and Codex-in-desktop natively support `AGENTS.md`.** OpenAI "helped pioneer" the format; it now lives at the OpenAI Codex repo root (`github.com/openai/codex/blob/main/AGENTS.md`) and was donated to the Agentic AI Foundation (a Linux Foundation project) in December 2025 as a vendor-neutral standard. (VERIFIED FACT — [agents.md](https://agents.md/) and [github.com/openai/codex/blob/main/AGENTS.md](https://github.com/openai/codex/blob/main/AGENTS.md), accessed 2026-08-20; donation date via secondary source [codersera.com AGENTS.md guide](https://codersera.com/blog/agents-md-complete-guide-2026/), accessed 2026-08-20)
- **Exact format/location:** a plain Markdown file named `AGENTS.md`, placed at the project root. Codex supports **nested** `AGENTS.md` files (one per subdirectory/package); agents walk up the directory tree from the file being edited and merge every `AGENTS.md` encountered, with the closest file winning on conflicts. (VERIFIED FACT, secondary but consistent across multiple 2026 guides — [morphllm.com/agents-md-guide](https://www.morphllm.com/agents-md-guide), accessed 2026-08-20)
- This means v-flow's existing agent skill (currently written for Claude Code/Cowork/Cursor as Markdown instructions, per the task context) is **directly portable to Codex** with no format translation: dropping the same or an adapted Markdown file at the repo root as `AGENTS.md` would be picked up automatically by Codex CLI and Codex-in-desktop. (INFERENCE — based on the documented AGENTS.md discovery mechanism, not verified against v-flow's actual skill file in this research pass)
- **Codex config** (sandbox mode, approval policy, writable roots, network access) lives in a separate file, `~/.codex/config.toml`, distinct from `AGENTS.md`. `AGENTS.md` conveys *task/workflow* instructions; `config.toml` conveys *permission* configuration. A v-flow setup guide for Codex users would need to walk users through **both** files. (VERIFIED FACT — [learn.chatgpt.com/docs/sandboxing](https://learn.chatgpt.com/docs/sandboxing), accessed 2026-08-20)
- ChatGPT Agent (cloud) and Work with Apps have no equivalent "reusable instruction file" mechanism relevant here, since neither can execute the CLI in the first place.

---

## 3. Concrete frictions v-flow would hit running under Codex (CLI or desktop)

This is the only surface where v-flow could plausibly run at all, so all friction analysis below is scoped to it.

### 3.1 Sandbox modes and defaults

Codex enforces two independent axes — **sandbox mode** and **approval policy** — both of which must permit an action before it proceeds. (VERIFIED FACT — [learn.chatgpt.com/docs/agent-approvals-security](https://learn.chatgpt.com/docs/agent-approvals-security), accessed 2026-08-20)

- **`read-only`** — inspection only, blocks all edits/commands.
- **`workspace-write` (default)** — read/write limited to the active workspace (current directory) plus `/tmp`; **no network access by default**; `.git`, `.agents`, `.codex` stay read-only recursively even in this mode.
- **`danger-full-access`** — no sandbox enforcement at all (network + filesystem unrestricted).

(VERIFIED FACT — [learn.chatgpt.com/docs/sandboxing](https://learn.chatgpt.com/docs/sandboxing), accessed 2026-08-20)

### 3.2 Filesystem access to external drives (`/Volumes/...`)

- By default, the workspace-write sandbox scopes writes to the current project directory and `/tmp` — **it does not include mounted external volumes**. v-flow's entire purpose (writing checksum-verified archives to external drives at `/Volumes/...`) falls outside the default writable root.
- Codex exposes an escape hatch: `sandbox_workspace_write.writable_roots` in `config.toml` (or the `--add-dir` CLI flag) lets a user explicitly add extra writable directories, including presumably a `/Volumes/MyDrive` path. (VERIFIED FACT — [learn.chatgpt.com/docs/config-advanced via search summary](https://developers.openai.com/codex/config-advanced), corroborated by [codex.danielvaughan.com: Multi-Directory Workflows](https://codex.danielvaughan.com/2026/05/10/codex-cli-multi-directory-workflows-add-dir-writable-roots-cross-repo-coordination/), accessed 2026-08-20)
- On **macOS specifically**, Codex enforces the sandbox via Apple's Seatbelt (`sandbox-exec`), and community reports show Seatbelt denials specifically for `/Volumes/...` paths surfacing as `deny(1) file-read-data /Volumes/...` in macOS console logs even when a writable root is nominally configured — i.e., there is a documented history of Seatbelt/`/Volumes` friction beyond just "add it to writable_roots." (SECONDARY SOURCE, treat with caution — [gist.github.com/rtzll/codex-sandboxing.md](https://gist.github.com/rtzll/8ec03ad8a4cca3ae43ce3db7eb7dcc09) and [codex.danielvaughan.com: Codex Sandbox Platform Implementation](https://codex.danielvaughan.com/2026/04/08/codex-sandbox-platform-implementation/), accessed 2026-08-20; there are also open GitHub issues on writable_roots not being respected on Windows, e.g. [openai/codex#23552](https://github.com/openai/codex/issues/23552), suggesting writable-root handling is an active pain point across platforms, not just macOS)
- **v-flow-specific friction (INFERENCE):** A non-technical v-flow user would need to correctly identify and hardcode their external drive's mount path (which changes if the drive is renamed, or if `/Volumes/Untitled` differs per card reader) into `config.toml`'s `writable_roots`/`--add-dir`, a step with no equivalent in Claude Code (which by default runs with full filesystem access from its working directory outward, modulo its own permission prompts). This is a real onboarding cliff for v-flow's target, non-developer, user.

### 3.3 Network access for `uv`/`pipx` self-install

- Network access is **off by default** even in `workspace-write` mode. Enabling it requires editing `config.toml`: `[sandbox_workspace_write] network_access = true`, or accepting an interactive approval prompt when Codex detects a command needs the network (e.g., `pip install`, `git push`). (VERIFIED FACT — [learn.chatgpt.com/docs/sandboxing](https://learn.chatgpt.com/docs/sandboxing), accessed 2026-08-20)
- **v-flow-specific friction (INFERENCE):** v-flow's skill self-installs the CLI via `uv`/`pipx`, both of which need network access to fetch packages from PyPI on first run. Under Codex's defaults, this install step would either (a) trigger an approval prompt the user must consent to, or (b) silently fail/be blocked if the user has set `approval_policy = "never"` or is running in a non-interactive context (see 3.4). This is an extra failure mode v-flow doesn't have to handle under Claude Code's default posture.

### 3.4 Interactive TTY prompts (y/n confirmations) — the sharpest friction

This is the single biggest documented risk for v-flow, which explicitly has interactive confirmation prompts on some commands.

- Codex's non-interactive mode, **`codex exec`**, is meant for scripts/CI: "runs a single session to completion without user interaction, emits events to stdout/stderr, and exits when the agent determines the task is complete." By default it runs in a **read-only** sandbox unless told otherwise. (VERIFIED FACT — [learn.chatgpt.com/docs/non-interactive-mode](https://learn.chatgpt.com/docs/non-interactive-mode), accessed 2026-08-20)
- Multiple **open GitHub issues on `openai/codex`** document that `codex exec` **hangs indefinitely** when it hits a situation requiring more input and stdin is not an interactive TTY:
  - `codex exec "<prompt>"` hangs indefinitely at "Reading additional input from stdin..." when run in a non-TTY environment. (VERIFIED FACT — [openai/codex#27019](https://github.com/openai/codex/issues/27019), accessed 2026-08-20)
  - `codex exec` hangs indefinitely when stdin is a non-TTY pipe with no writer, even though the prompt was already fully supplied as a CLI argument. (VERIFIED FACT — [openai/codex#20919](https://github.com/openai/codex/issues/20919), accessed 2026-08-20)
  - In non-interactive mode, tool calls requiring approval (e.g., MCP tool calls) are **auto-cancelled** rather than prompted, because stdin is closed — there is "no config key" to suppress this short of the blunt `--dangerously-bypass-approvals-and-sandbox` flag, or setting `-a never -s workspace-write` up front. (VERIFIED FACT — [openai/codex#24135](https://github.com/openai/codex/issues/24135), accessed 2026-08-20)
- **v-flow-specific friction (INFERENCE, high confidence):** v-flow's own interactive `y/n` confirmation prompts (e.g., "confirm before deleting the temporary editing copy," "confirm before overwriting duplicates") are a *second, independent* layer of interactivity stacked on top of Codex's own approval prompts. If Codex invokes v-flow as a subprocess under `codex exec` (headless/agentic mode) rather than the interactive TUI, v-flow's own TTY prompt has no interactive terminal to write to or read from — this is exactly the class of bug documented in the issues above, and would likely **hang the whole operation** rather than fail cleanly, unless v-flow detects non-TTY stdin and falls back to a flag-based confirmation (`--yes`/`--force`) instead of blocking on a prompt.
- Codex's interactive TUI mode (not `exec`) does have a working approval-prompt UI, so a user running Codex-in-desktop interactively and approving each v-flow command individually should not hit the hang — but that defeats the "conversational, low-friction" value proposition the skill is meant to provide, and still doesn't address v-flow's *own* nested confirmation prompt once Codex has already approved the shell command that runs it.

### 3.5 Timeouts on long-running operations (large video copies)

- Codex CLI has **no documented, user-facing configurable timeout for shell commands** in the reviewed docs; instead, multiple GitHub issues describe timeout handling as an unresolved rough edge:
  - When a shell tool call times out, Codex kills only the wrapping shell process (`bash -lc`), not its full child-process tree — orphaned children can keep pipes open and cause the CLI to hang indefinitely, despite an internal ~366-second wrapper timeout observed by users. (VERIFIED FACT re: the bug being reported, secondary — [openai/codex#4337](https://github.com/openai/codex/issues/4337), accessed 2026-08-20)
  - There is currently no way to kill a runaway background task from within the Codex UI, and no built-in equivalent to Claude Code's `BASH_DEFAULT_TIMEOUT_MS` env var. (VERIFIED FACT re: the gap being reported by users, secondary — [openai/codex#8656](https://github.com/openai/codex/issues/8656), accessed 2026-08-20)
- **v-flow-specific friction (INFERENCE, high confidence):** copying camera cards or large video archives is exactly the kind of multi-minute-to-multi-hour operation this ~366s internal wrapper timeout would clip. Unlike Claude Code (where the calling agent can set/extend a bash timeout per call), a v-flow user driving Codex risks a large ingest/archive copy being killed mid-transfer with no clean recovery path, which is especially dangerous for a tool whose core promise is checksum-verified, non-corrupting archival copies.

### 3.6 Approval-prompt fatigue as a distinct (softer) friction

- Even setting aside hangs, Codex's default `workspace-write` + `on-request`/`untrusted` approval policy means **every** filesystem write outside the workspace, every network call, and every command Codex doesn't recognize as "safe" triggers a prompt. (VERIFIED FACT — [learn.chatgpt.com/docs/agent-approvals-security](https://learn.chatgpt.com/docs/agent-approvals-security), accessed 2026-08-20)
- **v-flow-specific friction (INFERENCE):** a full v-flow session (ingest card → verify checksums → copy to archive drive → set up editing project → later archive exports) touches multiple external-drive paths and potentially a `uv`/`pipx` install — each a separate approval surface under Codex's default posture. A non-technical user would face several consent prompts per session unless they pre-configure `danger-full-access` (which OpenAI itself labels "not recommended") or carefully pre-populate `writable_roots` for their specific drive names.

---

## 4. Bottom line

**Which surface is realistic for a non-technical v-flow user today?**

Only **Codex** (the CLI, or its GUI wrapper inside the unified ChatGPT desktop app's Codex mode) can drive v-flow at all — Chat mode and Work with Apps cannot execute shell commands, and ChatGPT Agent is cloud-sandboxed with no path to the local filesystem whatsoever (VERIFIED, §1). Codex-in-desktop is the more realistic entry point for a non-technical user specifically, since it avoids a terminal-first setup and is bundled into the same ChatGPT desktop app across all plans including Free as of the July 2026 merge (VERIFIED, §1a). It also natively discovers `AGENTS.md`, so v-flow's existing skill content is portable there with effectively no format changes (VERIFIED, §2).

But "realistic" is a low bar cleared narrowly, not comfortably: Codex's sandbox defaults actively fight v-flow's actual job (writing to external drives, needing network for a first-run install, running long file copies, and asking its own y/n questions). None of this is fatal, but none of it is free either — it requires deliberate configuration that a Claude Code/Cowork user does not currently need to do.

**Top 3 concrete frictions to fix or document on v-flow's side, in priority order:**

1. **Nested-confirmation hang risk (§3.4).** If v-flow's own interactive `y/n` prompts run under `codex exec` (headless) with non-TTY stdin, they can hang the session indefinitely rather than fail cleanly — this is the most severe risk because it can strand a user mid-operation. Fix: detect non-interactive/non-TTY stdin in v-flow and fall back to an explicit `--yes`/`--force` flag path (which the Codex-facing skill instructions should be taught to pass) instead of blocking on a prompt Codex can't relay.

2. **External-drive writable-root setup (§3.2).** Codex's default sandbox does not include `/Volumes/...` by default, so v-flow's core write target is unreachable out of the box. Fix: document (in the AGENTS.md-facing skill or a setup wizard) the exact `config.toml`/`--add-dir` steps needed to grant Codex write access to the user's specific archive drive mount path, and account for that path changing when a drive is renamed or a different card reader is used.

3. **Long-copy timeout risk (§3.5).** Codex's internal shell-command timeout (observed around ~6 minutes) is not documented as user-configurable and has open bug reports about orphaned child processes on timeout — a real risk for multi-hour card ingests or archive copies. Fix: document that large copies should be chunked, run outside Codex's direct shell invocation (e.g., as a backgrounded/detached v-flow subcommand v-flow polls rather than one Codex holds a shell open for), or that Codex users should expect to re-run/resume rather than trust one long blocking call to complete.

A secondary, lower-priority item worth documenting: network access for the `uv`/`pipx` self-install step is off by default and needs either an approval click or a `config.toml` change (§3.3) — annoying but not dangerous, and a one-time cost per machine rather than per session.
