# FreeCrawl MCP Server - Technical Specification

## 1. Overview

### 1.1 Purpose and Goals

FreeCrawl is a self-hosted, open-source Model Context Protocol (MCP) server designed to replace Firecrawl with enhanced capabilities for web scraping, document processing, and structured data extraction. The system provides:

- **Web Content Extraction**: JavaScript-enabled scraping with anti-detection measures
- **Document Processing**: Multi-format document parsing and extraction via Unstructured
- **Structured Data Mining**: Schema-driven extraction with AI assistance
- **Production Scalability**: Concurrent processing with resource management
- **Zero-Configuration Deployment**: Single-file uv script with auto-dependency installation

### 1.2 Success Criteria

- Replace 100% of Firecrawl functionality in existing workflows
- Process 95%+ of standard websites without detection
- Handle 50+ concurrent requests with <5s response time
- Deploy in <30 seconds with single command
- Maintain <500MB memory footprint under normal load
- Achieve <5% error rate on accessible websites

### 1.3 Assumptions and Constraints

**Assumptions:**
- Python 3.12+ available on target systems
- Network access for dependency installation
- Sufficient resources for browser instances (2GB RAM minimum)
- Standard web protocols (HTTP/HTTPS) for target sites

**Constraints:**
- Single-file implementation (~2000 lines maximum)
- No external service dependencies (fully self-contained)
- Cross-platform compatibility (Linux, macOS, Windows)
- MIT license compatibility for all dependencies

## 2. System Architecture

### 2.1 High-Level Design

```mermaid
graph TB
    subgraph "Client Layer"
        C1[Claude Code]
        C2[MCP Client]
        C3[API Client]
    end
    
    subgraph "Transport Layer"
        T1[STDIO Transport]
        T2[HTTP/SSE Transport]
    end
    
    subgraph "FreeCrawl Core"
        MC[MCP Server Core]
        RT[Request Router]
        PM[Pool Manager]
        
        subgraph "Processing Engines"
            PE1[Playwright Engine]
            PE2[BeautifulSoup Engine]
            PE3[Unstructured Engine]
        end
        
        subgraph "Support Services"
            SS1[Anti-Detection Service]
            SS2[Cache Manager]
            SS3[Rate Limiter]
            SS4[Health Monitor]
        end
    end
    
    subgraph "External Resources"
        ER1[Target Websites]
        ER2[Local Documents]
        ER3[Search APIs]
    end
    
    C1 --> T1
    C2 --> T1
    C3 --> T2
    T1 --> MC
    T2 --> MC
    MC --> RT
    RT --> PM
    PM --> PE1
    PM --> PE2
    PM --> PE3
    PE1 --> SS1
    PE1 --> ER1
    PE2 --> ER1
    PE3 --> ER2
```

### 2.2 Component Interactions

#### Core Components

1. **MCP Server Core**: FastMCP-based server handling tool registration and message routing
2. **Request Router**: Dispatches requests to appropriate processing engines
3. **Pool Manager**: Manages browser instances and connection pools
4. **Processing Engines**: Specialized handlers for different content types
5. **Support Services**: Cross-cutting concerns (caching, rate limiting, monitoring)

#### Data Flow Sequence

```mermaid
sequenceDiagram
    participant Client
    participant MCP Server
    participant Router
    participant Pool Manager
    participant Playwright
    participant Unstructured
    participant Target Site
    
    Client->>MCP Server: Tool Request (scrape)
    MCP Server->>Router: Route Request
    Router->>Pool Manager: Get Browser Instance
    Pool Manager->>Playwright: Assign Browser
    Playwright->>Target Site: Navigate & Extract
    Target Site-->>Playwright: HTML/JS Content
    Playwright->>Unstructured: Process Content
    Unstructured-->>Playwright: Structured Data
    Playwright-->>Pool Manager: Release Browser
    Pool Manager-->>Router: Formatted Response
    Router-->>MCP Server: Tool Response
    MCP Server-->>Client: JSON Result
```

### 2.3 System Boundaries

**Internal Systems:**
- FreeCrawl MCP server process
- Browser pool (Playwright instances)
- In-memory cache
- Local file system access

**External Systems:**
- Target websites (HTTP/HTTPS)
- Local document storage
- Search engine APIs
- MCP clients

**Security Boundaries:**
- No credential storage (passed per-request)
- Sandboxed browser execution
- Rate-limited external requests
- Input validation at MCP boundary

## 3. Data Model

### 3.1 Entity Definitions

```python
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

# Core Entities

class BoundingBox(BaseModel):
    """Coordinate system for document elements"""
    x: float
    y: float
    width: float
    height: float

class DocumentMetadata(BaseModel):
    """Metadata for processed documents"""
    page_number: Optional[int] = None
    coordinates: Optional[BoundingBox] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    element_id: Optional[str] = None
    parent_id: Optional[str] = None

class DocumentElement(BaseModel):
    """Structured element from document processing"""
    type: Literal["Title", "Text", "List", "Table", "Image", "Code", "Header", "Footer"]
    content: str
    metadata: DocumentMetadata
    children: Optional[List['DocumentElement']] = None

class PageMetadata(BaseModel):
    """Web page metadata"""
    timestamp: datetime
    status_code: int
    content_type: str
    page_load_time: float  # milliseconds
    word_count: int
    language: Optional[str] = None
    encoding: Optional[str] = "utf-8"
    headers: Dict[str, str] = {}
    cookies: Optional[Dict[str, str]] = None

class ScrapedContent(BaseModel):
    """Primary response format for scraped content"""
    url: HttpUrl
    title: Optional[str] = None
    markdown: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    screenshot: Optional[str] = None  # base64 encoded
    metadata: PageMetadata
    elements: Optional[List[DocumentElement]] = None
    links: Optional[List[str]] = None
    images: Optional[List[str]] = None
    
class ExtractedData(BaseModel):
    """Schema-driven extracted data"""
    url: HttpUrl
    schema_version: str
    extracted_at: datetime
    data: Dict[str, Any]
    confidence_scores: Optional[Dict[str, float]] = None
    validation_errors: Optional[List[str]] = None

class CrawlResult(BaseModel):
    """Result from website crawling"""
    start_url: HttpUrl
    pages_found: int
    pages_scraped: int
    max_depth_reached: int
    content: List[ScrapedContent]
    sitemap: Optional[Dict[str, List[str]]] = None  # URL tree
    errors: Optional[List[Dict[str, str]]] = None

class SearchResult(BaseModel):
    """Web search result"""
    query: str
    total_results: int
    results: List[Dict[str, Any]]
    scraped_content: Optional[List[ScrapedContent]] = None
```

### 3.2 Relationships

```mermaid
erDiagram
    ScrapedContent ||--o{ DocumentElement : contains
    ScrapedContent ||--|| PageMetadata : has
    DocumentElement ||--|| DocumentMetadata : has
    DocumentElement ||--o{ DocumentElement : children
    CrawlResult ||--o{ ScrapedContent : aggregates
    SearchResult ||--o{ ScrapedContent : optionally_contains
    ExtractedData ||--|| ScrapedContent : derived_from
```

### 3.3 Database Schema

While FreeCrawl operates primarily in-memory, persistent caching uses this schema:

```sql
-- Cache storage (SQLite for single-file deployment)
CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    content_type TEXT NOT NULL,
    data BLOB NOT NULL,  -- Compressed JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0
);

CREATE INDEX idx_cache_expires ON cache_entries(expires_at);
CREATE INDEX idx_cache_url ON cache_entries(url);

-- Request history for rate limiting
CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_code INTEGER,
    response_time FLOAT
);

CREATE INDEX idx_request_domain_time ON request_log(domain, timestamp);
```

### 3.4 Migration Strategy

For existing Firecrawl users, provide compatibility mapping:

