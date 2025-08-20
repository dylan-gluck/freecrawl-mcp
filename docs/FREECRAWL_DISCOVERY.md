# FreeCrawl MCP Server - Discovery Document

## Executive Summary

Based on comprehensive research across Firecrawl capabilities, Unstructured Open Source, and modern web scraping alternatives, we recommend building **FreeCrawl** as a hybrid MCP server combining:

1. **FastMCP + Playwright** for modern web scraping with JavaScript support
2. **Unstructured Open Source** for document processing and extraction  
3. **uv single-file script** architecture for portability and simplicity
4. **Streamable HTTP transport** for production scalability

## Research Synthesis

### Primary Methods Required

#### Core Web Scraping Methods
```python
# Single URL scraping with format options
async def scrape(url: str, formats: list[str] = ["markdown"], **options) -> dict

# Batch URL processing with concurrency control  
async def batch_scrape(urls: list[str], concurrency: int = 10, **options) -> list[dict]

# Recursive website crawling with depth limits
async def crawl(url: str, max_depth: int = 2, limit: int = 100, **options) -> list[dict]

# Website URL discovery and mapping
async def map_site(url: str, limit: int = 1000) -> list[str]

# Web search with optional content extraction
async def search(query: str, limit: int = 5, scrape_results: bool = False) -> list[dict]

# AI-powered structured data extraction
async def extract(url: str, schema: dict, prompt: str = None) -> dict
```

#### Document Processing Methods (via Unstructured)
```python
# Process uploaded/local documents
async def process_document(file_path: str, strategy: str = "hi_res") -> list[dict]

# Chunk documents for RAG applications
async def chunk_document(elements: list[dict], strategy: str = "by_title") -> list[dict]
```

### Data Model Architecture

#### Standard Response Format
```typescript
interface ScrapedContent {
  url: string;
  title?: string;
  markdown?: string;
  html?: string;
  screenshot?: string; // base64
  metadata: {
    timestamp: string;
    status_code: number;
    content_type: string;
    page_load_time: number;
    word_count: number;
    language?: string;
  };
  elements?: DocumentElement[]; // For structured extraction
}

interface DocumentElement {
  type: "Title" | "Text" | "List" | "Table" | "Image";
  content: string;
  metadata: {
    page_number?: number;
    coordinates?: BoundingBox;
    confidence?: number;
  };
}
```

#### Tool Schema Definitions
```typescript
// Primary scraping tool
{
  name: "freecrawl_scrape",
  description: "Scrape content from a single URL with anti-detection",
  inputSchema: {
    type: "object",
    properties: {
      url: { type: "string", description: "URL to scrape" },
      formats: { 
        type: "array", 
        items: { enum: ["markdown", "html", "screenshot", "structured"] },
        default: ["markdown"]
      },
      javascript: { type: "boolean", default: true },
      wait_for: { type: "number", default: 2000 },
      anti_bot: { type: "boolean", default: true },
      extract_schema: { type: "object", description: "Schema for structured extraction" }
    },
    required: ["url"]
  }
}
```

### Requirements for MVP

#### Core Dependencies
```toml
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "fastmcp>=0.3.0",
#   "playwright>=1.40.0", 
#   "unstructured[all-docs]>=0.15.0",
#   "aiohttp>=3.9.0",
#   "beautifulsoup4>=4.12.0",
#   "turndown>=0.8.0",  # HTML to Markdown
#   "pydantic>=2.0.0",
#   "tenacity>=8.0.0"  # Retry logic
# ]
# ///
```

#### System Requirements
- Python 3.12+
- Playwright browser binaries (`playwright install`)
- System dependencies for Unstructured:
  - `libmagic-dev`
  - `poppler-utils` 
  - `tesseract-ocr`
  - `libreoffice`

#### Transport Configuration
```python
# Dual transport support
if os.getenv("FREECRAWL_TRANSPORT") == "http":
    # Streamable HTTP for production
    transport = httpx_sse.HTTPTransport(port=8000)
else:
    # STDIO for development
    transport = StdioTransport()
```

### Architecture Recommendations

#### Single-File uv Script Approach
**Pros:**
- Zero-config deployment
- Self-installing dependencies
- Portable across environments
- Minimal infrastructure requirements

**Cons:**
- Limited to ~2000 lines for maintainability
- No separate test files
- Harder to modularize complex features

#### Multi-File Project Alternative
**When to use:** If MVP grows beyond single-file limitations
- Complex authentication requirements
- Enterprise features (monitoring, logging)
- Extensive test suite requirements
- Multiple transport protocols

