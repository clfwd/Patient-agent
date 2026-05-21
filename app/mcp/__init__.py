"""MCP-style modular tool server package."""

from .router import McpRegistry, build_mcp_registry

__all__ = ["McpRegistry", "build_mcp_registry"]