```python
# Firecrawl compatibility layer
def firecrawl_to_freecrawl(firecrawl_response: dict) -> ScrapedContent:
    """Convert Firecrawl response format to FreeCrawl format"""
    return ScrapedContent(
        url=firecrawl_response["url"],
        title=firecrawl_response.get("metadata", {}).get("title"),
        markdown=firecrawl_response.get("markdown"),
        html=firecrawl_response.get("html"),
        metadata=PageMetadata(
            timestamp=datetime.now(),
            status_code=firecrawl_response.get("statusCode", 200),
            content_type="text/html",
            page_load_time=0,
            word_count=len(firecrawl_response.get("markdown", "").split())
        )
    )
```

## 4. API Design

### 4.1 MCP Tool Specifications

#### 4.1.1 Core Scraping Tool

```python
@mcp.tool()
async def freecrawl_scrape(
    url: str = Field(..., description="URL to scrape"),
    formats: List[Literal["markdown", "html", "text", "screenshot", "structured"]] = Field(
        default=["markdown"],
        description="Output formats to generate"
    ),
    javascript: bool = Field(default=True, description="Enable JavaScript execution"),
    wait_for: Optional[str] = Field(None, description="CSS selector or time (ms) to wait"),
    anti_bot: bool = Field(default=True, description="Enable anti-detection measures"),
    headers: Optional[Dict[str, str]] = Field(None, description="Custom HTTP headers"),
    cookies: Optional[Dict[str, str]] = Field(None, description="Custom cookies"),
    proxy: Optional[str] = Field(None, description="Proxy URL (http://user:pass@host:port)"),
    extract_schema: Optional[Dict[str, Any]] = Field(None, description="Schema for structured extraction"),
    cache: bool = Field(default=True, description="Use cached results if available"),
    timeout: int = Field(default=30000, description="Total timeout in milliseconds")
) -> ScrapedContent:
    """
    Scrape content from a single URL with advanced options.
    
    Returns comprehensive content in requested formats with metadata.
    Automatically handles JavaScript rendering, anti-bot measures, and retries.
    """
```

#### 4.1.2 Batch Scraping Tool

```python
@mcp.tool()
async def freecrawl_batch(
    urls: List[str] = Field(..., description="List of URLs to scrape", max_items=100),
    concurrency: int = Field(default=10, description="Maximum concurrent requests", ge=1, le=50),
    formats: List[str] = Field(default=["markdown"], description="Output formats"),
    common_options: Optional[Dict[str, Any]] = Field(None, description="Options applied to all URLs"),
    per_url_options: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="URL-specific options"),
    continue_on_error: bool = Field(default=True, description="Continue if individual URLs fail"),
    deduplication: bool = Field(default=True, description="Remove duplicate content")
) -> List[Union[ScrapedContent, Dict[str, str]]]:
    """
    Scrape multiple URLs concurrently with shared or individual options.
    
    Returns list of results in order of input URLs.
    Failed URLs return error dictionaries if continue_on_error is True.
    """
```

#### 4.1.3 Website Crawling Tool

```python
@mcp.tool()
async def freecrawl_crawl(
    start_url: str = Field(..., description="Starting URL for crawl"),
    max_depth: int = Field(default=2, description="Maximum crawl depth", ge=1, le=10),
    max_pages: int = Field(default=100, description="Maximum pages to crawl", ge=1, le=1000),
    include_patterns: Optional[List[str]] = Field(None, description="URL patterns to include (regex)"),
    exclude_patterns: Optional[List[str]] = Field(None, description="URL patterns to exclude (regex)"),
    follow_external: bool = Field(default=False, description="Follow external domain links"),
    formats: List[str] = Field(default=["markdown"], description="Content formats to extract"),
    respect_robots: bool = Field(default=True, description="Respect robots.txt"),
    crawl_delay: float = Field(default=1.0, description="Delay between requests (seconds)")
) -> CrawlResult:
    """
    Recursively crawl a website starting from the given URL.
    
    Discovers and scrapes pages up to max_depth from start_url.
    Builds a sitemap and returns all scraped content.
    """
```

#### 4.1.4 Site Mapping Tool

```python
@mcp.tool()
async def freecrawl_map(
    url: str = Field(..., description="Website URL to map"),
    max_urls: int = Field(default=1000, description="Maximum URLs to discover", ge=1, le=10000),
    include_patterns: Optional[List[str]] = Field(None, description="URL patterns to include"),
    exclude_patterns: Optional[List[str]] = Field(None, description="URL patterns to exclude"),
    group_by: Literal["path", "type", "depth"] = Field(default="path", description="Grouping strategy")
) -> Dict[str, Any]:
    """
    Discover and map all URLs on a website without scraping content.
    
    Returns structured sitemap with URL relationships and metadata.
    Useful for understanding site structure before crawling.
    """
```

#### 4.1.5 Document Processing Tool

```python
@mcp.tool()
async def freecrawl_process_document(
    file_path: str = Field(..., description="Path to document file"),
    url: Optional[str] = Field(None, description="URL to download document from"),
    strategy: Literal["fast", "hi_res", "ocr_only"] = Field(
        default="hi_res",
        description="Processing strategy: fast (quick), hi_res (accurate), ocr_only (images)"
    ),
    formats: List[Literal["markdown", "structured", "text"]] = Field(
        default=["structured"],
        description="Output formats"
    ),
    languages: Optional[List[str]] = Field(None, description="OCR languages (e.g., ['eng', 'fra'])"),
    chunk_size: Optional[int] = Field(None, description="Split into chunks of N characters"),
    extract_images: bool = Field(default=False, description="Extract embedded images"),
    extract_tables: bool = Field(default=True, description="Extract and structure tables")
) -> Dict[str, Any]:
    """
    Process documents (PDF, DOCX, PPTX, etc.) using Unstructured.
    
    Extracts text, tables, images, and metadata from various document formats.
    Supports OCR for scanned documents and multiple output formats.
    """
```

#### 4.1.6 Structured Extraction Tool

```python
@mcp.tool()
async def freecrawl_extract(
    url: str = Field(..., description="URL to extract data from"),
    schema: Dict[str, Any] = Field(..., description="JSON Schema or Pydantic model definition"),
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Example extractions"),
    prompt: Optional[str] = Field(None, description="Custom extraction instructions"),
    model: str = Field(default="gpt-4o-mini", description="LLM model for extraction"),
    validation: bool = Field(default=True, description="Validate against schema"),
    multiple: bool = Field(default=False, description="Extract multiple matching items")
) -> ExtractedData:
    """
    Extract structured data from web pages using schema-driven approach.
    
    Uses LLM to intelligently extract data matching the provided schema.
    Supports complex nested structures and validation.
    """
```

#### 4.1.7 Search Tool

```python
@mcp.tool()
async def freecrawl_search(
    query: str = Field(..., description="Search query"),
    limit: int = Field(default=10, description="Maximum results", ge=1, le=100),
    search_engine: Literal["duckduckgo", "google", "bing"] = Field(
        default="duckduckgo",
        description="Search engine to use"
    ),
    region: Optional[str] = Field(None, description="Region code (e.g., 'us-en', 'uk-en')"),
    safe_search: bool = Field(default=True, description="Enable safe search"),
    scrape_results: bool = Field(default=False, description="Scrape content from result URLs"),
    scrape_options: Optional[Dict[str, Any]] = Field(None, description="Options for scraping results")
) -> SearchResult:
    """
    Perform web search and optionally scrape results.
    
    Searches using specified engine and can automatically scrape
    the resulting pages for full content extraction.
    """
```

### 4.2 Error Handling

#### Error Response Format

