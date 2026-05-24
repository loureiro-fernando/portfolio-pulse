import asyncio

from app.mcp_servers.slack_server import call_tool


async def main() -> None:
    result = await call_tool(
        "post_alert",
        {
            "portco_name": "AcmeCo (test)",
            "severity": "info",
            "summary": "smoke test from portfolio-pulse MCP",
        },
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
