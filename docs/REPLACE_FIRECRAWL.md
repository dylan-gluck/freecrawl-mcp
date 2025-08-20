# Replace Firecrawl

Firecrawl (https://docs.firecrawl.dev/mcp-server) is honestly pretty awesome, but its super simple. This API & MCP server can be easily recreated using Unstructured Open Source (https://docs.unstructured.io/open-source/introduction/overview) or even written from scratch.

## Assignment

1. Conduct deep research on each of these libraries using parallel agents.
2. Consolidate findings into single discovery doc outlining the primary methods, data-model and requirements for an MVP. Server should ideally be written as a single-file uv script, but if more complexity is needed a small uv project may be appropriate. Stdio seems like the best option for this, but explore enabling HTTP and SSE through runtime flags.
3. Use an engineering-lead agent to compose a detailed specification of the new FreeCrawl MCP server.