```python
class ErrorResponse(BaseModel):
    """Standard error response format"""
    error: str  # Error type/code
    message: str  # Human-readable message
    details: Optional[Dict[str, Any]] = None  # Additional context
    timestamp: datetime
    request_id: Optional[str] = None
    retry_after: Optional[int] = None  # Seconds until retry allowed
```

#### Error Types and Codes

```python
class ErrorCode(Enum):
    # Client errors (4xx equivalent)
    INVALID_URL = "invalid_url"
    INVALID_SCHEMA = "invalid_schema"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    
    # Server errors (5xx equivalent)
    BROWSER_ERROR = "browser_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    PROCESSING_ERROR = "processing_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    
    # Anti-bot detection
    BOT_DETECTED = "bot_detected"
    CAPTCHA_REQUIRED = "captcha_required"
    IP_BLOCKED = "ip_blocked"
```

### 4.3 Rate Limiting

```python
class RateLimiter:
    """Token bucket rate limiter with per-domain tracking"""
    
    def __init__(self):
        self.limits = {
            "default": RateLimit(requests=60, window=60),  # 60 req/min
            "aggressive": RateLimit(requests=10, window=60),  # 10 req/min
            "relaxed": RateLimit(requests=120, window=60),  # 120 req/min
        }
        self.domain_buckets: Dict[str, TokenBucket] = {}
    
    async def check_rate_limit(self, domain: str) -> bool:
        """Check if request is allowed for domain"""
        bucket = self.get_bucket(domain)
        return await bucket.consume(1)
    
    def get_limit_info(self, domain: str) -> Dict[str, Any]:
        """Get current rate limit status"""
        bucket = self.get_bucket(domain)
        return {
            "remaining": bucket.tokens,
            "limit": bucket.capacity,
            "reset_at": bucket.next_refill,
            "window_seconds": bucket.window
        }
```

## 5. Implementation Details

### 5.1 Core Algorithms

#### 5.1.1 Intelligent Content Extraction

```python
class ContentExtractor:
    """Multi-strategy content extraction with fallback"""
    
    async def extract(self, html: str, url: str) -> ScrapedContent:
        """Extract content using best available method"""
        
        # Strategy 1: Readability-based extraction
        try:
            content = await self.extract_with_readability(html)
            if self.validate_content(content):
                return content
        except Exception:
            pass
        
        # Strategy 2: Schema.org structured data
        try:
            content = await self.extract_structured_data(html)
            if content:
                return content
        except Exception:
            pass
        
        # Strategy 3: Heuristic-based extraction
        try:
            content = await self.extract_with_heuristics(html)
            return content
        except Exception:
            pass
        
        # Fallback: Basic HTML parsing
        return await self.basic_extraction(html)
    
    async def extract_with_readability(self, html: str) -> Optional[Dict]:
        """Use readability algorithm for article extraction"""
        # Implementation of Mozilla Readability algorithm
        pass
    
    async def extract_structured_data(self, html: str) -> Optional[Dict]:
        """Extract JSON-LD, microdata, and RDFa"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract JSON-LD
        json_ld = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                json_ld.append(json.loads(script.string))
            except json.JSONDecodeError:
                continue
        
        # Extract microdata
        microdata = self.extract_microdata(soup)
        
        # Extract RDFa
        rdfa = self.extract_rdfa(soup)
        
        return {
            "json_ld": json_ld,
            "microdata": microdata,
            "rdfa": rdfa
        }
```

#### 5.1.2 Anti-Detection System

```python
class AntiDetectionService:
    """Comprehensive anti-bot detection evasion"""
    
    def __init__(self):
        self.user_agents = self.load_user_agents()
        self.fingerprints = self.generate_fingerprints()
        
    async def prepare_browser(self, context: BrowserContext) -> None:
        """Configure browser for stealth operation"""
        
        # Randomize user agent
        ua = random.choice(self.user_agents)
        
        # Set realistic viewport
        viewport = self.get_random_viewport()
        
        # Configure browser
        await context.add_init_script("""
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Add chrome object
            window.chrome = {
                runtime: {},
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Add realistic plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    }
                ]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Add battery API
            navigator.getBattery = () => Promise.resolve({
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1
            });
            
            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'MacIntel'
            });
            
            // Add WebGL vendor
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
        """)
        
        # Set headers
        await context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': ua,
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        })
    
    async def handle_challenge(self, page: Page) -> bool:
        """Detect and handle anti-bot challenges"""
        
        # Check for common challenge indicators
        challenges = {
            'cloudflare': 'cf-browser-verification',
            'recaptcha': 'g-recaptcha',
            'hcaptcha': 'h-captcha',
            'datadome': 'dd-request-id',
        }
        
        content = await page.content()
        
        for provider, indicator in challenges.items():
            if indicator in content:
                return await self.solve_challenge(page, provider)
        
        return True
    
    def get_random_viewport(self) -> Dict[str, int]:
        """Generate realistic viewport dimensions"""
        viewports = [
            {"width": 1920, "height": 1080},  # Full HD
            {"width": 1366, "height": 768},   # Common laptop
            {"width": 1440, "height": 900},   # MacBook
            {"width": 1536, "height": 864},   # Surface
            {"width": 1280, "height": 720},   # HD
        ]
        return random.choice(viewports)
```

#### 5.1.3 Concurrent Processing Manager

```python
class ConcurrentProcessor:
    """Manage concurrent scraping with resource limits"""
    
    def __init__(self, max_browsers: int = 5, max_concurrent: int = 50):
        self.browser_pool = BrowserPool(max_browsers)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.stats = ProcessingStats()
        
    async def process_batch(
        self,
        tasks: List[ScrapingTask],
        progress_callback: Optional[Callable] = None
    ) -> List[ScrapedContent]:
        """Process multiple tasks concurrently"""
        
        results = []
        queue = asyncio.Queue()
        
        # Add tasks to queue
        for task in tasks:
            await queue.put(task)
        
        # Create workers
        workers = []
        for i in range(min(len(tasks), self.max_concurrent)):
            worker = asyncio.create_task(
                self.worker(queue, results, progress_callback)
            )
            workers.append(worker)
        
        # Wait for completion
        await queue.join()
        
        # Cancel workers
        for worker in workers:
            worker.cancel()
        
        return results
    
    async def worker(
        self,
        queue: asyncio.Queue,
        results: List,
        progress_callback: Optional[Callable]
    ):
        """Worker coroutine for processing tasks"""
        while True:
            try:
                task = await queue.get()
                
                async with self.semaphore:
                    result = await self.process_single(task)
                    results.append(result)
                    
                    if progress_callback:
                        await progress_callback(len(results), queue.qsize())
                
                queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats.record_error(e)
                queue.task_done()
```

### 5.2 State Management

```python
class StateManager:
    """Centralized state management for the server"""
    
    def __init__(self):
        self.active_sessions: Dict[str, Session] = {}
        self.browser_pool: BrowserPool = None
        self.cache: CacheManager = None
        self.metrics: MetricsCollector = None
        self.config: ServerConfig = None
        
    async def initialize(self, config: ServerConfig):
        """Initialize all stateful components"""
        self.config = config
        
        # Initialize browser pool
        self.browser_pool = BrowserPool(
            max_browsers=config.max_browsers,
            browser_options=config.browser_options
        )
        await self.browser_pool.initialize()
        
        # Initialize cache
        self.cache = CacheManager(
            cache_dir=config.cache_dir,
            max_size=config.cache_max_size,
            ttl=config.cache_ttl
        )
        
        # Initialize metrics
        self.metrics = MetricsCollector()
        
    async def cleanup(self):
        """Cleanup all resources"""
        await self.browser_pool.cleanup()
        await self.cache.cleanup()
        
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get or create session"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = Session(session_id)
        return self.active_sessions[session_id]

class Session:
    """Individual session state"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.request_count = 0
        self.error_count = 0
        self.cookies: Dict[str, Dict[str, str]] = {}  # Domain -> cookies
        self.headers: Dict[str, str] = {}
        self.proxy: Optional[str] = None
```

