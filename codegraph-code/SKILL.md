---
name: codegraph-code
description: Use when working with CodeGraph MCP tools for structural code exploration — finding symbols, tracing callers/callees, impact analysis, or gathering focused context from a tree-sitter-parsed knowledge graph. Use this skill whenever the user asks questions like "where is X defined", "what calls Y", "what would break if I change Z", "show me Y's signature", or any request that involves navigating code structure, symbol lookup, call graphs, or understanding codebase architecture. Also use when the user mentions CodeGraph, codegraph tools, or when `.codegraph/` initialization status needs checking.
version: 1.0.0
---

# CodeGraph Skill

Guide for using CodeGraph MCP tools to answer structural code questions efficiently. CodeGraph is a tree-sitter-parsed knowledge graph covering every symbol, edge, and file in the project. Reads are sub-millisecond and return structural information that grep cannot provide.

## Quick Reference

| Question | Tool |
|---|---|
| "Where is X defined?" / "Find symbol named X" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "What does Y call?" | `codegraph_callees` |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Show me Y's signature / source / docstring" | `codegraph_node` |
| "Give me focused context for a task/area" | `codegraph_context` |
| "See several related symbols' source at once" | `codegraph_explore` |
| "What files exist under path/" | `codegraph_files` |
| "Is the index healthy?" | `codegraph_status` |

## When to Prefer CodeGraph Over Native Search

Use codegraph for **structural** questions: what calls what, what would break, where is X defined, what is X's signature. Use native grep/read only for **literal text** queries (string contents, comments, log messages) or after you already have a specific file open.

## Rules of Thumb

These patterns keep queries fast and context-efficient. They reflect how the index is built and what each tool is optimized for.

- **Answer directly — don't delegate exploration.** For "how does X work" / architecture / trace questions, answer with 2-3 codegraph calls: `codegraph_context` first, then ONE `codegraph_explore` for the source of the symbols it surfaces. CodeGraph IS the pre-built index, so spawning a separate file-reading sub-task/agent — or running a grep + read loop — repeats work codegraph already did and costs more for the same answer.
- **Trust codegraph results.** They come from a full AST parse. Do NOT re-verify them with grep — that's slower, less accurate, and wastes context.
- **Don't grep first** when looking up a symbol by name. `codegraph_search` is faster and returns kind + location + signature in one call.
- **Don't chain `codegraph_search` + `codegraph_node`** when you just want context — `codegraph_context` is one call.
- **Don't loop `codegraph_node` over many symbols** — one `codegraph_explore` call returns several symbols' source grouped in a single capped call, while each separate node/Read call re-reads the whole context and costs far more.
- **Index lag**: the file watcher debounces ~500ms behind writes; don't re-query immediately after editing a file in the same turn.

## If `.codegraph/` Doesn't Exist

The MCP server returns "not initialized." Ask the user:

> I notice this project doesn't have CodeGraph initialized. Want me to run `codegraph init -i` to build the index?