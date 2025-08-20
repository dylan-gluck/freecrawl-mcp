# FreeCrawl MCP Server

A production-ready Model Context Protocol (MCP) server for web scraping and document processing, designed as a self-hosted replacement for Firecrawl.

## 🚀 Features

- **JavaScript-enabled web scraping** with Playwright and anti-detection measures
- **Document processing** with fallback support for various formats
- **Concurrent batch processing** with configurable limits
- **Intelligent caching** with SQLite backend
- **Rate limiting** per domain
- **Comprehensive error handling** with retry logic
- **Single-file deployment** with uv script format
- **Health monitoring** and metrics collection

## 📦 Installation & Setup

### Prerequisites

- Python 3.12+
- uv package manager

### Quick Start

1. **Install and test FreeCrawl:**
   ```bash
   # Test installation
   uv run /path/to/freecrawl.py --help

   # Install browser dependencies
   uv run /path/to/freecrawl.py --install-browsers

   # Run basic functionality test
   uv run /path/to/freecrawl.py --test
   ```

2. **Run as MCP server (default STDIO mode):**
   ```bash
   uv run /path/to/freecrawl.py
   ```

3. **Test with example script:**
   ```bash
   uv run mcp/example_usage.py
   ```

## 🛠 Configuration

Configure FreeCrawl using environment variables:

### Basic Configuration
```bash
# Transport (stdio for MCP, http for REST API)
export FREECRAWL_TRANSPORT=stdio

# Browser pool settings
export FREECRAWL_MAX_BROWSERS=3
export FREECRAWL_HEADLESS=true

# Concurrency limits
export FREECRAWL_MAX_CONCURRENT=10
export FREECRAWL_MAX_PER_DOMAIN=3

# Cache settings
export FREECRAWL_CACHE=true
export FREECRAWL_CACHE_DIR=/tmp/freecrawl_cache
export FREECRAWL_CACHE_TTL=3600
export FREECRAWL_CACHE_SIZE=536870912  # 512MB

# Rate limiting
export FREECRAWL_RATE_LIMIT=60  # requests per minute

# Logging
export FREECRAWL_LOG_LEVEL=INFO
```

### Security Settings
```bash
# API authentication (optional)
export FREECRAWL_REQUIRE_API_KEY=false
export FREECRAWL_API_KEYS=key1,key2,key3

# Domain blocking
export FREECRAWL_BLOCKED_DOMAINS=localhost,127.0.0.1

# Anti-detection
export FREECRAWL_ANTI_DETECT=true
export FREECRAWL_ROTATE_UA=true
```

## 🔧 MCP Tools

FreeCrawl provides the following MCP tools:

### `freecrawl_scrape`
Scrape content from a single URL with advanced options.

**Parameters:**
- `url` (string): URL to scrape
- `formats` (array): Output formats - `["markdown", "html", "text", "screenshot", "structured"]`
- `javascript` (boolean): Enable JavaScript execution (default: true)
- `wait_for` (string, optional): CSS selector or time (ms) to wait
- `anti_bot` (boolean): Enable anti-detection measures (default: true)
- `headers` (object, optional): Custom HTTP headers
- `cookies` (object, optional): Custom cookies
- `cache` (boolean): Use cached results if available (default: true)
- `timeout` (number): Total timeout in milliseconds (default: 30000)

**Example:**
```json
{
  "name": "freecrawl_scrape",
  "arguments": {
    "url": "https://example.com",
    "formats": ["markdown", "screenshot"],
    "javascript": true,
    "wait_for": "2000"
  }
}
```

### `freecrawl_batch_scrape`
Scrape multiple URLs concurrently.

**Parameters:**
- `urls` (array): List of URLs to scrape (max 100)
- `concurrency` (number): Maximum concurrent requests (default: 5)
- `formats` (array): Output formats (default: `["markdown"]`)
- `common_options` (object, optional): Options applied to all URLs
- `continue_on_error` (boolean): Continue if individual URLs fail (default: true)

**Example:**
```json
{
  "name": "freecrawl_batch_scrape",
  "arguments": {
    "urls": [
      "https://example.com/page1",
      "https://example.com/page2"
    ],
    "concurrency": 3,
    "formats": ["markdown", "text"]
  }
}
```

### `freecrawl_extract`
Extract structured data using schema-driven approach.

**Parameters:**
- `url` (string): URL to extract data from
- `schema` (object): JSON Schema or Pydantic model definition
- `prompt` (string, optional): Custom extraction instructions
- `validation` (boolean): Validate against schema (default: true)
- `multiple` (boolean): Extract multiple matching items (default: false)

**Example:**
```json
{
  "name": "freecrawl_extract",
  "arguments": {
    "url": "https://example.com/product",
    "schema": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "price": {"type": "number"}
      }
    }
  }
}
```