### 5.3 Caching Strategy

```python
class CacheManager:
    """Intelligent caching with TTL and size limits"""
    
    def __init__(self, cache_dir: str, max_size: int, ttl: int):
        self.cache_dir = Path(cache_dir)
        self.max_size = max_size  # bytes
        self.ttl = ttl  # seconds
        self.db = self.init_db()
        self.current_size = self.calculate_size()
        
    def init_db(self) -> sqlite3.Connection:
        """Initialize SQLite cache database"""
        db_path = self.cache_dir / "cache.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                content_type TEXT NOT NULL,
                data BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                hit_count INTEGER DEFAULT 0,
                size_bytes INTEGER NOT NULL
            )
        """)
        return conn
    
    async def get(
        self,
        url: str,
        cache_key: Optional[str] = None
    ) -> Optional[ScrapedContent]:
        """Retrieve cached content if valid"""
        key = cache_key or self.generate_key(url)
        
        cursor = self.db.execute(
            "SELECT data, expires_at FROM cache_entries WHERE cache_key = ?",
            (key,)
        )
        row = cursor.fetchone()
        
        if row:
            data, expires_at = row
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                # Expired
                await self.delete(key)
                return None
            
            # Update hit count
            self.db.execute(
                "UPDATE cache_entries SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (key,)
            )
            
            # Decompress and deserialize
            content = pickle.loads(gzip.decompress(data))
            return ScrapedContent(**content)
        
        return None
    
    async def set(
        self,
        url: str,
        content: ScrapedContent,
        ttl: Optional[int] = None
    ) -> str:
        """Cache scraped content"""
        key = self.generate_key(url)
        
        # Serialize and compress
        data = gzip.compress(pickle.dumps(content.dict()))
        size = len(data)
        
        # Check size limits
        if size > self.max_size * 0.1:  # Single item shouldn't exceed 10% of cache
            return key
        
        # Evict if necessary
        while self.current_size + size > self.max_size:
            await self.evict_lru()
        
        # Store
        expires_at = datetime.now() + timedelta(seconds=ttl or self.ttl)
        self.db.execute(
            """
            INSERT OR REPLACE INTO cache_entries 
            (cache_key, url, content_type, data, expires_at, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, url, "scraped_content", data, expires_at, size)
        )
        self.db.commit()
        self.current_size += size
        
        return key
    
    async def evict_lru(self):
        """Evict least recently used entry"""
        cursor = self.db.execute(
            """
            SELECT cache_key, size_bytes FROM cache_entries
            ORDER BY hit_count ASC, created_at ASC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        
        if row:
            key, size = row
            await self.delete(key)
            self.current_size -= size
    
    def generate_key(self, url: str) -> str:
        """Generate cache key from URL"""
        return hashlib.md5(url.encode()).hexdigest()
```

### 5.4 Background Jobs

```python
class BackgroundJobManager:
    """Manage background tasks and maintenance"""
    
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
        self.jobs: List[asyncio.Task] = []
        
    async def start(self):
        """Start all background jobs"""
        self.jobs = [
            asyncio.create_task(self.cleanup_job()),
            asyncio.create_task(self.metrics_job()),
            asyncio.create_task(self.health_check_job()),
            asyncio.create_task(self.cache_maintenance_job()),
        ]
    
    async def stop(self):
        """Stop all background jobs"""
        for job in self.jobs:
            job.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
    
    async def cleanup_job(self):
        """Periodic cleanup of resources"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                
                # Clean expired sessions
                now = datetime.now()
                expired = []
                for sid, session in self.state.active_sessions.items():
                    if (now - session.last_activity).seconds > 3600:  # 1 hour
                        expired.append(sid)
                
                for sid in expired:
                    del self.state.active_sessions[sid]
                
                # Clean browser pool
                await self.state.browser_pool.cleanup_idle()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup job error: {e}")
    
    async def metrics_job(self):
        """Collect and report metrics"""
        while True:
            try:
                await asyncio.sleep(60)  # Every minute
                
                metrics = {
                    "active_sessions": len(self.state.active_sessions),
                    "browser_pool_size": self.state.browser_pool.size,
                    "cache_hit_rate": self.state.cache.get_hit_rate(),
                    "memory_usage": psutil.Process().memory_info().rss,
                    "cpu_percent": psutil.Process().cpu_percent(),
                }
                
                await self.state.metrics.record(metrics)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics job error: {e}")
```

## 6. Security Considerations

### 6.1 Authentication/Authorization

```python
class SecurityManager:
    """Handle security concerns"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.rate_limiter = RateLimiter()
        
    async def validate_request(self, request: Dict[str, Any]) -> bool:
        """Validate incoming request"""
        
        # Check API key if configured
        if self.config.require_api_key:
            api_key = request.get("api_key")
            if not self.validate_api_key(api_key):
                raise UnauthorizedError("Invalid API key")
        
        # Validate URL
        url = request.get("url")
        if url and not self.validate_url(url):
            raise ValidationError("Invalid or forbidden URL")
        
        # Check rate limits
        if not await self.rate_limiter.check_rate_limit(request.get("client_id")):
            raise RateLimitError("Rate limit exceeded")
        
        return True
    
    def validate_url(self, url: str) -> bool:
        """Validate URL safety"""
        parsed = urlparse(url)
        
        # Block private IPs
        if self.is_private_ip(parsed.hostname):
            return False
        
        # Block file:// URLs
        if parsed.scheme not in ["http", "https"]:
            return False
        
        # Check against blocklist
        if parsed.hostname in self.config.blocked_domains:
            return False
        
        return True
    
    def is_private_ip(self, hostname: str) -> bool:
        """Check if IP is private/local"""
        try:
            ip = ipaddress.ip_address(hostname)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            # Not an IP, resolve hostname
            try:
                ip = ipaddress.ip_address(socket.gethostbyname(hostname))
                return ip.is_private or ip.is_loopback or ip.is_link_local
            except (socket.gaierror, ValueError):
                return False
```

### 6.2 Data Encryption

```python
class EncryptionService:
    """Handle sensitive data encryption"""
    
    def __init__(self, key: Optional[bytes] = None):
        self.key = key or Fernet.generate_key()
        self.cipher = Fernet(self.key)
    
    def encrypt_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive fields in data"""
        sensitive_fields = ["password", "api_key", "token", "secret"]
        encrypted = data.copy()
        
        for field in sensitive_fields:
            if field in encrypted:
                encrypted[field] = self.cipher.encrypt(
                    encrypted[field].encode()
                ).decode()
        
        return encrypted
    
    def decrypt_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive fields in data"""
        # Implementation
        pass
```

### 6.3 Input Validation

```python
class InputValidator:
    """Comprehensive input validation"""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format and safety"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    @staticmethod
    def validate_schema(schema: Dict[str, Any]) -> bool:
        """Validate JSON schema"""
        try:
            Draft7Validator.check_schema(schema)
            return True
        except SchemaError:
            return False
    
    @staticmethod
    def sanitize_html(html: str) -> str:
        """Remove dangerous HTML elements"""
        return bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True
        )
```

### 6.4 Audit Logging

