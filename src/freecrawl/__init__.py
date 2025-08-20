"""
FreeCrawl MCP Server - Self-hosted web scraping and document processing

A production-ready MCP server that provides web scraping, document processing,
and structured data extraction capabilities as a Firecrawl replacement.
"""

__version__ = "0.1.0"
__author__ = "Dylan Gluck"
__email__ = "dylan@dylangluck.com"

from .server import FreeCrawlServer, ServerConfig

__all__ = ["FreeCrawlServer", "ServerConfig"]
