---
name: using-nowledge-mem
description: Uses Nowledge Mem through a remote MCP server for working memory, context bundles, memory search, and memory updates. Use when asked to recall, save, update, or inspect durable user knowledge.
---

# Using Nowledge Mem

Use this skill when the task benefits from the user's Nowledge Mem: current priorities, durable preferences, prior decisions, procedures, lessons, thread history, library artifacts, or knowledge graph context.

The bundled MCP server connects to the user's remote Mem server at `https://mem.selfrss.cloud/mcp`. It authenticates with the `NMEM_API_KEY` environment variable, so Amp must be started from a shell where that variable is set.

The MCP server name is `nowledge-mem` with a hyphen. Do not rewrite it as `nowledge_mem` when reading MCP resources or diagnosing server connection state.

## Workflow

1. At the start of a memory-aware task, call `read_context_bundle` when broad context matters, or `read_working_memory` when only today's focus is needed.
2. Use `memory_search` for prior decisions, preferences, procedures, and lessons related to the task.
3. Use `thread_search` or `thread_fetch_messages` only when the user asks about an earlier conversation or a memory points back to a source thread.
4. Use `memory_add` proactively when a durable decision, preference, procedure, event, or lesson emerges.
5. Use `memory_update` or `memory_supersede` instead of adding duplicates when new information corrects or replaces an existing memory.
6. Keep user-facing summaries concise: mention which memory operation mattered, not every tool call.

## Authentication

If the MCP tools fail with an authorization or missing API key error, ask the user to start Amp with:

```bash
export NMEM_API_KEY='their_mem_key_here'
amp
```

Do not ask the user to use OAuth for this server unless they explicitly request it.