```python
class AuditLogger:
    """Security audit logging"""
    
    def __init__(self, log_file: str):
        self.logger = self.setup_logger(log_file)
    
    async def log_request(
        self,
        request_id: str,
        client_id: str,
        action: str,
        details: Dict[str, Any]
    ):
        """Log security-relevant events"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
            "client_id": client_id,
            "action": action,
            "details": details,
            "ip_address": details.get("ip_address"),
            "user_agent": details.get("user_agent"),
        }
        
        self.logger.info(json.dumps(entry))
        
        # Alert on suspicious activity
        if self.is_suspicious(action, details):
            await self.send_alert(entry)
    
    def is_suspicious(self, action: str, details: Dict) -> bool:
        """Detect suspicious patterns"""
        suspicious_patterns = [
            "multiple_failed_auth",
            "rapid_requests",
            "sql_injection_attempt",
            "xss_attempt",
            "path_traversal",
        ]
        
        return any(pattern in str(details) for pattern in suspicious_patterns)
```

## 7. Performance Requirements

### 7.1 Response Time Targets

| Operation | Target (p50) | Target (p95) | Target (p99) | Max Timeout |
|-----------|--------------|--------------|--------------|-------------|
| Single URL Scrape | 2s | 5s | 10s | 30s |
| Batch Scrape (10 URLs) | 5s | 10s | 20s | 60s |
| Document Processing | 1s | 3s | 5s | 30s |
| Site Mapping | 3s | 8s | 15s | 60s |
| Search | 1s | 2s | 3s | 10s |
| Health Check | 50ms | 100ms | 200ms | 1s |

### 7.2 Throughput Requirements

```python
class PerformanceTargets:
    """System performance targets"""
    
    # Concurrent capacity
    MAX_CONCURRENT_REQUESTS = 50
    MAX_CONCURRENT_BROWSERS = 10
    MAX_CONNECTIONS_PER_DOMAIN = 5
    
    # Rate limits
    DEFAULT_RPS = 100  # Requests per second
    BURST_RPS = 200    # Burst capacity
    
    # Resource limits
    MAX_MEMORY_MB = 2048
    MAX_CPU_PERCENT = 80
    MAX_RESPONSE_SIZE_MB = 50
    
    # Cache performance
    CACHE_HIT_RATE_TARGET = 0.3  # 30% hit rate
    CACHE_LOOKUP_TIME_MS = 10
```

### 7.3 Resource Constraints

```python
class ResourceMonitor:
    """Monitor and enforce resource constraints"""
    
    def __init__(self, limits: PerformanceTargets):
        self.limits = limits
        self.process = psutil.Process()
        
    async def check_resources(self) -> Dict[str, Any]:
        """Check current resource usage"""
        return {
            "memory_mb": self.process.memory_info().rss / 1024 / 1024,
            "cpu_percent": self.process.cpu_percent(),
            "open_files": len(self.process.open_files()),
            "num_threads": self.process.num_threads(),
            "connections": len(self.process.connections()),
        }
    
    async def enforce_limits(self):
        """Enforce resource limits"""
        stats = await self.check_resources()
        
        # Memory limit
        if stats["memory_mb"] > self.limits.MAX_MEMORY_MB:
            await self.reduce_memory_usage()
        
        # CPU limit
        if stats["cpu_percent"] > self.limits.MAX_CPU_PERCENT:
            await self.throttle_processing()
    
    async def reduce_memory_usage(self):
        """Reduce memory consumption"""
        # Clear caches
        gc.collect()
        
        # Reduce browser pool
        await self.state.browser_pool.reduce_size()
        
        # Clear old sessions
        await self.state.cleanup_old_sessions()
```

## 8. Testing Strategy

### 8.1 Unit Test Approach

```python
# test_core.py
import pytest
from unittest.mock import Mock, patch, AsyncMock

class TestContentExtractor:
    """Unit tests for content extraction"""
    
    @pytest.fixture
    def extractor(self):
        return ContentExtractor()
    
    @pytest.mark.asyncio
    async def test_extract_markdown(self, extractor):
        """Test markdown extraction from HTML"""
        html = "<h1>Title</h1><p>Content</p>"
        result = await extractor.extract(html, "http://example.com")
        
        assert result.markdown == "# Title\n\nContent"
        assert result.title == "Title"
    
    @pytest.mark.asyncio
    async def test_extract_structured_data(self, extractor):
        """Test structured data extraction"""
        html = '''
        <script type="application/ld+json">
        {"@type": "Article", "headline": "Test"}
        </script>
        '''
        result = await extractor.extract_structured_data(html)
        
        assert result["json_ld"][0]["headline"] == "Test"
    
    @pytest.mark.asyncio
    async def test_fallback_extraction(self, extractor):
        """Test fallback when primary methods fail"""
        html = "<div>Basic content</div>"
        
        with patch.object(extractor, 'extract_with_readability', side_effect=Exception):
            result = await extractor.extract(html, "http://example.com")
        
        assert "Basic content" in result.text

class TestAntiDetection:
    """Unit tests for anti-detection measures"""
    
    @pytest.fixture
    def anti_detect(self):
        return AntiDetectionService()
    
    @pytest.mark.asyncio
    async def test_browser_preparation(self, anti_detect):
        """Test browser stealth configuration"""
        mock_context = AsyncMock()
        
        await anti_detect.prepare_browser(mock_context)
        
        # Verify init script was added
        mock_context.add_init_script.assert_called_once()
        
        # Verify headers were set
        mock_context.set_extra_http_headers.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_challenge_detection(self, anti_detect):
        """Test anti-bot challenge detection"""
        mock_page = AsyncMock()
        mock_page.content.return_value = '<div class="cf-browser-verification"></div>'
        
        detected = await anti_detect.handle_challenge(mock_page)
        
        assert detected is True  # Challenge detected
```

### 8.2 Integration Test Scenarios

```python
# test_integration.py
class TestEndToEnd:
    """Integration tests for complete workflows"""
    
    @pytest.fixture
    async def server(self):
        """Setup test server"""
        config = ServerConfig(
            max_browsers=2,
            cache_ttl=60,
            transport="stdio"
        )
        server = FreeCrawlServer(config)
        await server.initialize()
        yield server
        await server.cleanup()
    
    @pytest.mark.asyncio
    async def test_scrape_website(self, server, httpserver):
        """Test complete scraping workflow"""
        # Setup mock website
        httpserver.expect_request("/").respond_with_data(
            "<html><body><h1>Test Page</h1></body></html>"
        )
        
        # Perform scrape
        result = await server.freecrawl_scrape(
            url=httpserver.url_for("/"),
            formats=["markdown", "html"]
        )
        
        # Verify results
        assert result.title == "Test Page"
        assert "# Test Page" in result.markdown
        assert result.metadata.status_code == 200
    
    @pytest.mark.asyncio
    async def test_concurrent_scraping(self, server, httpserver):
        """Test concurrent request handling"""
        # Setup multiple endpoints
        for i in range(10):
            httpserver.expect_request(f"/page{i}").respond_with_data(
                f"<html><body>Page {i}</body></html>"
            )
        
        # Scrape concurrently
        urls = [httpserver.url_for(f"/page{i}") for i in range(10)]
        results = await server.freecrawl_batch(
            urls=urls,
            concurrency=5
        )
        
        # Verify all succeeded
        assert len(results) == 10
        assert all(r.metadata.status_code == 200 for r in results)
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, server):
        """Test rate limiting enforcement"""
        # Exhaust rate limit
        tasks = []
        for _ in range(100):
            tasks.append(
                server.freecrawl_scrape("http://example.com")
            )
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Some should be rate limited
        errors = [r for r in results if isinstance(r, RateLimitError)]
        assert len(errors) > 0
```

### 8.3 Performance Test Plans

