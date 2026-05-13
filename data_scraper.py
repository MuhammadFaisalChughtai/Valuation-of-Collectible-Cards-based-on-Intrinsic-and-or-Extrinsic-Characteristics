"""
Scrapes https://www.tcgplayer.com/ for Pokemon card data, including current market prices and recent sales history. Uses Playwright with Chromium techniques to bypass bot detection.
"""

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import random
import os
import json
import re
import mysql.connector
from mysql.connector import Error as MySQLError
from urllib.parse import quote
from datetime import datetime
import sys
from dotenv import load_dotenv

load_dotenv()

# configure the encoding for the console to handle any weird card names without crashing
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

INPUT_FILE  = './datasets/unique_pokemon_names.csv'
LOG_FILE    = './logs/scraper_log.txt'

# DB connection settings
# DB_HOST     = os.getenv('DB_HOST', 'localhost')
# DB_PORT     = int(os.getenv('DB_PORT', '3306'))
# DB_USER     = os.getenv('DB_USER', 'root')
# DB_PASSWORD = os.getenv('DB_PASSWORD', '') 
# DB_NAME     = os.getenv('DB_NAME', 'pokemon_tcg')

DB_HOST     = os.getenv('DB_HOST')
DB_PORT     = int(os.getenv('DB_PORT'))
DB_USER     = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD') 
DB_NAME     = os.getenv('DB_NAME')

# To avoid getting blocked, we restart the browser completely after a few cards
CONTEXT_RECYCLE_EVERY = 12

def log(msg: str, level: str = "INFO"):
    """Custom logger to print to console and append to our log file."""
    ts  = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}\n")
    except Exception:
        pass

def log_progress(cur: int, total: int, name: str):
    """Shows a clean progress bar in the terminal."""
    pct = cur / total * 100 if total else 0
    print(f"\r  [{pct:4.1f}%]  {cur}/{total}  {name[:38]:<38}", end="", flush=True)

#  modren web agent strings, viewports, and locales to randomize our fingerprint and avoid bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
]

VIEWPORTS = [{"width": 1920, "height": 1080}, {"width": 1440, "height": 900},
             {"width": 1366, "height": 768},  {"width": 1536, "height": 864}]
LOCALES   = ["en-US", "en-GB", "en-CA"]
TIMEZONES = ["America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London"]

def rdelay(lo=3.0, hi=9.0):
    """Random delay to mimic human reading/waiting times."""
    time.sleep(random.uniform(lo, hi))

def human_scroll(page):
    """Human scrolling to trigger lazy loading and bypass bot checks."""
    try:
        for _ in range(random.randint(2, 5)):
            page.evaluate(f"window.scrollBy(0, {random.randint(250, 700)})")
            time.sleep(random.uniform(0.3, 0.8))
        if random.random() < 0.3:
            page.evaluate("window.scrollBy(0, -150)")  # occasionally scroll back up
            time.sleep(random.uniform(0.2, 0.4))
    except Exception:
        pass

