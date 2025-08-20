#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastmcp>=0.3.0",
#     "playwright>=1.40.0",
#     "aiohttp>=3.9.0",
#     "beautifulsoup4>=4.12.0",
#     "markdownify>=0.11.0",
#     "pydantic>=2.0.0",
#     "tenacity>=8.0.0",
#     "psutil>=5.9.0",
#     "aiosqlite>=0.19.0",
# ]
# ///
"""
Example usage of FreeCrawl MCP Server

This script demonstrates how to use the FreeCrawl server programmatically.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

async def test_freecrawl_direct():
    """Test FreeCrawl server directly (not through MCP protocol)"""
    print("Testing FreeCrawl Server Direct API...")

    # Import the server
    sys.path.insert(0, str(Path(__file__).parent))
    from freecrawl import FreeCrawlServer, ServerConfig

    # Create server with minimal config
    config = ServerConfig()
    config.cache_enabled = False  # Disable cache for testing
    server = FreeCrawlServer(config)

    try:
        await server.initialize()

        # Test basic scraping
        print("\n1. Testing basic scraping...")
        result = await server.freecrawl_scrape(
            url="https://httpbin.org/html",
            formats=["markdown", "text"]
        )

        if "error" not in result:
            print(f"✓ Successfully scraped content")
            print(f"  Title: {result.get('title', 'N/A')}")
            print(f"  Content length: {len(result.get('markdown', ''))}")
        else:
            print(f"✗ Error: {result['message']}")

        # Test batch scraping
        print("\n2. Testing batch scraping...")
        batch_result = await server.freecrawl_batch_scrape(
            urls=[
                "https://httpbin.org/html",
                "https://httpbin.org/json"
            ],
            concurrency=2,
            formats=["text"]
        )

        print(f"✓ Batch scraped {len(batch_result)} URLs")
        for i, result in enumerate(batch_result):
            if "error" not in result:
                print(f"  URL {i+1}: Success ({len(result.get('text', ''))} chars)")
            else:
                print(f"  URL {i+1}: Error - {result.get('message', 'Unknown')}")

        # Test health check
        print("\n3. Testing health check...")
        health = await server.freecrawl_health_check()
        print(f"✓ Health status: {health.get('status', 'unknown')}")

        # Test document processing (basic fallback)
        print("\n4. Testing document processing...")
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("This is a test document.\nWith multiple lines.\n")
            doc_path = f.name

        try:
            doc_result = await server.freecrawl_process_document(
                file_path=doc_path,
                formats=["text", "markdown"]
            )
            print(f"✓ Document processed: {doc_result.get('word_count', 0)} words")
        finally:
            Path(doc_path).unlink()

        print("\n🎉 All tests passed!")

    except Exception as e:
        print(f"✗ Test failed: {e}")

    finally:
        await server.cleanup()

def test_mcp_protocol():
    """Test FreeCrawl through MCP protocol"""
    print("\nTesting FreeCrawl MCP Protocol...")

    try:
        # Start the MCP server process
        process = subprocess.Popen(
            [sys.executable, "freecrawl.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).parent,
            text=True
        )

        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }

        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read response (with timeout)
        import select
        ready, _, _ = select.select([process.stdout], [], [], 5.0)

        if ready:
            response = process.stdout.readline()
            if response:
                data = json.loads(response.strip())
                if "result" in data:
                    print("✓ MCP protocol initialization successful")
                    print(f"  Server capabilities: {list(data['result'].get('capabilities', {}).keys())}")
                else:
                    print(f"✗ MCP initialization failed: {data}")
            else:
                print("✗ No response from MCP server")
        else:
            print("✗ MCP server timeout")

        process.terminate()
        process.wait(timeout=5)

    except Exception as e:
        print(f"✗ MCP protocol test failed: {e}")
        if 'process' in locals():
            process.terminate()

async def main():
    """Run all tests"""
    print("FreeCrawl MCP Server - Example Usage & Testing")
    print("=" * 50)

    # Test direct API
    await test_freecrawl_direct()

    # Test MCP protocol
    test_mcp_protocol()

    print("\n" + "=" * 50)
    print("Example Usage Complete!")
    print("\nTo use FreeCrawl as an MCP server:")
    print("  uv run freecrawl.py")
    print("\nTo test FreeCrawl functionality:")
    print("  uv run freecrawl.py --test")
    print("\nTo install browsers:")
    print("  uv run freecrawl.py --install-browsers")

if __name__ == "__main__":
    asyncio.run(main())