```python
# test_performance.py
class TestPerformance:
    """Performance and load tests"""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_throughput(self, server, benchmark_sites):
        """Test maximum throughput"""
        start = time.time()
        
        # Process 100 URLs
        results = await server.freecrawl_batch(
            urls=benchmark_sites[:100],
            concurrency=20
        )
        
        duration = time.time() - start
        rps = len(results) / duration
        
        # Assert minimum throughput
        assert rps >= 5  # At least 5 requests per second
        
        # Check resource usage
        stats = await server.state.resource_monitor.check_resources()
        assert stats["memory_mb"] < 1024  # Less than 1GB
        assert stats["cpu_percent"] < 90   # Less than 90% CPU
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_memory_leak(self, server):
        """Test for memory leaks during extended operation"""
        initial_memory = psutil.Process().memory_info().rss
        
        # Run 1000 requests
        for _ in range(100):
            await server.freecrawl_batch(
                urls=["http://example.com"] * 10,
                concurrency=5
            )
            
            # Force garbage collection
            gc.collect()
        
        final_memory = psutil.Process().memory_info().rss
        memory_growth = (final_memory - initial_memory) / initial_memory
        
        # Memory growth should be less than 20%
        assert memory_growth < 0.2
    
    @pytest.mark.asyncio
    async def test_cache_performance(self, server):
        """Test cache hit rate and performance"""
        url = "http://example.com/cached"
        
        # First request (cache miss)
        start = time.time()
        result1 = await server.freecrawl_scrape(url)
        miss_time = time.time() - start
        
        # Second request (cache hit)
        start = time.time()
        result2 = await server.freecrawl_scrape(url)
        hit_time = time.time() - start
        
        # Cache hit should be much faster
        assert hit_time < miss_time * 0.1  # 10x faster
        
        # Content should be identical
        assert result1.markdown == result2.markdown
```

## 9. Deployment & Operations

### 9.1 Configuration Requirements

```python
# freecrawl_server.py - Configuration section
#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "fastmcp>=0.3.0",
#   "playwright>=1.40.0",
#   "unstructured[all-docs]>=0.15.0",
#   "aiohttp>=3.9.0",
#   "beautifulsoup4>=4.12.0",
#   "markdownify>=0.11.0",
#   "pydantic>=2.0.0",
#   "tenacity>=8.0.0",
#   "psutil>=5.9.0",
#   "cryptography>=41.0.0",
# ]
# ///

import os
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ServerConfig:
    """FreeCrawl server configuration"""
    
    # Transport
    transport: str = os.getenv("FREECRAWL_TRANSPORT", "stdio")
    http_port: int = int(os.getenv("FREECRAWL_PORT", "8000"))
    
    # Browser pool
    max_browsers: int = int(os.getenv("FREECRAWL_MAX_BROWSERS", "5"))
    browser_headless: bool = os.getenv("FREECRAWL_HEADLESS", "true").lower() == "true"
    browser_timeout: int = int(os.getenv("FREECRAWL_BROWSER_TIMEOUT", "30000"))
    
    # Concurrency
    max_concurrent: int = int(os.getenv("FREECRAWL_MAX_CONCURRENT", "50"))
    max_per_domain: int = int(os.getenv("FREECRAWL_MAX_PER_DOMAIN", "5"))
    
    # Cache
    cache_enabled: bool = os.getenv("FREECRAWL_CACHE", "true").lower() == "true"
    cache_dir: Path = Path(os.getenv("FREECRAWL_CACHE_DIR", "/tmp/freecrawl_cache"))
    cache_ttl: int = int(os.getenv("FREECRAWL_CACHE_TTL", "3600"))
    cache_max_size: int = int(os.getenv("FREECRAWL_CACHE_SIZE", "1073741824"))  # 1GB
    
    # Security
    require_api_key: bool = os.getenv("FREECRAWL_REQUIRE_API_KEY", "false").lower() == "true"
    api_keys: list = os.getenv("FREECRAWL_API_KEYS", "").split(",") if os.getenv("FREECRAWL_API_KEYS") else []
    blocked_domains: list = os.getenv("FREECRAWL_BLOCKED_DOMAINS", "").split(",") if os.getenv("FREECRAWL_BLOCKED_DOMAINS") else []
    
    # Anti-detection
    anti_detect: bool = os.getenv("FREECRAWL_ANTI_DETECT", "true").lower() == "true"
    user_agent_rotation: bool = os.getenv("FREECRAWL_ROTATE_UA", "true").lower() == "true"
    proxy_list: list = os.getenv("FREECRAWL_PROXIES", "").split(",") if os.getenv("FREECRAWL_PROXIES") else []
    
    # Performance
    rate_limit_default: int = int(os.getenv("FREECRAWL_RATE_LIMIT", "60"))
    request_timeout: int = int(os.getenv("FREECRAWL_REQUEST_TIMEOUT", "30"))
    max_response_size: int = int(os.getenv("FREECRAWL_MAX_RESPONSE", "52428800"))  # 50MB
    
    # Monitoring
    metrics_enabled: bool = os.getenv("FREECRAWL_METRICS", "true").lower() == "true"
    log_level: str = os.getenv("FREECRAWL_LOG_LEVEL", "INFO")
    audit_log: bool = os.getenv("FREECRAWL_AUDIT_LOG", "false").lower() == "true"
```

### 9.2 Single-File Script Implementation

```python
# freecrawl_server.py - Main implementation structure

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

# Configure logging
logging.basicConfig(
    level=getattr(logging, ServerConfig().log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# [Previous configuration section...]

# === Core Implementation ===

class FreeCrawlServer:
    """Main FreeCrawl MCP server implementation"""
    
    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self.state = StateManager()
        self.mcp = self.setup_mcp()
        
    def setup_mcp(self):
        """Setup MCP server with tools"""
        from fastmcp import FastMCP
        
        mcp = FastMCP(
            name="FreeCrawl",
            version="1.0.0",
            description="Web scraping and document processing MCP server"
        )
        
        # Register all tools
        mcp.tool()(self.freecrawl_scrape)
        mcp.tool()(self.freecrawl_batch)
        mcp.tool()(self.freecrawl_crawl)
        mcp.tool()(self.freecrawl_map)
        mcp.tool()(self.freecrawl_process_document)
        mcp.tool()(self.freecrawl_extract)
        mcp.tool()(self.freecrawl_search)
        mcp.tool()(self.health_check)
        
        return mcp
    
    async def initialize(self):
        """Initialize server components"""
        logger.info("Initializing FreeCrawl server...")
        
        # Initialize state manager
        await self.state.initialize(self.config)
        
        # Install Playwright browsers if needed
        if not await self.check_browsers():
            logger.info("Installing Playwright browsers...")
            await self.install_browsers()
        
        # Start background jobs
        self.job_manager = BackgroundJobManager(self.state)
        await self.job_manager.start()
        
        logger.info("FreeCrawl server initialized successfully")
    
    async def cleanup(self):
        """Cleanup server resources"""
        logger.info("Shutting down FreeCrawl server...")
        
        # Stop background jobs
        await self.job_manager.stop()
        
        # Cleanup state
        await self.state.cleanup()
        
        logger.info("FreeCrawl server shutdown complete")
    
    async def run(self):
        """Run the server"""
        await self.initialize()
        
        try:
            if self.config.transport == "http":
                # HTTP/SSE transport
                await self.run_http()
            else:
                # STDIO transport (default)
                await self.run_stdio()
        finally:
            await self.cleanup()
    
    async def run_stdio(self):
        """Run with STDIO transport"""
        from fastmcp.server import StdioTransport
        
        transport = StdioTransport()
        await self.mcp.run(transport)
    
    async def run_http(self):
        """Run with HTTP/SSE transport"""
        from aiohttp import web
        
        app = web.Application()
        
        # Setup routes
        app.router.add_post('/tools/{tool_name}', self.handle_http_request)
        app.router.add_get('/health', self.handle_health_check)
        app.router.add_get('/metrics', self.handle_metrics)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.config.http_port)
        
        logger.info(f"Starting HTTP server on port {self.config.http_port}")
        await site.start()
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
    
    # === Tool Implementations ===
    
    async def freecrawl_scrape(self, **kwargs) -> Dict[str, Any]:
        """Implementation of scrape tool"""
        # [Full implementation as specified in API section]
        pass
    
    # [Other tool implementations...]
    
    # === Helper Methods ===
    
    async def check_browsers(self) -> bool:
        """Check if Playwright browsers are installed"""
        from playwright.async_api import async_playwright
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()
                return True
        except Exception:
            return False
    
    async def install_browsers(self):
        """Install Playwright browsers"""
        import subprocess
        subprocess.run(["playwright", "install", "chromium"], check=True)

# === Entry Point ===

def main():
    """Main entry point"""
    import sys
    
    # Parse command line arguments
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
FreeCrawl MCP Server

Usage:
  freecrawl_server.py [options]

Options:
  --http          Use HTTP transport instead of STDIO
  --port PORT     HTTP port (default: 8000)
  --config FILE   Load configuration from file
  --help          Show this help message

Environment Variables:
  FREECRAWL_TRANSPORT    Transport type (stdio|http)
  FREECRAWL_PORT         HTTP port
  FREECRAWL_MAX_BROWSERS Maximum browser instances
  [... other environment variables ...]

Examples:
  # Run with STDIO (default)
  ./freecrawl_server.py
  
  # Run with HTTP
  ./freecrawl_server.py --http --port 8080
  
  # Run with environment config
  FREECRAWL_TRANSPORT=http FREECRAWL_PORT=8000 ./freecrawl_server.py
        """)
        sys.exit(0)
    
    # Override config from command line
    config = ServerConfig()
    if "--http" in sys.argv:
        config.transport = "http"
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        config.http_port = int(sys.argv[idx + 1])
    
    # Run server
    server = FreeCrawlServer(config)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 9.3 Production Considerations

#### Containerization

```dockerfile
# Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libmagic-dev \
    poppler-utils \
    tesseract-ocr \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy server script