def create_context(p):
    """
    Sets up a Playwright Chromium context heavily modified to avoid bot detection.
    This tool hides signs of browser automation, mimics regular browser plugins, and masks WebGL hardware details to help avoid bot detection.
    """
    ua  = random.choice(USER_AGENTS)
    vp  = random.choice(VIEWPORTS)
    loc = random.choice(LOCALES)
    tz  = random.choice(TIMEZONES)
    log(f"New context UA={ua[-28:]} {vp['width']}x{vp['height']} {loc}", "BAN")

    browser = p.chromium.launch(
        headless=False,  # running headless usually gets flagged faster
        slow_mo=50,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-features=SegmentationPlatform,Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-component-update",
            "--disable-stack-profiler",
            "--disable-gpu",
            "--mute-audio",
        ]
    )
    ctx = browser.new_context(
        user_agent=ua, viewport=vp, locale=loc, timezone_id=tz,
        extra_http_headers={
            "Accept-Language": f"{loc},en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    
    # Overwrite JS variables that reveal we are using Playwright
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',    { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages',  { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Open Source Technology Center';
            if (parameter === 37446) return 'Mesa DRI Intel(R) HD Graphics 520 (Skylake GT2)';
            return getParameter.apply(this, arguments);
        };
    """)
    return browser, ctx

def get_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME,
        connection_timeout=10, autocommit=False
    )

def get_done(conn) -> tuple[set, set]:
    """The script retrieves URLs and names that have already been scraped to prevent repeating work if it restarts."""
    cur = conn.cursor()
    cur.execute("SELECT product_url FROM cards WHERE product_url IS NOT NULL AND scrape_error IS NULL")
    urls = {r[0] for r in cur.fetchall()}
    
    cur.execute("SELECT DISTINCT search_query FROM cards")
    names = {str(r[0]).strip().lower() for r in cur.fetchall() if r[0]}
    cur.close()
    return urls, names

INSERT_SQL = """
    INSERT INTO cards (
        tcg, name, set_name, search_query,
        full_name, product_url, market_price,
        history_total_sold, history_low_price, history_high_price,
        last_sold_date, last_sold_price,
        card_number, card_number_rarity, rarity, card_rarity, artist,
        card_type_hp_stage, hp, stage, card_type,
        attacks,
        weakness_resistance_retreat, weakness, resistance, retreat,
        sku_variant, sku_condition, scrape_error
    ) VALUES (
        %(tcg)s, %(name)s, %(set_name)s, %(search_query)s,
        %(full_name)s, %(product_url)s, %(market_price)s,
        %(history_total_sold)s, %(history_low_price)s, %(history_high_price)s,
        %(last_sold_date)s, %(last_sold_price)s,
        %(card_number)s, %(card_number_rarity)s, %(rarity)s, %(card_rarity)s, %(artist)s,
        %(card_type_hp_stage)s, %(hp)s, %(stage)s, %(card_type)s,
        %(attacks)s,
        %(weakness_resistance_retreat)s, %(weakness)s, %(resistance)s, %(retreat)s,
        %(sku_variant)s, %(sku_condition)s, %(scrape_error)s
    )
"""

def db_insert_card(conn, row: dict) -> int:
    cur = conn.cursor()
    cur.execute(INSERT_SQL, row)
    cid = cur.lastrowid
    conn.commit()
    cur.close()
    return cid

def db_insert_ph(conn, card_id: int, raw: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO price_history (card_id, raw_json) VALUES (%s, %s)", (card_id, raw))
    conn.commit()
    cur.close()

def db_insert_ls(conn, card_id: int, raw: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO latest_sales (card_id, raw_json) VALUES (%s, %s)", (card_id, raw))
    conn.commit()
    cur.close()

# Regex Parsing
# TCGPlayer pages are super messy, so we use regex on the raw text to extract stats
COMBINED_RE = re.compile(r'Card Type\s*/\s*HP\s*/\s*Stage[:\s]+(.+?)(?:\n|$)', re.IGNORECASE)
HP_BETWEEN_SLASHES_RE = re.compile(r'[^/]+/\s*(\d{1,4})\s*/')
HP_SUFFIX_RE = re.compile(r'\b(\d{1,4})\s*HP\b', re.IGNORECASE)
PRICE_RE = re.compile(r'Market Price\s*\n[\t ]*\n?[\t ]*(\$[\d,]+\.\d{2})', re.IGNORECASE)
PRICE_FALLBACK_RE = re.compile(r'Market Price[^\n]*\n[^\n]*\n[^\n]*(\$[\d,]+\.\d{2})', re.IGNORECASE)

def parse_hp(text: str):
    m = HP_BETWEEN_SLASHES_RE.search(text)
    if m:
        val = int(m.group(1))
        # Valid Pokemon HP range
        if 10 <= val <= 340:
            return val
            
    m2 = HP_SUFFIX_RE.search(text)
    if m2:
        val = int(m2.group(1))
        if 10 <= val <= 340:
            return val
    return None

def parse_market_price(body: str):
    m = PRICE_RE.search(body)
    if m: return m.group(1)
    
    m2 = PRICE_FALLBACK_RE.search(body)
    if m2: return m2.group(1)
    
    return None

def parse_card_number_rarity(raw: str) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(' / ', 1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return raw.strip(), None

def parse_weakness_resistance_retreat(raw: str) -> tuple[str | None, str | None, str | None]:
    if not raw:
        return None, None, None
    parts = [p.strip() for p in raw.split(' / ')]
    weakness   = parts[0] if len(parts) > 0 else None
    resistance = parts[1] if len(parts) > 1 else None
    retreat    = parts[2] if len(parts) > 2 else None
    return weakness, resistance, retreat

STAGES = ["VMAX", "VSTAR", "V-UNION", "GX", "EX", "TAG TEAM", "Stage 2", "Stage 1", "Restored", "Basic V", "Basic"]
TYPES = ["Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting", "Darkness", "Metal", "Dragon", "Fairy", "Colorless"]

def parse_stage(text: str):
    lower = text.lower()
    for s in STAGES:
        if s.lower() in lower:
            return s
    return None

def parse_card_type(text: str):
    found = [t for t in TYPES if re.search(rf'\b{t}\b', text, re.IGNORECASE)]
    return ", ".join(found) if found else None

def scrape_and_save(context, conn, card_name: str, done_urls: set) -> tuple[int, int]:
    """
    The main engine.
    1. Searches for the card name
    2. Collects all product links from the search results
    3. Visits each product link and captures pricing data and sales history from API network calls
    """
    page = context.new_page()
    saved = 0
    errors = 0
    
    # stashing intercepted JSON responses here 
    api_data = {"ph": [], "ls": []}

    def on_response(resp):
        """We intercept XHR requests to avoid parsing complex charts directly from the DOM."""
        try:
            if "tcgplayer.com" not in resp.url: return
            if resp.request.resource_type not in ("fetch", "xhr"): return
            
            if "price/history" in resp.url: # XHR Request
                try: api_data["ph"].append(resp.json())
                except: pass
            elif "latestsales" in resp.url: # XHR Request
                try: api_data["ls"].append(resp.json())
                except: pass
        except Exception: pass

    page.on("response", on_response)

    try:
        links = []
        # We only collect data from the first 10 pages on TCGPlayer
        for page_num in range(1, 11):
            url = f"https://www.tcgplayer.com/search/pokemon/product?productLineName=pokemon&q={quote(card_name)}&view=grid&page={page_num}"
            p_links = []
            
            for attempt in range(2):
                try:
                    log(f"Search -> {card_name} (Page {page_num})", "SEARCH")
                    page.goto(url, wait_until="networkidle", timeout=60_000)
                    time.sleep(random.uniform(4.0, 6.0))
                    
                    try:
                        page.wait_for_selector(".search-results, .product-card", timeout=10_000)
                    except: pass

                    # Scroll to load everything on the grid
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                    time.sleep(1.0)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

                    # Grab all the product URLs from the grid
                    selectors = [".search-result__title a", ".product-card__title a", ".product-card__image a"]
                    for sel in selectors:
                        try:
                            for el in page.locator(sel).all():
                                href = el.get_attribute("href", timeout=1_000)
                                if href and "/product/" in href:
                                    base = ("https://www.tcgplayer.com" + href if href.startswith("/") else href).split("?")[0]
                                    if base not in p_links: p_links.append(base)
                        except: continue
                    
                    # Fallback in case they changed classes
                    if not p_links:
                        try:
                            for el in page.locator("a").all():
                                href = el.get_attribute("href", timeout=500)
                                if href and "/product/" in href:
                                    base = ("https://www.tcgplayer.com" + href if href.startswith("/") else href).split("?")[0]
                                    if base not in p_links: p_links.append(base)
                        except: pass

                    if p_links: break
                    
                    if attempt == 0:
                        log(f"No links for '{card_name}' on Page {page_num} pass 1, retrying...", "WARN")
                        time.sleep(10)
                except PlaywrightTimeout:
                    if attempt == 1: log(f"Page {page_num} timeout", "WARN")
                    time.sleep(5)

            if not p_links:
                break # We've hit the last page
            
            new_found = False
            for l in p_links:
                if l not in links:
                    links.append(l)
                    new_found = True
            
            # If we didn't find any new links on this page, we can stop paginating further.
            if not new_found:
                break
            
            rdelay(1.5, 3.5)

        if not links:
            log(f"No product links for '{card_name}'", "WARN")
            _save_error(conn, card_name, None, "No results found")
            errors += 1
            return saved, errors

        log(f"{len(links)} listings found", "INFO")

        # We visit each product page to capture detail data and API calls
        for i, link in enumerate(links[:50]):
            if link in done_urls:
                log(f"Skip (URL in DB): ...{link[-30:]}", "SKIP")
                saved += 1
                continue

            log(f"[{i+1}/{min(len(links),50)}] {link.split('/')[-1]}", "INFO")
            api_data["ph"].clear()
            api_data["ls"].clear()

            loaded = False
            for attempt in range(3):
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=30_000)
                    loaded = True
                    break
                except PlaywrightTimeout:
                    wait = 5 * (attempt + 1)
                    log(f"Timeout attempt {attempt+1}, retry in {wait}s", "WARN")
                    time.sleep(wait)

            if not loaded:
                log(f"Skipping after 3 timeouts: {link}", "ERROR")
                _save_error(conn, card_name, link, "Product page timeout")
                errors += 1
                continue

            human_scroll(page)
            time.sleep(random.uniform(2.5, 4.5))

            row = _build_row(page, card_name, link, api_data)

            try:
                cid = db_insert_card(conn, row)
                log(f"[DONE] [{cid}] {row.get('full_name','?')} HP={row.get('hp','?')} Stage={row.get('stage','?')} Price={row.get('market_price','?')}", "OK")
                saved += 1

                # Save the raw intercepted JSON payloads if we found them
                ph_raw = row.pop("_ph_raw", None)
                ls_raw = row.pop("_ls_raw", None)
                
                if ph_raw: db_insert_ph(conn, cid, ph_raw)
                if ls_raw: db_insert_ls(conn, cid, ls_raw)

            except MySQLError as e:
                log(f"DB insert error: {e}", "ERROR")
                errors += 1

            rdelay(2.0, 5.5)

    except Exception as e:
        log(f"Critical error for '{card_name}': {e}", "ERROR")
        errors += 1
    finally:
        try: page.close()
        except Exception: pass

    return saved, errors

def _build_row(page, card_name: str, link: str, api_data: dict) -> dict:
    """Takes the raw page DOM and the intercepted API data, and formats it for our database schema."""
    row: dict = {
        "tcg": "pokemon",
        "name": card_name,
        "set_name": None,
        "search_query": card_name,
        "product_url": link,
        "full_name": None, "market_price": None,
        "history_total_sold": None, "history_low_price": None, "history_high_price": None,
        "last_sold_date": None, "last_sold_price": None,
        "card_number": None, "card_number_rarity": None, "rarity": None, "card_rarity": None, "artist": None,
        "card_type_hp_stage": None,
        "hp": None, "stage": None, "card_type": None,
        "attacks": None,
        "weakness_resistance_retreat": None, "weakness": None, "resistance": None, "retreat": None,
        "sku_variant": None, "sku_condition": None,
        "scrape_error": None,
        "_ph_raw": None, "_ls_raw": None,
    }

    try:
        h1_text = page.locator("h1").first.inner_text(timeout=5_000).strip()
        row["full_name"] = h1_text
        
        # Bot challenge detection: If we notice specific phrases in the main title, it probably means we've been flagged and should stop scraping this page.
        challenge_indicators = ["Hmm, that’s not right.", "Verify you are human", "Please prove you are human"]
        if any(ind in h1_text for ind in challenge_indicators):
            log(f"Bot Challenge Detected: '{h1_text}'", "WARN")
            row["scrape_error"] = "Bot Challenge Detection"
            return row
            
    except Exception: pass

    try:
        body = page.locator("body").inner_text(timeout=10_000)
    except Exception:
        body = ""

    if "Verify you are human" in body:
        log("Bot Challenge Detected in body text", "WARN")
        row["scrape_error"] = "Bot Challenge Detection"
        return row

    if body and not row.get("market_price"):
        row["market_price"] = parse_market_price(body)

    if body:
        # Extract basic stats from the blob
        m = re.search(r"Card Number\s*/\s*Rarity[:\s]+(.*?)(?:\n|$)", body, re.IGNORECASE)
        if m:
            raw_nr = m.group(1).strip()
            row["card_number_rarity"] = raw_nr
            num, rar = parse_card_number_rarity(raw_nr)
            row["card_number"] = num
            row["rarity"] = rar
            row["card_rarity"] = rar

        m_art = re.search(r"Artist\s*[:\s]+(.*?)(?:\n|$)", body, re.IGNORECASE)
        if m_art:
            row["artist"] = m_art.group(1).strip()

        m2 = COMBINED_RE.search(body)
        if m2:
            combined = m2.group(1).strip()
            row["card_type_hp_stage"] = combined
            row["hp"]        = parse_hp(combined)
            row["stage"]     = parse_stage(combined)
            row["card_type"] = parse_card_type(combined)

        if row["hp"] is None:
            row["hp"] = parse_hp(body[:5000])
        if row["stage"] is None:
            row["stage"] = parse_stage(body[:5000])

        # Gather all attack strings
        atk_parts = []
        for n in range(1, 5):
            m_atk = re.search(rf"Attack\s*{n}[:\s]+(.*?)(?:\n|$)", body, re.IGNORECASE)
            if m_atk: atk_parts.append(m_atk.group(1).strip())
        if atk_parts:
            row["attacks"] = " | ".join(atk_parts)

        m_wr = re.search(r"Weakness\s*/\s*Resistance\s*/\s*Retreat Cost[:\s]+(.*?)(?:\n|$)", body, re.IGNORECASE)
        if m_wr:
            raw_wr = m_wr.group(1).strip()
            row["weakness_resistance_retreat"] = raw_wr
            row["weakness"], row["resistance"], row["retreat"] = parse_weakness_resistance_retreat(raw_wr)

    # Process intercepted API payloads
    if api_data["ph"]:
        try:
            res = api_data["ph"][0].get("result", [])
            if res:
                sku = res[0]
                row["sku_variant"]   = sku.get("variant")
                row["sku_condition"] = sku.get("condition")
                buckets = sku.get("buckets", [])
                row["_ph_raw"] = json.dumps(buckets)
                
                # Calculate aggregated sales stats
                sold = lo = hi = 0; lo = 999999
                for b in buckets:
                    sold += int(b.get("quantitySold", 0))
                    l = float(b.get("lowSalePrice", 0))
                    h = float(b.get("highSalePrice", 0))
                    if l > 0 and l < lo: lo = l
                    if h > 0 and h > hi: hi = h
                    
                row["history_total_sold"] = sold
                row["history_low_price"]  = lo if lo < 999999 else 0
                row["history_high_price"] = hi
        except Exception: pass

    if api_data["ls"]:
        try:
            s = api_data["ls"][0].get("data", [])
            row["_ls_raw"] = json.dumps(s)
            if s:
                row["last_sold_date"]  = s[0].get("orderDate")
                row["last_sold_price"] = s[0].get("purchasePrice")
        except Exception: pass

    return row

def _save_error(conn, card_name: str, link, err_msg: str):
    """Fallback save so we don't retry broken links or blocked pages infinitely."""
    try:
        row = {
            "tcg": "pokemon", "name": card_name, "set_name": None,
            "search_query": card_name, "full_name": None, "product_url": link,
            "market_price": None, "history_total_sold": None, "history_low_price": None,
            "history_high_price": None, "last_sold_date": None, "last_sold_price": None,
            "card_number": None, "card_number_rarity": None, "rarity": None, "card_rarity": None, "artist": None,
            "card_type_hp_stage": None,
            "hp": None, "stage": None, "card_type": None,
            "attacks": None,
            "weakness_resistance_retreat": None, "weakness": None, "resistance": None, "retreat": None,
            "sku_variant": None, "sku_condition": None, "scrape_error": err_msg,
        }
        db_insert_card(conn, row)
    except Exception as e:
        log(f"Could not save error row: {e}", "ERROR")

def main():
    if not os.path.exists(INPUT_FILE):
        log(f"'{INPUT_FILE}' not found!", "ERROR")
        return

    df = pd.read_csv(INPUT_FILE)
    if 'name' not in df.columns:
        log(f"'{INPUT_FILE}' must contain a 'name' column!", "ERROR")
        return

    log(f"Loaded {len(df):,} names from {INPUT_FILE}", "INFO")

    done_count = 0
    try:
        conn = get_db()
        log(f"MySQL {DB_HOST}:{DB_PORT}/{DB_NAME}", "DB")
        done_urls, done_names = get_done(conn)
        done_count = len(done_urls)
    except MySQLError as e:
        log(f"MySQL failed: {e}", "ERROR")
        return

    total = len(df)
    log(f"Resume: {done_count:,} listings & {len(done_names):,} names already in DB", "INFO")

    saved_total = 0; errors_total = 0

    with sync_playwright() as p:
        browser, ctx = create_context(p)
        ctx_count = 0

        try:
            for enum_idx, (_, row) in enumerate(df.iterrows()):
                name = str(row.get('name', '')).strip()
                if not name or name.lower() == 'nan':
                    continue

                if name.lower() in done_names:
                    log_progress(enum_idx + 1, total, f"Skip: {name}")
                    continue
                
                print()
                log_progress(enum_idx + 1, total, name)
                print()

                # Refresh the browser session periodically to clear cookies and reset fingerprints
                if ctx_count >= CONTEXT_RECYCLE_EVERY:
                    log(f"Recycling browser after {ctx_count} cards...", "BAN")
                    try: browser.close()
                    except Exception: pass
                    time.sleep(random.uniform(5, 12))
                    browser, ctx = create_context(p)
                    ctx_count = 0

                s, e = scrape_and_save(ctx, conn, name, done_urls)
                saved_total  += s
                errors_total += e
                ctx_count    += 1
                done_names.add(name.lower())

                rdelay(3.5, 9.0)

        except KeyboardInterrupt:
            log("Interrupted by user.", "WARN")
        finally:
            # Clean up processes
            try: browser.close()
            except Exception: pass
            
            try: conn.close()
            except Exception: pass

    print()
    log(f"Finished - {saved_total} saved | {errors_total} errors", "INFO")

if __name__ == "__main__":
    main()
