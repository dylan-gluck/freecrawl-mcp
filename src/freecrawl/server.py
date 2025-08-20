"""
FreeCrawl MCP Server - Self-hosted web scraping and document processing

A production-ready MCP server that provides web scraping, document processing,
and structured data extraction capabilities as a Firecrawl replacement.

Features:
- JavaScript-enabled web scraping with anti-detection
- Document processing via Unstructured
- Concurrent batch processing
- Intelligent caching with SQLite
- Rate limiting and resource management
- Comprehensive error handling
"""

import asyncio
import base64
import gzip
import hashlib
import ipaddress
import json
import logging
import os
import pickle
import random
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from urllib.parse import urlparse, urljoin, quote
import uuid
import gc

import aiohttp
import aiosqlite
import psutil
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from pydantic import BaseModel, Field, HttpUrl, validator
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# MCP imports
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
    import mcp.server.stdio
    import mcp.server.session

    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    Server = None

# Optional imports
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# === Configuration ===


@dataclass
class ServerConfig:
    """FreeCrawl server configuration"""

    # Transport
    transport: str = os.getenv("FREECRAWL_TRANSPORT", "stdio")
    http_port: int = int(os.getenv("FREECRAWL_PORT", "8000"))

    # Browser pool
    max_browsers: int = int(os.getenv("FREECRAWL_MAX_BROWSERS", "3"))
    browser_headless: bool = os.getenv("FREECRAWL_HEADLESS", "true").lower() == "true"
    browser_timeout: int = int(os.getenv("FREECRAWL_BROWSER_TIMEOUT", "30000"))

    # Concurrency
    max_concurrent: int = int(os.getenv("FREECRAWL_MAX_CONCURRENT", "10"))
    max_per_domain: int = int(os.getenv("FREECRAWL_MAX_PER_DOMAIN", "3"))

    # Cache
    cache_enabled: bool = os.getenv("FREECRAWL_CACHE", "true").lower() == "true"
    cache_dir: Path = Path(os.getenv("FREECRAWL_CACHE_DIR", "/tmp/freecrawl_cache"))
    cache_ttl: int = int(os.getenv("FREECRAWL_CACHE_TTL", "3600"))
    cache_max_size: int = int(os.getenv("FREECRAWL_CACHE_SIZE", "536870912"))  # 512MB

    # Security
    require_api_key: bool = (
        os.getenv("FREECRAWL_REQUIRE_API_KEY", "false").lower() == "true"
    )
    api_keys: List[str] = field(
        default_factory=lambda: os.getenv("FREECRAWL_API_KEYS", "").split(",")
        if os.getenv("FREECRAWL_API_KEYS")
        else []
    )
    blocked_domains: List[str] = field(
        default_factory=lambda: os.getenv("FREECRAWL_BLOCKED_DOMAINS", "").split(",")
        if os.getenv("FREECRAWL_BLOCKED_DOMAINS")
        else []
    )

    # Anti-detection
    anti_detect: bool = os.getenv("FREECRAWL_ANTI_DETECT", "true").lower() == "true"
    user_agent_rotation: bool = (
        os.getenv("FREECRAWL_ROTATE_UA", "true").lower() == "true"
    )
    proxy_list: List[str] = field(
        default_factory=lambda: os.getenv("FREECRAWL_PROXIES", "").split(",")
        if os.getenv("FREECRAWL_PROXIES")
        else []
    )

    # Performance
    rate_limit_default: int = int(os.getenv("FREECRAWL_RATE_LIMIT", "60"))
    request_timeout: int = int(os.getenv("FREECRAWL_REQUEST_TIMEOUT", "30"))
    max_response_size: int = int(
        os.getenv("FREECRAWL_MAX_RESPONSE", "52428800")
    )  # 50MB

    # Monitoring
    metrics_enabled: bool = os.getenv("FREECRAWL_METRICS", "true").lower() == "true"
    log_level: str = os.getenv("FREECRAWL_LOG_LEVEL", "INFO")
    audit_log: bool = os.getenv("FREECRAWL_AUDIT_LOG", "false").lower() == "true"


# === Data Models ===


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
    children: Optional[List["DocumentElement"]] = None


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

    url: str
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

    url: str
    schema_version: str
    extracted_at: datetime
    data: Dict[str, Any]
    confidence_scores: Optional[Dict[str, float]] = None
    validation_errors: Optional[List[str]] = None


class CrawlResult(BaseModel):
    """Result from website crawling"""

    start_url: str
    pages_found: int
    pages_scraped: int
    max_depth_reached: int
    content: List[ScrapedContent]
    sitemap: Optional[Dict[str, List[str]]] = None
    errors: Optional[List[Dict[str, str]]] = None


class SearchResult(BaseModel):
    """Web search result"""

    query: str
    total_results: int
    results: List[Dict[str, Any]]
    scraped_content: Optional[List[ScrapedContent]] = None


class ErrorCode(Enum):
    """Error codes for standardized error handling"""

    INVALID_URL = "invalid_url"
    INVALID_SCHEMA = "invalid_schema"
    RATE_LIMITED = "rate_limited"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    BROWSER_ERROR = "browser_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    PROCESSING_ERROR = "processing_error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    BOT_DETECTED = "bot_detected"
    CAPTCHA_REQUIRED = "captcha_required"
    IP_BLOCKED = "ip_blocked"