COPY freecrawl_server.py /app/

# Set working directory
WORKDIR /app

# Install Python dependencies (handled by uv)
RUN uv pip install --system playwright unstructured

# Install Playwright browsers
RUN playwright install chromium

# Expose HTTP port
EXPOSE 8000

# Run server
CMD ["python", "freecrawl_server.py", "--http"]
```

#### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  freecrawl:
    build: .
    ports:
      - "8000:8000"
    environment:
      FREECRAWL_TRANSPORT: http
      FREECRAWL_MAX_BROWSERS: 10
      FREECRAWL_CACHE_DIR: /data/cache
      FREECRAWL_LOG_LEVEL: INFO
    volumes:
      - freecrawl-cache:/data/cache
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'

volumes:
  freecrawl-cache:
```

#### Systemd Service

```ini
# /etc/systemd/system/freecrawl.service
[Unit]
Description=FreeCrawl MCP Server
After=network.target

[Service]
Type=simple
User=freecrawl
Group=freecrawl
WorkingDirectory=/opt/freecrawl
Environment="FREECRAWL_TRANSPORT=http"
Environment="FREECRAWL_PORT=8000"
Environment="FREECRAWL_MAX_BROWSERS=10"
ExecStart=/usr/bin/python3 /opt/freecrawl/freecrawl_server.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/freecrawl/server.log
StandardError=append:/var/log/freecrawl/error.log

# Resource limits
LimitNOFILE=65536
MemoryLimit=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

## 10. Monitoring & Observability

### 10.1 Health Checks

```python
class HealthChecker:
    """System health monitoring"""
    
    async def check_health(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        checks = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "checks": {}
        }
        
        # Check browser pool
        try:
            browser_health = await self.check_browser_pool()
            checks["checks"]["browser_pool"] = browser_health
        except Exception as e:
            checks["checks"]["browser_pool"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            checks["status"] = "degraded"
        
        # Check cache
        try:
            cache_health = await self.check_cache()
            checks["checks"]["cache"] = cache_health
        except Exception as e:
            checks["checks"]["cache"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check memory
        memory_health = self.check_memory()
        checks["checks"]["memory"] = memory_health
        if memory_health["status"] == "unhealthy":
            checks["status"] = "degraded"
        
        # Check external connectivity
        connectivity = await self.check_connectivity()
        checks["checks"]["connectivity"] = connectivity
        
        return checks
    
    def check_memory(self) -> Dict[str, Any]:
        """Check memory usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        return {
            "status": "healthy" if memory_mb < 1500 else "warning" if memory_mb < 2000 else "unhealthy",
            "memory_mb": memory_mb,
            "threshold_mb": 2000
        }
```

### 10.2 Metrics Collection

```python
class MetricsCollector:
    """Collect and expose metrics"""
    
    def __init__(self):
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "response_time_sum": 0,
            "response_time_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "browser_pool_size": 0,
            "active_sessions": 0,
        }
        self.histograms = {
            "response_time": [],
            "content_size": [],
        }
    
    async def record_request(
        self,
        tool: str,
        success: bool,
        response_time: float,
        content_size: int = 0
    ):
        """Record request metrics"""
        self.metrics["requests_total"] += 1
        
        if success:
            self.metrics["requests_success"] += 1
        else:
            self.metrics["requests_failed"] += 1
        
        self.metrics["response_time_sum"] += response_time
        self.metrics["response_time_count"] += 1
        
        # Update histograms
        self.histograms["response_time"].append(response_time)
        if content_size:
            self.histograms["content_size"].append(content_size)
        
        # Trim histograms to last 1000 entries
        for key in self.histograms:
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        avg_response_time = (
            self.metrics["response_time_sum"] / self.metrics["response_time_count"]
            if self.metrics["response_time_count"] > 0
            else 0
        )
        
        return {
            "counters": self.metrics,
            "gauges": {
                "avg_response_time": avg_response_time,
                "cache_hit_rate": self.calculate_cache_hit_rate(),
                "success_rate": self.calculate_success_rate(),
            },
            "histograms": {
                "response_time_p50": self.percentile(self.histograms["response_time"], 50),
                "response_time_p95": self.percentile(self.histograms["response_time"], 95),
                "response_time_p99": self.percentile(self.histograms["response_time"], 99),
            }
        }
```

### 10.3 Operational Requirements

#### Logging Configuration

```python
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "json": {
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "level": "INFO"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "/var/log/freecrawl/server.log",
            "maxBytes": 104857600,  # 100MB
            "backupCount": 10,
            "level": "DEBUG"
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "/var/log/freecrawl/error.log",
            "maxBytes": 104857600,
            "backupCount": 10,
            "level": "ERROR"
        }
    },
    "loggers": {
        "freecrawl": {
            "handlers": ["console", "file", "error_file"],
            "level": "DEBUG",
            "propagate": False
        }
    }
}
```

#### Monitoring Dashboard

```python
class MonitoringDashboard:
    """Simple HTML dashboard for monitoring"""
    
    def generate_dashboard(self) -> str:
        """Generate HTML dashboard"""
        metrics = self.metrics_collector.get_metrics()
        health = self.health_checker.check_health()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>FreeCrawl Monitor</title>
            <meta http-equiv="refresh" content="5">
            <style>
                body {{ font-family: monospace; padding: 20px; }}
                .healthy {{ color: green; }}
                .degraded {{ color: orange; }}
                .unhealthy {{ color: red; }}
                .metric {{ margin: 10px 0; }}
                .section {{ margin: 20px 0; border: 1px solid #ccc; padding: 10px; }}
            </style>
        </head>
        <body>
            <h1>FreeCrawl Server Monitor</h1>
            
            <div class="section">
                <h2>Health Status: <span class="{health['status']}">{health['status'].upper()}</span></h2>
                <div>Last Check: {health['timestamp']}</div>
            </div>
            
            <div class="section">
                <h2>Request Metrics</h2>
                <div class="metric">Total Requests: {metrics['counters']['requests_total']}</div>
                <div class="metric">Success Rate: {metrics['gauges']['success_rate']:.2%}</div>
                <div class="metric">Avg Response Time: {metrics['gauges']['avg_response_time']:.2f}s</div>
                <div class="metric">P95 Response Time: {metrics['histograms']['response_time_p95']:.2f}s</div>
            </div>
            
            <div class="section">
                <h2>Cache Performance</h2>
                <div class="metric">Hit Rate: {metrics['gauges']['cache_hit_rate']:.2%}</div>
                <div class="metric">Total Hits: {metrics['counters']['cache_hits']}</div>
                <div class="metric">Total Misses: {metrics['counters']['cache_misses']}</div>
            </div>
            
            <div class="section">
                <h2>Resource Usage</h2>
                <div class="metric">Browser Pool Size: {metrics['counters']['browser_pool_size']}</div>
                <div class="metric">Active Sessions: {metrics['counters']['active_sessions']}</div>
                <div class="metric">Memory Usage: {health['checks']['memory']['memory_mb']:.1f} MB</div>
            </div>
        </body>
        </html>
        """
```

## 11. Migration Path

### 11.1 Firecrawl Compatibility Mode

```python
class FirecrawlCompatibility:
    """Provide Firecrawl-compatible API"""
    
    def __init__(self, server: FreeCrawlServer):
        self.server = server
    
    async def scrape(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Firecrawl-compatible scrape endpoint"""
        # Map Firecrawl parameters to FreeCrawl
        freecrawl_params = {
            "url": params["url"],
            "formats": ["markdown", "html"] if params.get("includeHtml") else ["markdown"],
            "javascript": not params.get("skipJavascript", False),
            "wait_for": params.get("waitFor"),
            "headers": params.get("headers"),
        }
        
        # Call FreeCrawl
        result = await self.server.freecrawl_scrape(**freecrawl_params)
        
        # Map response to Firecrawl format
        return {
            "success": True,
            "data": {
                "url": str(result.url),
                "markdown": result.markdown,
                "html": result.html,
                "metadata": {
                    "title": result.title,
                    "statusCode": result.metadata.status_code,
                },
                "screenshot": result.screenshot,
            }
        }
```

### 11.2 Migration Script

```bash
#!/bin/bash
# migrate_from_firecrawl.sh

echo "FreeCrawl Migration Tool"
echo "======================="

# Check for existing Firecrawl configuration
if [ -f ".env.firecrawl" ]; then
    echo "Found Firecrawl configuration, converting..."
    
    # Convert environment variables
    sed 's/FIRECRAWL_/FREECRAWL_/g' .env.firecrawl > .env.freecrawl
    
    # Update API endpoints in code
    find . -type f -name "*.py" -exec sed -i 's/firecrawl\.dev/localhost:8000/g' {} \;
    find . -type f -name "*.js" -exec sed -i 's/firecrawl\.dev/localhost:8000/g' {} \;
    
    echo "Configuration converted"
fi

# Install FreeCrawl
echo "Installing FreeCrawl..."
curl -sSL https://github.com/your-org/freecrawl/releases/latest/download/freecrawl_server.py -o freecrawl_server.py
chmod +x freecrawl_server.py

# Install dependencies
echo "Installing dependencies..."
./freecrawl_server.py --install-deps

# Test installation
echo "Testing FreeCrawl installation..."
if ./freecrawl_server.py --test; then
    echo "✓ FreeCrawl installed successfully"
else
    echo "✗ Installation failed"
    exit 1
fi

echo ""
echo "Migration complete! Start FreeCrawl with:"
echo "  ./freecrawl_server.py --http --port 8000"
```

### 11.3 Client Library Updates

```python
# freecrawl_client.py - Drop-in replacement for Firecrawl client

class FreeCrawlClient:
    """Client library compatible with Firecrawl API"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
    
    async def scrape_url(self, url: str, **options) -> Dict[str, Any]:
        """Scrape a single URL (Firecrawl-compatible)"""
        # Maintain Firecrawl API compatibility
        response = await self.session.post(
            f"{self.base_url}/scrape",
            json={"url": url, **options},
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        return await response.json()
    
    async def crawl_url(self, url: str, **options) -> Dict[str, Any]:
        """Crawl a website (Firecrawl-compatible)"""
        response = await self.session.post(
            f"{self.base_url}/crawl",
            json={"url": url, **options},
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        return await response.json()
    
    # FreeCrawl-specific enhancements
    async def process_document(self, file_path: str, **options) -> Dict[str, Any]:
        """Process documents with Unstructured (FreeCrawl enhancement)"""
        response = await self.session.post(
            f"{self.base_url}/process",
            json={"file_path": file_path, **options},
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        return await response.json()
```

## Success Metrics

### MVP Success Criteria Validation

- [ ] **Firecrawl Replacement**: 100% API compatibility with migration tools
- [ ] **Website Coverage**: Test suite covering 95%+ of Alexa top 1000 sites
- [ ] **Concurrent Performance**: Load test demonstrating 50+ concurrent requests
- [ ] **Response Time**: P95 < 5 seconds for standard pages
- [ ] **Deployment Simplicity**: Single command installation with auto-dependencies
- [ ] **Memory Efficiency**: Sustained operation under 500MB for normal workload
- [ ] **Error Rate**: <5% failure rate on accessible public websites
- [ ] **Documentation**: Comprehensive API docs with examples
- [ ] **Testing**: >80% code coverage with unit and integration tests
- [ ] **Production Ready**: Health checks, metrics, and operational tooling

## Appendices

### A. Code Examples

#### Basic Usage

```python
#!/usr/bin/env python3
import asyncio
from freecrawl_client import FreeCrawlClient

async def main():
    # Initialize client
    client = FreeCrawlClient()
    
    # Simple scrape
    result = await client.scrape_url(
        "https://example.com",
        formats=["markdown", "screenshot"]
    )
    print(f"Title: {result['title']}")
    print(f"Content: {result['markdown'][:500]}...")
    
    # Batch scraping
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    ]
    results = await client.batch_scrape(urls, concurrency=3)
    
    # Structured extraction
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "number"},
            "availability": {"type": "boolean"}
        }
    }
    
    extracted = await client.extract(
        "https://example.com/product",
        schema=schema
    )
    print(f"Extracted data: {extracted['data']}")

if __name__ == "__main__":
    asyncio.run(main())
```

### B. Configuration Templates

#### Production Configuration

```yaml
# freecrawl-config.yml
server:
  transport: http
  port: 8000
  workers: 4

browser:
  max_instances: 10
  headless: true
  timeout: 30000
  
concurrency:
  max_requests: 100
  per_domain: 5
  
cache:
  enabled: true
  directory: /var/cache/freecrawl
  ttl: 3600
  max_size: 2GB
  
security:
  require_api_key: true
  rate_limit: 100
  blocked_domains:
    - localhost
    - 127.0.0.1
    
monitoring:
  metrics: true
  health_endpoint: /health
  log_level: INFO
```

### C. Troubleshooting Guide

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| High memory usage | Browser pool too large | Reduce `FREECRAWL_MAX_BROWSERS` |
| Slow responses | JavaScript-heavy sites | Increase `wait_for` timeout |
| Bot detection | Missing anti-detection | Enable `anti_bot` flag |
| Cache misses | TTL too short | Increase `FREECRAWL_CACHE_TTL` |
| Connection refused | Wrong transport | Check `FREECRAWL_TRANSPORT` setting |
| Rate limiting | Too many requests | Implement backoff strategy |

---

*This technical specification provides a complete blueprint for implementing the FreeCrawl MCP server. The design prioritizes simplicity, performance, and compatibility while providing significant enhancements over Firecrawl through Unstructured integration and advanced anti-detection capabilities.*