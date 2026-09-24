"""Run the official TigerGraph MCP server against .env TG_* settings.

    python -m backend.mcp.official
"""

from tigergraph_mcp.main import main

if __name__ == "__main__":
    main()