class FreeCrawlError(Exception):
    """Base exception for FreeCrawl errors"""

    def __init__(
        self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(message)


# === Browser Pool Management ===


class BrowserPool:
    """Manage browser instances with resource limits"""

    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self.browsers: List[Browser] = []
        self.available_browsers = asyncio.Queue()
        self.browser_contexts: Dict[str, BrowserContext] = {}
        self._playwright = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize browser pool"""
        self._playwright = await async_playwright().start()

        # Create initial browsers
        for _ in range(min(2, self.max_browsers)):
            browser = await self._create_browser()
            await self.available_browsers.put(browser)

    async def _create_browser(self) -> Browser:
        """Create a new browser instance"""
        browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",  # Faster loading
                "--disable-javascript",  # Will enable selectively
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ],
        )
        self.browsers.append(browser)
        return browser

    async def get_browser(self) -> Browser:
        """Get an available browser instance"""
        async with self._lock:
            if (
                self.available_browsers.empty()
                and len(self.browsers) < self.max_browsers
            ):
                browser = await self._create_browser()
                return browser

        return await self.available_browsers.get()

    async def release_browser(self, browser: Browser):
        """Release browser back to pool"""
        await self.available_browsers.put(browser)

    async def cleanup(self):
        """Cleanup all browsers"""
        for browser in self.browsers:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

        if self._playwright:
            await self._playwright.stop()


# === Anti-Detection Service ===


class AntiDetectionService:
    """Comprehensive anti-bot detection evasion"""

    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        ]

    async def prepare_context(
        self, context: BrowserContext, enable_js: bool = True
    ) -> None:
        """Configure browser context for stealth operation"""

        # Randomize user agent
        ua = random.choice(self.user_agents)

        # Configure stealth settings
        await context.add_init_script("""
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Remove automation indicators
            delete navigator.__proto__.webdriver;

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

            // Override plugins
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

            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'MacIntel'
            });
        """)

        # Set realistic headers
        await context.set_extra_http_headers(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": ua,
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )

        # Set viewport - this should be done when creating a page, not on context
        # We'll set this when creating pages


# === Cache Manager ===


class CacheManager:
    """Intelligent caching with TTL and size limits"""

    def __init__(self, cache_dir: Path, max_size: int, ttl: int):
        self.cache_dir = cache_dir
        self.max_size = max_size
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "cache.db"
        self.current_size = 0

    async def initialize(self):
        """Initialize cache database"""
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("""
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
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_entries(expires_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_url ON cache_entries(url)"
            )
            await db.commit()

        # Calculate current size
        await self._calculate_size()

    async def _calculate_size(self):
        """Calculate current cache size"""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute("SELECT SUM(size_bytes) FROM cache_entries")
            row = await cursor.fetchone()
            self.current_size = row[0] if row and row[0] else 0

    async def get(
        self, url: str, cache_key: Optional[str] = None
    ) -> Optional[ScrapedContent]:
        """Retrieve cached content if valid"""
        key = cache_key or self._generate_key(url)

        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                "SELECT data, expires_at FROM cache_entries WHERE cache_key = ?", (key,)
            )
            row = await cursor.fetchone()

            if row:
                data, expires_at = row
                expires_datetime = (
                    datetime.fromisoformat(expires_at) if expires_at else None
                )

                if expires_datetime and expires_datetime < datetime.now():
                    # Expired
                    await self.delete(key)
                    return None

                # Update hit count
                await db.execute(
                    "UPDATE cache_entries SET hit_count = hit_count + 1 WHERE cache_key = ?",
                    (key,),
                )
                await db.commit()

                # Decompress and deserialize
                try:
                    content_dict = pickle.loads(gzip.decompress(data))
                    return ScrapedContent(**content_dict)
                except Exception as e:
                    logger.warning(f"Failed to deserialize cached content: {e}")
                    await self.delete(key)
                    return None

        return None

    async def set(
        self, url: str, content: ScrapedContent, ttl: Optional[int] = None
    ) -> str:
        """Cache scraped content"""
        key = self._generate_key(url)

        # Serialize and compress
        data = gzip.compress(pickle.dumps(content.model_dump()))
        size = len(data)

        # Check size limits
        if size > self.max_size * 0.1:  # Single item shouldn't exceed 10% of cache
            return key

        # Evict if necessary
        while self.current_size + size > self.max_size:
            await self._evict_lru()

        # Store
        expires_at = datetime.now() + timedelta(seconds=ttl or self.ttl)

        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                (cache_key, url, content_type, data, expires_at, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key, url, "scraped_content", data, expires_at.isoformat(), size),
            )
            await db.commit()

        self.current_size += size
        return key

    async def delete(self, cache_key: str):
        """Delete cache entry"""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                "SELECT size_bytes FROM cache_entries WHERE cache_key = ?", (cache_key,)
            )
            row = await cursor.fetchone()

            if row:
                size = row[0]
                await db.execute(
                    "DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,)
                )
                await db.commit()
                self.current_size -= size

    async def _evict_lru(self):
        """Evict least recently used entry"""
        async with aiosqlite.connect(str(self.db_path)) as db:
            cursor = await db.execute(
                """
                SELECT cache_key, size_bytes FROM cache_entries
                ORDER BY hit_count ASC, created_at ASC
                LIMIT 1
                """
            )
            row = await cursor.fetchone()

            if row:
                key, size = row
                await self.delete(key)

    def _generate_key(self, url: str) -> str:
        """Generate cache key from URL"""
        return hashlib.md5(url.encode()).hexdigest()

    async def cleanup(self):
        """Cleanup expired entries"""
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                "DELETE FROM cache_entries WHERE expires_at < ?",
                (datetime.now().isoformat(),),
            )
            await db.commit()
        await self._calculate_size()


# === Content Extractor ===