### `freecrawl_process_document`
Process documents (PDF, DOCX, etc.) with OCR support.

**Parameters:**
- `file_path` (string, optional): Path to document file
- `url` (string, optional): URL to download document from
- `strategy` (string): Processing strategy - `"fast"`, `"hi_res"`, `"ocr_only"` (default: "hi_res")
- `formats` (array): Output formats - `["markdown", "structured", "text"]`
- `languages` (array, optional): OCR languages (e.g., `["eng", "fra"]`)
- `extract_images` (boolean): Extract embedded images (default: false)
- `extract_tables` (boolean): Extract and structure tables (default: true)

**Example:**
```json
{
  "name": "freecrawl_process_document",
  "arguments": {
    "url": "https://example.com/document.pdf",
    "strategy": "hi_res",
    "formats": ["markdown", "structured"]
  }
}
```

### `freecrawl_health_check`
Get server health status and metrics.

**Example:**
```json
{
  "name": "freecrawl_health_check",
  "arguments": {}
}
```

## 🔄 Integration with Claude Code

### MCP Configuration

Add FreeCrawl to your `.claude/agent-tools.json`:

```json
{
  "mcp": {
    "freecrawl": {
      "command": "uv",
      "args": ["run", "/path/to/freecrawl.py"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### Usage in Prompts

```
Please scrape the content from https://example.com and extract the main article text in markdown format.
```

Claude Code will automatically use the `freecrawl_scrape` tool to fetch and process the content.

## 🚀 Performance & Scalability

### Resource Usage
- **Memory**: ~100MB base + ~50MB per browser instance
- **CPU**: Moderate usage during active scraping
- **Storage**: Cache grows based on configured limits

### Throughput
- **Single requests**: 2-5 seconds typical response time
- **Batch processing**: 10-50 concurrent requests depending on configuration
- **Cache hit ratio**: 30%+ for repeated content

### Optimization Tips
1. **Enable caching** for frequently accessed content
2. **Adjust concurrency** based on target site rate limits
3. **Use appropriate formats** - markdown is faster than screenshots
4. **Configure rate limiting** to avoid being blocked

## 🛡 Security Considerations

### Anti-Detection
- Rotating user agents
- Realistic browser fingerprints
- Request timing randomization
- JavaScript execution in sandboxed environment

### Input Validation
- URL format validation
- Private IP blocking
- Domain blocklist support
- Request size limits

### Resource Protection
- Memory usage monitoring
- Browser pool size limits
- Request timeout enforcement
- Rate limiting per domain

## 🔧 Troubleshooting

### Common Issues

| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| High memory usage | Too many browser instances | Reduce `FREECRAWL_MAX_BROWSERS` |
| Slow responses | JavaScript-heavy sites | Increase timeout or disable JS |
| Bot detection | Missing anti-detection | Ensure `FREECRAWL_ANTI_DETECT=true` |
| Cache misses | TTL too short | Increase `FREECRAWL_CACHE_TTL` |
| Import errors | Missing dependencies | Run `uv run /path/to/freecrawl.py --test` |

### Debug Mode
```bash
export FREECRAWL_LOG_LEVEL=DEBUG
uv run /path/to/freecrawl.py --test
```

### Health Check
```bash
# Check server status
curl localhost:8000/health  # If running in HTTP mode

# Or use the health check tool
echo '{"name": "freecrawl_health_check", "arguments": {}}' | uv run /path/to/freecrawl.py
```

## 📈 Monitoring & Observability

### Health Metrics
- Browser pool status
- Memory and CPU usage
- Cache hit rates
- Request success rates
- Response times

### Logging
FreeCrawl provides structured logging with configurable levels:
- ERROR: Critical failures
- WARNING: Recoverable issues
- INFO: General operations
- DEBUG: Detailed troubleshooting

## 🔧 Development

### Running Tests
```bash
# Basic functionality test
uv run /path/to/freecrawl.py --test

# Comprehensive example
uv run mcp/example_usage.py
```

### Code Structure
- **Core server**: `FreeCrawlServer` class
- **Browser management**: `BrowserPool` for resource pooling
- **Content extraction**: `ContentExtractor` with multiple strategies
- **Caching**: `CacheManager` with SQLite backend
- **Rate limiting**: `RateLimiter` with token bucket algorithm

## 📄 License

This project is licensed under the MIT License - see the technical specification for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests: `uv run /path/to/freecrawl.py --test`
4. Submit a pull request

## 📚 Technical Specification

For detailed technical information, see `ai_docs/FREECRAWL_TECHNICAL_SPEC.md`.

---

**FreeCrawl MCP Server** - Self-hosted web scraping for the modern web 🚀
