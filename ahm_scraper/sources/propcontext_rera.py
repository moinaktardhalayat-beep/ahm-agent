"""Karnataka RERA via PropContext MCP server. No API key required."""
import asyncio
import json

MCP_URL = "https://propcontext-production.up.railway.app/mcp"

LOCALITIES = [
    "Bengaluru North",
    "Bengaluru South",
    "Bengaluru East",
    "Bengaluru West",
    "Yelahanka",
    "Anekal",
]


async def _call_tool(tool, arguments):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return json.loads("\n".join(texts)) if texts else {}


def _extract(data):
    if isinstance(data, dict):
        return data.get("projects") or data.get("results") or data.get("data") or []
    if isinstance(data, list):
        return data
    return []


def search_bengaluru_projects(limit=100):
    all_projects = []
    for loc in LOCALITIES:
        try:
            data = asyncio.run(_call_tool("search_projects", {
                "locality": loc,
                "limit": limit,
            }))
        except Exception as e:
            print(f"[PropContext] {loc} failed: {type(e).__name__}: {e}")
            continue

        projects = _extract(data)
        print(f"[PropContext] {loc}: {len(projects)} projects")
        all_projects.extend(projects)

    return all_projects