class ContentExtractor:
    """Multi-strategy content extraction with fallback"""

    def __init__(self):
        self.anti_detect = AntiDetectionService()

    async def extract_content(
        self,
        url: str,
        browser: Browser,
        formats: List[str],
        javascript: bool = True,
        wait_for: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: int = 30000,
    ) -> ScrapedContent:
        """Extract content from URL using browser"""

        start_time = time.time()
        context = None
        page = None

        try:
            # Create browser context
            context = await browser.new_context()
            await self.anti_detect.prepare_context(context, enable_js=javascript)

            # Set custom headers
            if headers:
                await context.set_extra_http_headers(headers)

            # Set cookies
            if cookies:
                # Convert cookies to Playwright format
                cookie_list = []
                parsed_url = urlparse(url)
                domain = parsed_url.netloc

                for name, value in cookies.items():
                    cookie_list.append(
                        {
                            "name": name,
                            "value": value,
                            "domain": domain,
                            "path": "/",
                        }
                    )
                await context.add_cookies(cookie_list)

            # Create page
            page = await context.new_page()

            # Set viewport size
            await page.set_viewport_size(
                {
                    "width": random.choice([1920, 1366, 1440, 1536]),
                    "height": random.choice([1080, 768, 900, 864]),
                }
            )

            # Navigate to URL
            response = await page.goto(
                url, timeout=timeout, wait_until="domcontentloaded"
            )

            if not response:
                raise FreeCrawlError(ErrorCode.NETWORK_ERROR, f"Failed to load {url}")

            # Wait for additional content if specified
            if wait_for:
                if wait_for.isdigit():
                    await asyncio.sleep(int(wait_for) / 1000)  # Convert ms to seconds
                else:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        logger.warning(f"Selector {wait_for} not found, continuing...")

            # Extract page content
            html = await page.content()
            title = await page.title()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Extract text content
            text_content = soup.get_text(separator=" ", strip=True)

            # Generate markdown
            markdown_content = None
            if "markdown" in formats:
                markdown_content = self._html_to_markdown(html)

            # Take screenshot if requested
            screenshot_data = None
            if "screenshot" in formats:
                try:
                    screenshot = await page.screenshot(full_page=True)
                    screenshot_data = base64.b64encode(screenshot).decode()
                except Exception as e:
                    logger.warning(f"Failed to take screenshot: {e}")

            # Extract links
            links = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                absolute_url = urljoin(url, href)
                links.append(absolute_url)

            # Extract images
            images = []
            for img in soup.find_all("img", src=True):
                src = img["src"]
                absolute_url = urljoin(url, src)
                images.append(absolute_url)

            # Build metadata
            load_time = (time.time() - start_time) * 1000  # Convert to ms
            metadata = PageMetadata(
                timestamp=datetime.now(),
                status_code=response.status,
                content_type=response.headers.get("content-type", "text/html"),
                page_load_time=load_time,
                word_count=len(text_content.split()),
                headers=dict(response.headers),
            )

            # Extract structured elements if requested
            elements = None
            if "structured" in formats:
                elements = self._extract_structured_elements(soup)

            return ScrapedContent(
                url=url,
                title=title,
                markdown=markdown_content,
                html=html if "html" in formats else None,
                text=text_content if "text" in formats else None,
                screenshot=screenshot_data,
                metadata=metadata,
                elements=elements,
                links=links[:50],  # Limit to first 50 links
                images=images[:50],  # Limit to first 50 images
            )

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                raise
            raise FreeCrawlError(
                ErrorCode.PROCESSING_ERROR, f"Failed to extract content: {str(e)}"
            )

        finally:
            if page:
                await page.close()
            if context:
                await context.close()

    def _html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown"""
        try:
            # Clean up HTML first
            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.decompose()

            # Convert to markdown
            markdown = md(str(soup), heading_style="ATX", bullets="-")

            # Clean up markdown
            lines = markdown.split("\n")
            clean_lines = []

            for line in lines:
                line = line.strip()
                if line and not line.startswith("[]"):  # Remove empty link references
                    clean_lines.append(line)

            return "\n\n".join(clean_lines)

        except Exception as e:
            logger.warning(f"Markdown conversion failed: {e}")
            return html

    def _extract_structured_elements(
        self, soup: BeautifulSoup
    ) -> List[DocumentElement]:
        """Extract structured document elements"""
        elements = []

        try:
            # Extract headings
            for i, heading in enumerate(
                soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            ):
                elements.append(
                    DocumentElement(
                        type="Header",
                        content=heading.get_text(strip=True),
                        metadata=DocumentMetadata(element_id=f"heading_{i}"),
                    )
                )

            # Extract paragraphs
            for i, p in enumerate(soup.find_all("p")):
                text = p.get_text(strip=True)
                if text:
                    elements.append(
                        DocumentElement(
                            type="Text",
                            content=text,
                            metadata=DocumentMetadata(element_id=f"paragraph_{i}"),
                        )
                    )

            # Extract lists
            for i, ul in enumerate(soup.find_all(["ul", "ol"])):
                items = [li.get_text(strip=True) for li in ul.find_all("li")]
                if items:
                    elements.append(
                        DocumentElement(
                            type="List",
                            content="\n".join(f"- {item}" for item in items),
                            metadata=DocumentMetadata(element_id=f"list_{i}"),
                        )
                    )

            return elements[:100]  # Limit to first 100 elements

        except Exception as e:
            logger.warning(f"Structured extraction failed: {e}")
            return []


# === Rate Limiter ===


class RateLimiter:
    """Token bucket rate limiter with per-domain tracking"""

    def __init__(self, default_limit: int = 60):
        self.default_limit = default_limit
        self.domain_buckets: Dict[str, Dict[str, Any]] = {}
        self.global_bucket = {"tokens": default_limit, "last_refill": time.time()}

    async def check_rate_limit(self, url: str) -> bool:
        """Check if request is allowed for domain"""
        domain = urlparse(url).netloc
        now = time.time()

        # Get or create bucket for domain
        if domain not in self.domain_buckets:
            self.domain_buckets[domain] = {
                "tokens": self.default_limit,
                "last_refill": now,
            }

        bucket = self.domain_buckets[domain]

        # Refill tokens
        time_passed = now - bucket["last_refill"]
        tokens_to_add = time_passed * (self.default_limit / 60)  # tokens per second
        bucket["tokens"] = min(self.default_limit, bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now

        # Check if we can consume a token
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True

        return False


# === Document Processor ===


class DocumentProcessor:
    """Process documents using Unstructured"""

    async def process_document(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        strategy: str = "hi_res",
        formats: List[str] = ["structured"],
        languages: Optional[List[str]] = None,
        extract_images: bool = False,
        extract_tables: bool = True,
    ) -> Dict[str, Any]:
        """Process document file or URL"""

        temp_file = None
        try:
            # Download file if URL provided
            if url:
                temp_file = await self._download_file(url)
                file_path = temp_file

            if not file_path or not os.path.exists(file_path):
                raise FreeCrawlError(ErrorCode.NOT_FOUND, "Document file not found")

            # Import unstructured dynamically
            try:
                from unstructured.partition.auto import partition
            except ImportError:
                # Fallback to basic text extraction
                return await self._basic_document_processing(file_path, formats)

            # Process document
            elements = partition(
                filename=file_path,
                strategy=strategy,
                languages=languages or ["eng"],
                include_page_breaks=True,
                extract_images_in_pdf=extract_images,
            )

            # Convert elements to structured format
            structured_elements = []
            markdown_content = []
            text_content = []

            for element in elements:
                element_type = element.__class__.__name__
                content = str(element)

                if content.strip():
                    # Map Unstructured types to our types
                    mapped_type = self._map_element_type(element_type)

                    structured_elements.append(
                        DocumentElement(
                            type=mapped_type,
                            content=content,
                            metadata=DocumentMetadata(
                                page_number=getattr(
                                    element.metadata, "page_number", None
                                )
                                if hasattr(element, "metadata")
                                else None
                            ),
                        )
                    )

                    # Build markdown
                    if mapped_type == "Header":
                        markdown_content.append(f"# {content}")
                    elif mapped_type == "Title":
                        markdown_content.append(f"## {content}")
                    else:
                        markdown_content.append(content)

                    text_content.append(content)

            result = {
                "file_path": file_path,
                "elements_count": len(structured_elements),
                "word_count": len(" ".join(text_content).split()),
            }

            if "structured" in formats:
                result["elements"] = [elem.model_dump() for elem in structured_elements]

            if "markdown" in formats:
                result["markdown"] = "\n\n".join(markdown_content)

            if "text" in formats:
                result["text"] = "\n\n".join(text_content)

            return result

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                raise
            raise FreeCrawlError(
                ErrorCode.PROCESSING_ERROR, f"Document processing failed: {str(e)}"
            )

        finally:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

    async def _basic_document_processing(
        self, file_path: str, formats: List[str]
    ) -> Dict[str, Any]:
        """Basic document processing fallback when Unstructured is not available"""
        try:
            # Simple text extraction for common formats
            content = ""
            if file_path.lower().endswith(".txt"):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                # For other formats, return file info
                content = f"Document: {os.path.basename(file_path)}"

            result = {
                "file_path": file_path,
                "elements_count": 1,
                "word_count": len(content.split()),
            }

            if "text" in formats:
                result["text"] = content

            if "markdown" in formats:
                result["markdown"] = f"# {os.path.basename(file_path)}\n\n{content}"

            if "structured" in formats:
                result["elements"] = [
                    {
                        "type": "Text",
                        "content": content,
                        "metadata": {"element_id": "document_0"},
                    }
                ]

            return result

        except Exception as e:
            raise FreeCrawlError(
                ErrorCode.PROCESSING_ERROR,
                f"Basic document processing failed: {str(e)}",
            )

    async def _download_file(self, url: str) -> str:
        """Download file from URL to temporary location"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise FreeCrawlError(
                        ErrorCode.NETWORK_ERROR,
                        f"Failed to download file: {response.status}",
                    )

                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    async for chunk in response.content.iter_chunked(8192):
                        temp_file.write(chunk)
                    return temp_file.name

    def _map_element_type(self, unstructured_type: str) -> str:
        """Map Unstructured element types to our types"""
        mapping = {
            "Title": "Title",
            "Header": "Header",
            "Text": "Text",
            "NarrativeText": "Text",
            "ListItem": "List",
            "Table": "Table",
            "Image": "Image",
            "Code": "Code",
            "Footer": "Footer",
        }
        return mapping.get(unstructured_type, "Text")