### Performance & Scalability

#### Async Architecture Pattern
```python
import asyncio
from contextlib import asynccontextmanager

class FreeCrawlServer:
    def __init__(self):
        self.session_pool = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100),
            timeout=aiohttp.ClientTimeout(total=30)
        )
        self.browser_pool = None  # Managed Playwright browsers
        
    @asynccontextmanager
    async def get_browser(self):
        # Pool management for concurrent scraping
        pass
        
    async def scrape_concurrent(self, urls: list[str]) -> list[dict]:
        semaphore = asyncio.Semaphore(10)  # Concurrency limit
        tasks = [self._scrape_with_semaphore(url, semaphore) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

#### Anti-Detection Strategy
```python
# Rotating user agents and proxy support
BROWSER_CONFIG = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
    "viewport": {"width": 1920, "height": 1080},
    "locale": "en-US",
    "timezone": "America/New_York",
    "permissions": ["geolocation"],
    "extra_http_headers": {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }
}
```

### Error Handling & Reliability

#### Retry Logic with Exponential Backoff
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def robust_scrape(url: str) -> dict:
    # Implementation with comprehensive error handling
    pass
```

#### Status Monitoring
```python
# Health check endpoint for production
@mcp.tool()
def health_check() -> dict:
    return {
        "status": "healthy",
        "browser_pool_size": len(self.browser_pool),
        "active_sessions": self.session_pool.connector._conns_per_host,
        "uptime": time.time() - self.start_time
    }
```

## MVP Implementation Plan

### Phase 1: Core Functionality (Week 1-2)
- [x] Research completed
- [ ] Single-file uv script structure
- [ ] Basic scrape tool with Playwright
- [ ] Markdown conversion pipeline
- [ ] MCP server registration and transport

### Phase 2: Enhanced Features (Week 3-4)  
- [ ] Batch scraping with concurrency
- [ ] Unstructured document processing integration
- [ ] Basic anti-detection measures
- [ ] Error handling and retry logic

### Phase 3: Production Features (Week 5-6)
- [ ] Advanced anti-bot capabilities
- [ ] Structured data extraction with schemas
- [ ] Performance optimization
- [ ] Comprehensive testing and documentation

### Phase 4: Advanced Capabilities (Optional)
- [ ] Crawling with depth control
- [ ] Web search integration
- [ ] Proxy rotation system
- [ ] Enterprise authentication

## Comparison with Firecrawl

| Feature | Firecrawl | FreeCrawl MVP |
|---------|-----------|---------------|
| **Web Scraping** | ✅ Advanced | ✅ Playwright-based |
| **Document Processing** | ❌ Limited | ✅ Unstructured integration |
| **Anti-Detection** | ✅ Professional | ⚠️ Basic (MVP) |
| **Cost** | 💰 Credit-based | 🆓 Self-hosted |
| **JavaScript Support** | ✅ Advanced | ✅ Full Playwright |
| **Deployment** | ☁️ Cloud only | 🏠 Self-hosted |
| **Customization** | ❌ Limited | ✅ Full control |
| **MCP Integration** | ✅ Official | ✅ FastMCP |

## Risk Assessment

### Technical Risks
- **Anti-bot detection**: Requires ongoing maintenance as sites update defenses
- **Performance scaling**: May need optimization for high-concurrency scenarios  
- **Browser management**: Playwright browser lifecycle management complexity

### Mitigation Strategies
- Start with basic anti-detection, enhance iteratively
- Implement circuit breakers and rate limiting
- Use managed browser pools with health checks
- Plan for containerized deployment with resource limits

## Success Metrics

### MVP Success Criteria
- Successfully scrape 95% of standard websites
- Process documents with 90%+ accuracy vs Firecrawl
- Handle 10 concurrent requests without degradation
- Deploy as single-file script with zero-config

### Performance Targets
- Response time: <5 seconds for standard pages
- Memory usage: <500MB under normal load
- Concurrent capacity: 50+ simultaneous scraping tasks
- Error rate: <5% for accessible websites

## Next Steps

1. **Create detailed technical specification** using engineering-lead agent
2. **Prototype single-file implementation** with core scraping functionality
3. **Integrate Unstructured** for document processing pipeline
4. **Implement anti-detection baseline** using Playwright stealth mode
5. **Performance testing** with representative workload
6. **Production deployment** with monitoring and observability

---

*This discovery document synthesizes research from Firecrawl documentation, Unstructured Open Source analysis, and modern web scraping best practices as of August 2025.*