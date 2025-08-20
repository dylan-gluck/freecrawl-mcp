"""
FreeCrawl MCP Server entry point for command-line execution.
"""

import asyncio
import sys
import logging
from .server import FreeCrawlServer, ServerConfig

logger = logging.getLogger(__name__)


async def main():
    """Main entry point"""
    try:
        # Parse basic arguments
        if "--help" in sys.argv or "-h" in sys.argv:
            print("""
FreeCrawl MCP Server

Usage:
  freecrawl-mcp [options]

Options:
  --install-browsers    Install Playwright browsers and exit
  --test               Run basic functionality test
  --help               Show this help message

Environment Variables:
  FREECRAWL_TRANSPORT       Transport type (stdio|http) [default: stdio]
  FREECRAWL_MAX_BROWSERS    Maximum browser instances [default: 3]
  FREECRAWL_CACHE_DIR       Cache directory [default: /tmp/freecrawl_cache]
  FREECRAWL_LOG_LEVEL       Log level [default: INFO]

Examples:
  # Run MCP server (default)
  uvx freecrawl-mcp

  # Install browsers
  uvx freecrawl-mcp --install-browsers

  # Test installation
  uvx freecrawl-mcp --test

For more configuration options, see the documentation.
            """)
            return 0

        # Handle install browsers
        if "--install-browsers" in sys.argv:
            logger.info("Installing Playwright browsers...")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "playwright",
                "install",
                "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("Browsers installed successfully")
                return 0
            else:
                logger.error(f"Failed to install browsers: {stderr.decode()}")
                return 1

        # Handle test
        if "--test" in sys.argv:
            logger.info("Running FreeCrawl test...")
            config = ServerConfig()
            server = FreeCrawlServer(config)

            try:
                await server.initialize()

                # Test basic scraping
                result = await server.freecrawl_scrape("https://httpbin.org/html")
                if "error" not in result:
                    logger.info("✓ Basic scraping test passed")
                else:
                    logger.error(
                        f"✗ Basic scraping test failed: {result.get('message')}"
                    )
                    return 1

                # Test health check
                health = await server.freecrawl_health_check()
                if health.get("status") in ["healthy", "degraded"]:
                    logger.info("✓ Health check test passed")
                else:
                    logger.error("✗ Health check test failed")
                    return 1

                logger.info("✓ All tests passed - FreeCrawl is working correctly")
                return 0

            finally:
                await server.cleanup()

        # Run normal server
        config = ServerConfig()
        server = FreeCrawlServer(config)

        await server.run()
        return 0

    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        return 1


def sync_main():
    """Synchronous entry point for direct execution"""
    try:
        return asyncio.run(main())
    except Exception as e:
        logger.error(f"Startup error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(sync_main())