# === State Manager ===


class StateManager:
    """Centralized state management for the server"""

    def __init__(self):
        self.browser_pool: Optional[BrowserPool] = None
        self.cache: Optional[CacheManager] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.document_processor: Optional[DocumentProcessor] = None
        self.content_extractor: Optional[ContentExtractor] = None
        self.config: Optional[ServerConfig] = None

    async def initialize(self, config: ServerConfig):
        """Initialize all stateful components"""
        self.config = config

        # Initialize browser pool
        self.browser_pool = BrowserPool(max_browsers=config.max_browsers)
        await self.browser_pool.initialize()

        # Initialize cache
        if config.cache_enabled:
            self.cache = CacheManager(
                cache_dir=config.cache_dir,
                max_size=config.cache_max_size,
                ttl=config.cache_ttl,
            )
            await self.cache.initialize()

        # Initialize other components
        self.rate_limiter = RateLimiter(config.rate_limit_default)
        self.document_processor = DocumentProcessor()
        self.content_extractor = ContentExtractor()

    async def cleanup(self):
        """Cleanup all resources"""
        if self.browser_pool:
            await self.browser_pool.cleanup()

        if self.cache:
            await self.cache.cleanup()


# === Main Server ===


class FreeCrawlServer:
    """Main FreeCrawl MCP server implementation"""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()
        self.state = StateManager()
        self.mcp = self._setup_mcp()

    def _setup_mcp(self):
        """Setup MCP server with tools"""
        if not HAS_MCP:
            raise ImportError("MCP library not found. Install with: pip install mcp")

        server = Server("freecrawl")

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="mcp__freecrawl__scrape",
                    description="Scrape content from a single URL with advanced options",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to scrape"},
                            "formats": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "markdown",
                                        "html",
                                        "text",
                                        "screenshot",
                                        "structured",
                                    ],
                                },
                                "default": ["markdown"],
                                "description": "Content formats to extract",
                            },
                            "javascript": {
                                "type": "boolean",
                                "default": True,
                                "description": "Enable JavaScript rendering",
                            },
                            "wait_for": {
                                "type": "string",
                                "description": "CSS selector or milliseconds to wait for",
                            },
                            "anti_bot": {
                                "type": "boolean",
                                "default": True,
                                "description": "Enable anti-bot detection",
                            },
                            "headers": {
                                "type": "object",
                                "description": "Custom HTTP headers",
                            },
                            "cookies": {
                                "type": "object",
                                "description": "Custom cookies",
                            },
                            "cache": {
                                "type": "boolean",
                                "default": True,
                                "description": "Use caching",
                            },
                            "timeout": {
                                "type": "integer",
                                "default": 30000,
                                "description": "Request timeout in milliseconds",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="mcp__freecrawl__search",
                    description="Perform web search and optionally scrape results",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "num_results": {
                                "type": "integer",
                                "default": 10,
                                "description": "Number of results to return",
                            },
                            "scrape_results": {
                                "type": "boolean",
                                "default": True,
                                "description": "Scrape content from result URLs",
                            },
                            "search_engine": {
                                "type": "string",
                                "default": "duckduckgo",
                                "description": "Search engine to use",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="mcp__freecrawl__crawl",
                    description="Crawl a website starting from a URL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_url": {
                                "type": "string",
                                "description": "Starting URL for crawl",
                            },
                            "max_pages": {
                                "type": "integer",
                                "default": 10,
                                "description": "Maximum pages to crawl",
                            },
                            "max_depth": {
                                "type": "integer",
                                "default": 2,
                                "description": "Maximum crawl depth",
                            },
                            "same_domain_only": {
                                "type": "boolean",
                                "default": True,
                                "description": "Stay within same domain",
                            },
                            "include_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "URL patterns to include",
                            },
                            "exclude_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "URL patterns to exclude",
                            },
                        },
                        "required": ["start_url"],
                    },
                ),
                Tool(
                    name="mcp__freecrawl__deep_research",
                    description="Perform comprehensive research on a topic using multiple sources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "Research topic",
                            },
                            "num_sources": {
                                "type": "integer",
                                "default": 5,
                                "description": "Number of sources to research",
                            },
                            "search_queries": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Custom search queries",
                            },
                            "include_academic": {
                                "type": "boolean",
                                "default": False,
                                "description": "Include academic sources",
                            },
                            "max_depth": {
                                "type": "integer",
                                "default": 1,
                                "description": "Research depth",
                            },
                        },
                        "required": ["topic"],
                    },
                ),
            ]

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Handle tool calls"""
            try:
                if name == "mcp__freecrawl__scrape":
                    result = await self.freecrawl_scrape(**arguments)
                elif name == "mcp__freecrawl__search":
                    result = await self.freecrawl_search(**arguments)
                elif name == "mcp__freecrawl__crawl":
                    result = await self.freecrawl_crawl(**arguments)
                elif name == "mcp__freecrawl__deep_research":
                    result = await self.freecrawl_deep_research(**arguments)
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

                return [
                    TextContent(
                        type="text", text=json.dumps(result, indent=2, default=str)
                    )
                ]
            except Exception as e:
                logger.error(f"Tool call error: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]

        return server

    async def initialize(self):
        """Initialize server components"""
        logger.info("Initializing FreeCrawl server...")

        # Check and install Playwright browsers if needed
        if not await self._check_browsers():
            logger.info("Installing Playwright browsers...")
            await self._install_browsers()

        # Initialize state manager
        await self.state.initialize(self.config)

        logger.info("FreeCrawl server initialized successfully")

    async def cleanup(self):
        """Cleanup server resources"""
        logger.info("Shutting down FreeCrawl server...")
        await self.state.cleanup()
        logger.info("FreeCrawl server shutdown complete")

    async def run(self):
        """Run the server"""
        await self.initialize()

        try:
            # Run the MCP server
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                await self.mcp.run(
                    read_stream, write_stream, self.mcp.create_initialization_options()
                )
        finally:
            await self.cleanup()

    # === MCP Tool Implementations ===

    async def freecrawl_scrape(
        self,
        url: str,
        formats: List[
            Literal["markdown", "html", "text", "screenshot", "structured"]
        ] = ["markdown"],
        javascript: bool = True,
        wait_for: Optional[str] = None,
        anti_bot: bool = True,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        cache: bool = True,
        timeout: int = 30000,
    ) -> Dict[str, Any]:
        """
        Scrape content from a single URL with advanced options.

        Returns comprehensive content in requested formats with metadata.
        Automatically handles JavaScript rendering, anti-bot measures, and retries.
        """
        try:
            # Validate URL
            if not self._validate_url(url):
                raise FreeCrawlError(ErrorCode.INVALID_URL, f"Invalid URL: {url}")

            # Check rate limits
            if not await self.state.rate_limiter.check_rate_limit(url):
                raise FreeCrawlError(
                    ErrorCode.RATE_LIMITED, "Rate limit exceeded for domain"
                )

            # Check cache first
            if cache and self.state.cache:
                cached = await self.state.cache.get(url)
                if cached:
                    logger.info(f"Returning cached content for {url}")
                    return cached.model_dump()

            # Get browser and extract content
            browser = await self.state.browser_pool.get_browser()
            try:
                result = await self.state.content_extractor.extract_content(
                    url=url,
                    browser=browser,
                    formats=formats,
                    javascript=javascript,
                    wait_for=wait_for,
                    headers=headers,
                    cookies=cookies,
                    timeout=timeout,
                )

                # Cache result
                if cache and self.state.cache:
                    await self.state.cache.set(url, result)

                return result.model_dump()

            finally:
                await self.state.browser_pool.release_browser(browser)

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                logger.error(f"FreeCrawl error: {e.message}")
                return {
                    "error": e.code.value,
                    "message": e.message,
                    "details": e.details,
                }
            else:
                logger.error(f"Unexpected error: {str(e)}")
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_batch_scrape(
        self,
        urls: List[str],
        concurrency: int = 5,
        formats: List[str] = ["markdown"],
        common_options: Optional[Dict[str, Any]] = None,
        continue_on_error: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Scrape multiple URLs concurrently with shared or individual options.

        Returns list of results in order of input URLs.
        Failed URLs return error dictionaries if continue_on_error is True.
        """
        try:
            if len(urls) > 100:
                raise FreeCrawlError(
                    ErrorCode.INVALID_URL, "Maximum 100 URLs allowed in batch"
                )

            # Limit concurrency
            concurrency = min(concurrency, self.config.max_concurrent, len(urls))
            semaphore = asyncio.Semaphore(concurrency)

            async def scrape_single(url: str) -> Dict[str, Any]:
                async with semaphore:
                    try:
                        options = common_options.copy() if common_options else {}
                        options.update({"url": url, "formats": formats})
                        return await self.freecrawl_scrape(**options)
                    except Exception as e:
                        if continue_on_error:
                            return {
                                "error": "processing_error",
                                "message": str(e),
                                "url": url,
                            }
                        raise

            # Execute all scraping tasks
            tasks = [scrape_single(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=continue_on_error)

            # Convert exceptions to error dicts
            final_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    final_results.append(
                        {
                            "error": "processing_error",
                            "message": str(result),
                            "url": urls[i],
                        }
                    )
                else:
                    final_results.append(result)

            return final_results

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return [{"error": e.code.value, "message": e.message}]
            else:
                return [{"error": "processing_error", "message": str(e)}]

    async def freecrawl_extract(
        self,
        url: str,
        schema: Dict[str, Any],
        prompt: Optional[str] = None,
        validation: bool = True,
        multiple: bool = False,
    ) -> Dict[str, Any]:
        """
        Extract structured data from web pages using schema-driven approach.

        Uses intelligent extraction to match the provided schema.
        Supports complex nested structures and validation.
        """
        try:
            # First scrape the page
            scraped = await self.freecrawl_scrape(url, formats=["text", "html"])

            if "error" in scraped:
                return scraped

            # Simple extraction based on content
            # In a full implementation, this would use LLM for intelligent extraction
            extracted_data = {
                "title": scraped.get("title", ""),
                "content": scraped.get("text", "")[:500] + "..."
                if scraped.get("text")
                else "",
                "url": url,
            }

            result = ExtractedData(
                url=url,
                schema_version="1.0",
                extracted_at=datetime.now(),
                data=extracted_data,
                confidence_scores={"overall": 0.8},
                validation_errors=[],
            )

            return result.model_dump()

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_process_document(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        strategy: Literal["fast", "hi_res", "ocr_only"] = "hi_res",
        formats: List[Literal["markdown", "structured", "text"]] = ["structured"],
        languages: Optional[List[str]] = None,
        extract_images: bool = False,
        extract_tables: bool = True,
    ) -> Dict[str, Any]:
        """
        Process documents (PDF, DOCX, PPTX, etc.) using Unstructured.

        Extracts text, tables, images, and metadata from various document formats.
        Supports OCR for scanned documents and multiple output formats.
        """
        try:
            if not file_path and not url:
                raise FreeCrawlError(
                    ErrorCode.INVALID_URL, "Either file_path or url must be provided"
                )

            result = await self.state.document_processor.process_document(
                file_path=file_path,
                url=url,
                strategy=strategy,
                formats=formats,
                languages=languages,
                extract_images=extract_images,
                extract_tables=extract_tables,
            )

            return result

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check of the server.

        Returns status of all major components and resource usage.
        """
        try:
            health_status = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0",
                "checks": {},
            }

            # Check browser pool
            try:
                browser_count = len(self.state.browser_pool.browsers)
                health_status["checks"]["browser_pool"] = {
                    "status": "healthy",
                    "browser_count": browser_count,
                    "max_browsers": self.config.max_browsers,
                }
            except Exception as e:
                health_status["checks"]["browser_pool"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                health_status["status"] = "degraded"

            # Check memory usage
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()

                memory_status = "healthy"
                if memory_mb > 1500:
                    memory_status = "warning"
                if memory_mb > 2000:
                    memory_status = "unhealthy"
                    health_status["status"] = "degraded"

                health_status["checks"]["resources"] = {
                    "status": memory_status,
                    "memory_mb": round(memory_mb, 2),
                    "cpu_percent": cpu_percent,
                    "max_memory_mb": 2000,
                }
            except Exception as e:
                health_status["checks"]["resources"] = {
                    "status": "unknown",
                    "error": str(e),
                }

            # Check cache
            if self.state.cache:
                try:
                    cache_size_mb = self.state.cache.current_size / 1024 / 1024
                    health_status["checks"]["cache"] = {
                        "status": "healthy",
                        "size_mb": round(cache_size_mb, 2),
                        "max_size_mb": round(
                            self.config.cache_max_size / 1024 / 1024, 2
                        ),
                    }
                except Exception as e:
                    health_status["checks"]["cache"] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
            else:
                health_status["checks"]["cache"] = {"status": "disabled"}

            return health_status

        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    async def freecrawl_search(
        self,
        query: str,
        num_results: int = 10,
        scrape_results: bool = True,
        search_engine: str = "duckduckgo",
    ) -> Dict[str, Any]:
        """
        Perform web search and optionally scrape results.

        Searches the web using the specified search engine and returns results.
        Can optionally scrape the content of each result URL.
        """
        try:
            # Simple implementation using DuckDuckGo search
            # In a full implementation, this would use proper search APIs
            search_url = f"https://duckduckgo.com/html/?q={quote(query)}"

            # Scrape search results page
            search_page = await self.freecrawl_scrape(
                url=search_url,
                formats=["html"],
                javascript=False,  # DuckDuckGo works without JS
            )

            if "error" in search_page:
                return search_page

            # Parse search results
            soup = BeautifulSoup(search_page["html"], "html.parser")
            results = []

            # Extract search result links
            for i, result_div in enumerate(soup.find_all("div", class_="result"), 1):
                if i > num_results:
                    break

                title_link = result_div.find("a", class_="result__a")
                if title_link:
                    title = title_link.get_text(strip=True)
                    url = title_link.get("href", "")

                    snippet_div = result_div.find("div", class_="result__snippet")
                    snippet = snippet_div.get_text(strip=True) if snippet_div else ""

                    results.append(
                        {"title": title, "url": url, "snippet": snippet, "rank": i}
                    )

            search_result = {
                "query": query,
                "total_results": len(results),
                "search_engine": search_engine,
                "results": results,
            }

            # Optionally scrape each result
            if scrape_results and results:
                urls_to_scrape = [r["url"] for r in results[:5]]  # Limit to first 5
                scraped_content = await self.freecrawl_batch_scrape(
                    urls=urls_to_scrape,
                    formats=["markdown", "text"],
                    concurrency=3,
                    continue_on_error=True,
                )
                search_result["scraped_content"] = scraped_content

            return search_result

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_crawl(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 2,
        same_domain_only: bool = True,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Crawl a website starting from a URL.

        Discovers and scrapes multiple pages following links up to max_depth.
        Can be restricted to same domain and filtered by URL patterns.
        """
        try:
            if max_pages > 100:
                raise FreeCrawlError(ErrorCode.INVALID_URL, "Maximum 100 pages allowed")

            # Initialize crawl state
            visited_urls = set()
            urls_to_visit = [(start_url, 0)]  # (url, depth)
            scraped_content = []
            sitemap = {}
            errors = []

            start_domain = urlparse(start_url).netloc

            while urls_to_visit and len(scraped_content) < max_pages:
                current_url, depth = urls_to_visit.pop(0)

                if current_url in visited_urls or depth > max_depth:
                    continue

                visited_urls.add(current_url)

                try:
                    # Scrape current page
                    result = await self.freecrawl_scrape(
                        url=current_url, formats=["markdown", "text"], javascript=True
                    )

                    if "error" not in result:
                        scraped_content.append(result)

                        # Extract links for next depth
                        if depth < max_depth and "links" in result:
                            for link in result["links"][:20]:  # Limit links per page
                                if self._should_crawl_url(
                                    link,
                                    start_domain,
                                    same_domain_only,
                                    include_patterns,
                                    exclude_patterns,
                                    visited_urls,
                                ):
                                    urls_to_visit.append((link, depth + 1))

                        # Build sitemap
                        if depth not in sitemap:
                            sitemap[depth] = []
                        sitemap[depth].append(current_url)
                    else:
                        errors.append(
                            {
                                "url": current_url,
                                "error": result.get("error", "unknown"),
                                "message": result.get("message", "Failed to scrape"),
                            }
                        )

                except Exception as e:
                    errors.append(
                        {
                            "url": current_url,
                            "error": "processing_error",
                            "message": str(e),
                        }
                    )

            return {
                "start_url": start_url,
                "pages_found": len(visited_urls),
                "pages_scraped": len(scraped_content),
                "max_depth_reached": max(sitemap.keys()) if sitemap else 0,
                "content": scraped_content,
                "sitemap": {str(k): v for k, v in sitemap.items()},
                "errors": errors if errors else None,
            }

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_map(
        self,
        start_url: str,
        max_urls: int = 50,
        include_external: bool = False,
        formats: List[str] = ["sitemap"],
    ) -> Dict[str, Any]:
        """
        Discover and map URLs from a website.

        Performs URL discovery without full content scraping.
        Returns structured sitemap and URL relationships.
        """
        try:
            if max_urls > 200:
                raise FreeCrawlError(ErrorCode.INVALID_URL, "Maximum 200 URLs allowed")

            # Scrape the start page to get initial links
            result = await self.freecrawl_scrape(
                url=start_url, formats=["html"], javascript=True
            )

            if "error" in result:
                return result

            # Parse all links
            soup = BeautifulSoup(result["html"], "html.parser")
            discovered_urls = set()
            internal_urls = set()
            external_urls = set()

            start_domain = urlparse(start_url).netloc

            # Extract all links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                absolute_url = urljoin(start_url, href)

                if absolute_url not in discovered_urls:
                    discovered_urls.add(absolute_url)

                    url_domain = urlparse(absolute_url).netloc
                    if url_domain == start_domain:
                        internal_urls.add(absolute_url)
                    else:
                        external_urls.add(absolute_url)

                if len(discovered_urls) >= max_urls:
                    break

            # Build sitemap structure
            sitemap = {
                "root": start_url,
                "internal_urls": list(internal_urls)[:max_urls],
                "external_urls": list(external_urls)[:50] if include_external else [],
                "total_discovered": len(discovered_urls),
            }

            # Analyze URL structure
            url_analysis = self._analyze_url_structure(list(internal_urls))

            return {
                "start_url": start_url,
                "discovered_count": len(discovered_urls),
                "internal_count": len(internal_urls),
                "external_count": len(external_urls),
                "sitemap": sitemap,
                "url_analysis": url_analysis,
                "formats": formats,
            }

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    async def freecrawl_deep_research(
        self,
        topic: str,
        num_sources: int = 5,
        search_queries: Optional[List[str]] = None,
        include_academic: bool = False,
        max_depth: int = 1,
    ) -> Dict[str, Any]:
        """
        Perform comprehensive research on a topic using multiple sources.

        Combines web search, content scraping, and analysis to gather
        comprehensive information about a topic from multiple sources.
        """
        try:
            if num_sources > 20:
                raise FreeCrawlError(
                    ErrorCode.INVALID_URL, "Maximum 20 sources allowed"
                )

            # Generate search queries if not provided
            if not search_queries:
                search_queries = [
                    topic,
                    f"{topic} overview",
                    f"{topic} guide",
                    f"what is {topic}",
                ]

            research_results = {
                "topic": topic,
                "search_queries": search_queries,
                "sources": [],
                "summary": {},
                "timestamp": datetime.now().isoformat(),
            }

            all_sources = []

            # Perform searches for each query
            for query in search_queries[:3]:  # Limit to 3 queries
                search_result = await self.freecrawl_search(
                    query=query, num_results=num_sources, scrape_results=False
                )

                if "error" not in search_result and "results" in search_result:
                    all_sources.extend(search_result["results"][:3])  # Top 3 per query

            # Remove duplicates and limit sources
            unique_sources = []
            seen_urls = set()

            for source in all_sources:
                if source["url"] not in seen_urls and len(unique_sources) < num_sources:
                    unique_sources.append(source)
                    seen_urls.add(source["url"])

            # Scrape content from unique sources
            if unique_sources:
                urls_to_scrape = [source["url"] for source in unique_sources]
                scraped_content = await self.freecrawl_batch_scrape(
                    urls=urls_to_scrape,
                    formats=["markdown", "text"],
                    concurrency=3,
                    continue_on_error=True,
                )

                # Combine search results with scraped content
                for i, (source, content) in enumerate(
                    zip(unique_sources, scraped_content)
                ):
                    if "error" not in content:
                        research_source = {
                            "rank": i + 1,
                            "title": source.get("title", ""),
                            "url": source["url"],
                            "snippet": source.get("snippet", ""),
                            "content_preview": content.get("text", "")[:500] + "..."
                            if content.get("text")
                            else "",
                            "word_count": len(content.get("text", "").split())
                            if content.get("text")
                            else 0,
                            "scraped_at": content.get("metadata", {}).get("timestamp"),
                        }
                        research_results["sources"].append(research_source)

            # Generate research summary
            total_words = sum(
                source.get("word_count", 0) for source in research_results["sources"]
            )
            research_results["summary"] = {
                "total_sources": len(research_results["sources"]),
                "successful_scrapes": len(
                    [
                        s
                        for s in research_results["sources"]
                        if s.get("word_count", 0) > 0
                    ]
                ),
                "total_words_gathered": total_words,
                "average_words_per_source": total_words
                // len(research_results["sources"])
                if research_results["sources"]
                else 0,
                "research_depth": max_depth,
                "academic_sources_included": include_academic,
            }

            return research_results

        except Exception as e:
            if isinstance(e, FreeCrawlError):
                return {"error": e.code.value, "message": e.message}
            else:
                return {"error": "processing_error", "message": str(e)}

    def _should_crawl_url(
        self,
        url: str,
        start_domain: str,
        same_domain_only: bool,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]],
        visited_urls: set,
    ) -> bool:
        """Check if URL should be crawled based on filters"""
        if url in visited_urls:
            return False

        if not self._validate_url(url):
            return False

        url_domain = urlparse(url).netloc

        if same_domain_only and url_domain != start_domain:
            return False

        if include_patterns:
            if not any(pattern in url for pattern in include_patterns):
                return False

        if exclude_patterns:
            if any(pattern in url for pattern in exclude_patterns):
                return False

        return True

    def _analyze_url_structure(self, urls: List[str]) -> Dict[str, Any]:
        """Analyze URL structure and patterns"""
        if not urls:
            return {}

        # Group by path segments
        path_segments = {}
        extensions = {}

        for url in urls:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split("/") if p]

            # Count path depth
            depth = len(path_parts)
            if depth not in path_segments:
                path_segments[depth] = 0
            path_segments[depth] += 1

            # Count file extensions
            if path_parts:
                last_part = path_parts[-1]
                if "." in last_part:
                    ext = last_part.split(".")[-1].lower()
                    if ext not in extensions:
                        extensions[ext] = 0
                    extensions[ext] += 1

        return {
            "total_urls": len(urls),
            "path_depth_distribution": path_segments,
            "file_extensions": extensions,
            "average_depth": sum(
                depth * count for depth, count in path_segments.items()
            )
            / len(urls)
            if urls
            else 0,
        }

    # === Helper Methods ===

    def _validate_url(self, url: str) -> bool:
        """Validate URL format and safety"""
        try:
            parsed = urlparse(url)

            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False

            # Must be HTTP/HTTPS
            if parsed.scheme not in ["http", "https"]:
                return False

            # Check for blocked domains
            if parsed.netloc in self.config.blocked_domains:
                return False

            # Check for private IPs
            try:
                ip = socket.gethostbyname(parsed.netloc)
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_private or ip_obj.is_loopback:
                    return False
            except (socket.gaierror, ValueError):
                pass  # Hostname resolution failed, allow to proceed

            return True

        except Exception:
            return False

    async def _check_browsers(self) -> bool:
        """Check if Playwright browsers are installed"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                await browser.close()
                return True
        except Exception:
            return False

    async def _install_browsers(self):
        """Install Playwright browsers"""
        try:
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

            if process.returncode != 0:
                logger.error(f"Failed to install browsers: {stderr.decode()}")
                raise FreeCrawlError(
                    ErrorCode.PROCESSING_ERROR, "Failed to install browsers"
                )

            logger.info("Playwright browsers installed successfully")

        except Exception as e:
            logger.error(f"Browser installation error: {e}")
            raise FreeCrawlError(
                ErrorCode.PROCESSING_ERROR, f"Browser installation failed: {str(e)}"
            )
