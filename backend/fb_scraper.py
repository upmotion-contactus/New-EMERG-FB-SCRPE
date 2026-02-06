"""Facebook Group Lead Scraper using Playwright - OPTIMIZED VERSION"""
import asyncio
import json
import os
import re
import csv
import secrets
import glob
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import logging
from concurrent.futures import ThreadPoolExecutor

from industry_config import matches_industry, detect_industry, is_qualified_prospect

logger = logging.getLogger(__name__)

# Configurable paths - use environment variables for production flexibility
COOKIES_FILE = os.environ.get('FB_COOKIES_FILE', '/app/backend/fb_cookies.json')
SCRAPE_DIR = os.environ.get('SCRAPE_DIR', '/app/scrape_files')
BROWSER_PATH = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/pw-browsers')

# Performance tuning settings
SCROLL_DELAY = float(os.environ.get('SCROLL_DELAY', '0.3'))  # Reduced from 0.8
PAGE_LOAD_TIMEOUT = int(os.environ.get('PAGE_LOAD_TIMEOUT', '15000'))  # Reduced from 30000
CONCURRENT_SCRAPES = int(os.environ.get('CONCURRENT_SCRAPES', '3'))  # Parallel profile scraping
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '5'))  # Profiles per batch


def find_chromium_executable() -> Optional[str]:
    """Dynamically find the Chromium browser executable path for different environments"""
    
    # Check for environment variable override first
    if os.environ.get('CHROMIUM_PATH'):
        custom_path = os.environ.get('CHROMIUM_PATH')
        if os.path.isfile(custom_path) and os.access(custom_path, os.X_OK):
            logger.info(f"Using CHROMIUM_PATH from env: {custom_path}")
            return custom_path
    
    # Get browser base path from env or use common locations
    browser_bases = [
        os.environ.get('PLAYWRIGHT_BROWSERS_PATH', ''),
        '/pw-browsers',
        '/ms-playwright',
        os.path.expanduser('~/.cache/ms-playwright'),
        '/root/.cache/ms-playwright',
    ]
    
    # Filter out empty paths
    browser_bases = [b for b in browser_bases if b]
    
    for browser_base in browser_bases:
        if not os.path.isdir(browser_base):
            continue
            
        # Pattern to find chromium directories
        chromium_patterns = [
            f"{browser_base}/chromium-*/chrome-linux/chrome",
            f"{browser_base}/chromium_headless_shell-*/headless_shell",
            f"{browser_base}/chromium/chrome-linux/chrome",
            f"{browser_base}/chromium-*/chrome",
        ]
        
        for pattern in chromium_patterns:
            matches = glob.glob(pattern)
            if matches:
                # Sort to get the latest version and return the first match
                matches.sort(reverse=True)
                executable = matches[0]
                if os.path.isfile(executable) and os.access(executable, os.X_OK):
                    logger.info(f"Found Chromium at: {executable}")
                    return executable
    
    # Fallback: let Playwright find it automatically (this is preferred for production)
    logger.info("No custom Chromium path found, will use Playwright's default browser discovery")
    return None


async def check_browser_availability() -> Dict[str, Any]:
    """Check if Playwright browser is available and can be launched"""
    from playwright.async_api import async_playwright
    
    chromium_path = find_chromium_executable()
    
    try:
        async with async_playwright() as p:
            launch_options = {
                'headless': True,
                'args': ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
            }
            
            if chromium_path:
                launch_options['executable_path'] = chromium_path
            
            browser = await p.chromium.launch(**launch_options)
            version = browser.version
            await browser.close()
            
            return {
                'available': True,
                'version': version,
                'path': chromium_path or 'Playwright default'
            }
    except Exception as e:
        error_msg = str(e)
        
        # Try without custom path if it failed
        if chromium_path:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
                    )
                    version = browser.version
                    await browser.close()
                    return {
                        'available': True,
                        'version': version,
                        'path': 'Playwright default (fallback)'
                    }
            except Exception as e2:
                error_msg = str(e2)
        
        return {
            'available': False,
            'error': error_msg,
            'path': chromium_path,
            'hint': 'Playwright browsers may not be installed. Run: playwright install chromium'
        }


def generate_slug_suffix() -> str:
    """Generate high-entropy random suffix (>=32 bits) for slugs"""
    return secrets.token_hex(8)  # 64 bits of entropy


def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text[:50] if text else 'unknown'


def load_cookies() -> List[Dict]:
    """Load Facebook cookies from file"""
    if not os.path.exists(COOKIES_FILE):
        return []
    try:
        with open(COOKIES_FILE, 'r') as f:
            cookies = json.load(f)
        return cookies if isinstance(cookies, list) else []
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")
        return []


def save_cookies(cookies: List[Dict]) -> bool:
    """Save Facebook cookies to file"""
    try:
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving cookies: {e}")
        return False


def delete_cookies() -> bool:
    """Delete saved cookies file"""
    try:
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
        return True
    except Exception as e:
        logger.error(f"Error deleting cookies: {e}")
        return False


def cookies_exist() -> bool:
    """Check if cookies file exists and has content"""
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE, 'r') as f:
            cookies = json.load(f)
        return isinstance(cookies, list) and len(cookies) > 0
    except:
        return False


def format_cookies_for_playwright(cookies: List[Dict]) -> List[Dict]:
    """Format cookies for Playwright compatibility"""
    formatted = []
    for cookie in cookies:
        c = {
            'name': cookie.get('name', ''),
            'value': cookie.get('value', ''),
            'domain': cookie.get('domain', '.facebook.com'),
            'path': cookie.get('path', '/')
        }
        
        # Handle sameSite
        same_site = cookie.get('sameSite', 'None')
        if same_site in ['Strict', 'Lax', 'None']:
            c['sameSite'] = same_site
        else:
            c['sameSite'] = 'None'
        
        # Handle secure
        c['secure'] = cookie.get('secure', True)
        
        # Handle httpOnly
        c['httpOnly'] = cookie.get('httpOnly', False)
        
        # Handle expiration
        if 'expirationDate' in cookie:
            c['expires'] = int(cookie['expirationDate'])
        elif 'expires' in cookie:
            c['expires'] = int(cookie['expires'])
        
        formatted.append(c)
    
    return formatted


async def take_debug_screenshot(page: Page, name: str):
    """Take a debug screenshot"""
    try:
        path = f"/tmp/fb_debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=path, full_page=False)
        logger.info(f"Debug screenshot saved: {path}")
    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")


async def is_login_page(page: Page) -> bool:
    """Check if current page is Facebook login page"""
    try:
        url = page.url
        # Direct URL checks
        if '/login' in url or 'login.php' in url or 'checkpoint' in url:
            return True
        
        title = await page.title()
        if title and ('log in' in title.lower() or 'login' in title.lower() or 'facebook' == title.lower().strip()):
            return True
        
        # Check for login form elements
        login_form = await page.query_selector('form[action*="login"]')
        if login_form:
            return True
        
        # Check for login button
        login_btn = await page.query_selector('#loginbutton, button[name="login"], input[value="Log In"]')
        if login_btn:
            return True
        
        # Check page content for login indicators
        content = await page.content()
        login_indicators = ['id="loginbutton"', 'name="login"', 'Create new account', 'Forgot password?']
        if any(indicator in content for indicator in login_indicators):
            return True
        
        return False
    except:
        return False


async def verify_facebook_session(page: Page) -> bool:
    """Verify that Facebook session is active by checking for user elements"""
    try:
        # Look for elements that only appear when logged in
        user_menu = await page.query_selector('[aria-label="Your profile"], [aria-label="Account"], [data-pagelet="ProfileTilesFeed"]')
        if user_menu:
            return True
        
        # Check for navigation elements
        nav = await page.query_selector('[role="navigation"]')
        if nav:
            nav_text = await nav.inner_text()
            if 'Home' in nav_text or 'Friends' in nav_text:
                return True
        
        return False
    except:
        return False


async def scrape_facebook_group(
    urls: List[str],
    industry: str,
    status_callback: Callable[[Dict], None],
    job_id: str
) -> Dict[str, Any]:
    """Main scraping function for Facebook groups - OPTIMIZED FOR LONG SCRAPES"""
    
    results = []
    all_matches = []
    total_scanned = 0
    group_names_scraped = []  # Track all group names for combined filename
    
    # Long scrape settings - EXTENDED FOR MULTI-HOUR SCRAPES
    MAX_SCRAPE_TIME = int(os.environ.get('MAX_SCRAPE_TIME', '14400'))  # 4 hours default
    HEARTBEAT_INTERVAL = 30
    start_time = datetime.now(timezone.utc)
    
    # Ensure scrape directory exists
    os.makedirs(SCRAPE_DIR, exist_ok=True)
    
    # Load cookies
    cookies = load_cookies()
    if not cookies:
        status_callback({
            'status': 'error',
            'message': 'No Facebook cookies configured. Please add cookies in settings.',
            'job_id': job_id
        })
        return {'success': False, 'error': 'No cookies configured'}
    
    formatted_cookies = format_cookies_for_playwright(cookies)
    
    # Find Chromium executable dynamically (works in sandbox and production)
    chromium_path = find_chromium_executable()
    
    async with async_playwright() as p:
        try:
            # OPTIMIZED: Performance-tuned browser launch options
            launch_options = {
                'headless': True,
                'args': [
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-gpu', 
                    '--disable-dev-shm-usage',
                    '--disable-software-rasterizer',
                    '--single-process',
                    '--disable-extensions',
                    '--disable-background-networking',
                    '--disable-sync',
                    '--disable-translate',
                    '--disable-features=TranslateUI',
                    '--metrics-recording-only',
                    '--mute-audio',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--ignore-certificate-errors',
                    '--ignore-ssl-errors',
                    '--ignore-certificate-errors-spki-list',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            }
            
            if chromium_path:
                launch_options['executable_path'] = chromium_path
                logger.info(f"Launching Chromium from custom path: {chromium_path}")
            else:
                logger.info("Launching Chromium using Playwright's default browser discovery")
            
            try:
                browser = await p.chromium.launch(**launch_options)
            except Exception as launch_error:
                if chromium_path:
                    logger.warning(f"Custom path failed ({launch_error}), trying Playwright default...")
                    del launch_options['executable_path']
                    browser = await p.chromium.launch(**launch_options)
                else:
                    raise launch_error
            
            # OPTIMIZED: Performance-tuned browser context
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                bypass_csp=True,
                ignore_https_errors=True,
                java_script_enabled=True
            )
            
            # Add cookies
            await context.add_cookies(formatted_cookies)
            
            page = await context.new_page()
            
            # SPEED OPTIMIZATION: Block unnecessary resources
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font", "stylesheet"]
                else route.continue_()
            )
            
            for url_idx, url in enumerate(urls):
                status_callback({
                    'status': 'running',
                    'message': f'Processing URL {url_idx + 1}/{len(urls)}: {url}',
                    'job_id': job_id,
                    'current_url': url,
                    'url_progress': f'{url_idx + 1}/{len(urls)}'
                })
                
                try:
                    # Navigate to group members page
                    members_url = url.rstrip('/') + '/members'
                    logger.info(f"Navigating to: {members_url}")
                    
                    await page.goto(members_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(3)
                    
                    # Check for login page
                    if await is_login_page(page):
                        await take_debug_screenshot(page, 'login_detected')
                        status_callback({
                            'status': 'error',
                            'message': 'Facebook login required. Please update your cookies.',
                            'job_id': job_id
                        })
                        await browser.close()
                        return {'success': False, 'error': 'Login required - cookies expired'}
                    
                    # Extract group name from page
                    group_name = 'unknown_group'
                    try:
                        title = await page.title()
                        if title and '|' in title:
                            group_name = title.split('|')[0].strip()
                        elif title:
                            group_name = title.strip()
                    except:
                        pass
                    
                    logger.info(f"Scraping group: {group_name}")
                    group_names_scraped.append(group_name)  # Track group name
                    
                    # Stage 1: Collect member links with infinite scroll
                    status_callback({
                        'status': 'running',
                        'message': f'Stage 1: Collecting member links from {group_name}...',
                        'job_id': job_id,
                        'stage': 'collecting'
                    })
                    
                    member_links = await stage1_collect_links(
                        page, industry, status_callback, job_id, 
                        collect_all=False, start_time=start_time
                    )
                    
                    total_scanned += len(member_links.get('all_scanned', []))
                    
                    logger.info(f"Found {len(member_links.get('matches', []))} matches out of {len(member_links.get('all_scanned', []))} scanned")
                    
                    # Stage 2: Deep scrape matched profiles
                    if member_links.get('matches'):
                        status_callback({
                            'status': 'running',
                            'message': f'Stage 2: Deep scraping {len(member_links["matches"])} profiles...',
                            'job_id': job_id,
                            'stage': 'deep_scraping'
                        })
                        
                        # No limit on deep scraping - process ALL collected members
                        profiles_to_scrape = member_links['matches']
                        
                        scraped_data = await stage2_deep_scrape(
                            page, profiles_to_scrape, status_callback, job_id, start_time,
                            industry=industry, group_name=group_name
                        )
                        
                        all_matches.extend(scraped_data)
                        
                        # Only save individual CSV if single group, otherwise wait for combined
                        if len(urls) == 1 and scraped_data:
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            slug_suffix = generate_slug_suffix()
                            filename = f"{industry}_{slugify(group_name)}_{slug_suffix}_{timestamp}.csv"
                            filepath = os.path.join(SCRAPE_DIR, filename)
                            
                            save_to_csv(scraped_data, filepath)
                            
                            results.append({
                                'url': url,
                                'group_name': group_name,
                                'members_scanned': len(member_links.get('all_scanned', [])),
                                'matches_found': len(scraped_data),
                                'file': filename
                            })
                        else:
                            # For multi-group, just track results (combined CSV saved at end)
                            results.append({
                                'url': url,
                                'group_name': group_name,
                                'members_scanned': len(member_links.get('all_scanned', [])),
                                'matches_found': len(scraped_data),
                                'file': None  # Will be set to combined file at end
                            })
                            
                        # Update status after completing each group
                        status_callback({
                            'status': 'running',
                            'message': f'Completed group {url_idx + 1}/{len(urls)}: {group_name} ({len(scraped_data)} leads). Moving to next...',
                            'job_id': job_id,
                            'url_progress': f'{url_idx + 1}/{len(urls)}',
                            'groups_completed': url_idx + 1,
                            'total_groups': len(urls),
                            'total_matches': len(all_matches),
                            'total_scanned': total_scanned
                        })
                    else:
                        results.append({
                            'url': url,
                            'group_name': group_name,
                            'members_scanned': len(member_links.get('all_scanned', [])),
                            'matches_found': 0,
                            'file': None
                        })
                        
                        # Update status - no matches but move to next
                        status_callback({
                            'status': 'running',
                            'message': f'Completed group {url_idx + 1}/{len(urls)}: {group_name} (0 leads). Moving to next...',
                            'job_id': job_id,
                            'url_progress': f'{url_idx + 1}/{len(urls)}',
                            'groups_completed': url_idx + 1,
                            'total_groups': len(urls)
                        })
                
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {e}")
                    await take_debug_screenshot(page, 'url_error')
                    results.append({
                        'url': url,
                        'error': str(e),
                        'matches_found': 0
                    })
                    
                    # Don't exit loop on single URL error - continue to next URL
                    status_callback({
                        'status': 'running',
                        'message': f'Error on group {url_idx + 1}/{len(urls)}, continuing to next...',
                        'job_id': job_id,
                        'url_progress': f'{url_idx + 1}/{len(urls)}'
                    })
                    continue  # Explicitly continue to next URL
            
            await browser.close()
            
        except Exception as e:
            logger.error(f"Browser error: {e}")
            status_callback({
                'status': 'error',
                'message': f'Browser error: {str(e)}',
                'job_id': job_id
            })
            return {'success': False, 'error': str(e)}
    
    # Create combined CSV with all leads from all groups
    combined_filename = None
    if all_matches and len(group_names_scraped) > 0:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        slug_suffix = generate_slug_suffix()
        
        # Create filename with all group names (max 3 for readability)
        if len(group_names_scraped) <= 3:
            groups_slug = '_'.join([slugify(name)[:20] for name in group_names_scraped])
        else:
            groups_slug = '_'.join([slugify(name)[:15] for name in group_names_scraped[:3]]) + f'_and_{len(group_names_scraped)-3}_more'
        
        combined_filename = f"{industry}_{groups_slug}_{slug_suffix}_{timestamp}.csv"
        combined_filepath = os.path.join(SCRAPE_DIR, combined_filename)
        
        # Add source group to each lead
        for lead in all_matches:
            if 'source_group' not in lead:
                lead['source_group'] = ', '.join(group_names_scraped)
        
        save_to_csv(all_matches, combined_filepath)
        logger.info(f"Saved combined CSV with {len(all_matches)} leads from {len(group_names_scraped)} groups: {combined_filename}")
    
    # Final status
    status_callback({
        'status': 'completed',
        'message': f'Completed! Found {len(all_matches)} leads from {len(group_names_scraped)} groups.',
        'job_id': job_id,
        'total_matches': len(all_matches),
        'total_scanned': total_scanned,
        'groups_scraped': group_names_scraped,
        'combined_file': combined_filename
    })
    
    return {
        'success': True,
        'results': results,
        'total_matches': len(all_matches),
        'total_scanned': total_scanned,
        'groups_scraped': group_names_scraped,
        'combined_file': combined_filename
    }


async def stage1_collect_links(
    page: Page,
    industry: str,
    status_callback: Callable,
    job_id: str,
    collect_all: bool = False,
    start_time: datetime = None
) -> Dict:
    """Stage 1: Infinite scroll and collect member links - WITH ERROR RECOVERY"""
    
    all_scanned = set()
    matches = []
    no_new_count = 0
    scroll_count = 0
    max_scrolls = 50000
    last_gc = 0
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    if start_time is None:
        start_time = datetime.now(timezone.utc)
    
    # Try to click "New to the group" section if available
    try:
        new_members_btn = await page.query_selector('text="New to the group"')
        if new_members_btn:
            await new_members_btn.click()
            await asyncio.sleep(1)
    except:
        pass
    
    while scroll_count < max_scrolls and no_new_count < 20:
        # Check timeout every 100 scrolls
        if scroll_count % 100 == 0:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > 10800:  # 3 hours max for stage 1
                logger.info(f"Stage 1 timeout after {elapsed:.0f}s, {len(all_scanned)} scanned")
                break
        
        # MEMORY OPTIMIZATION: Clear old DOM references every 500 scrolls
        if scroll_count - last_gc > 500:
            try:
                await page.evaluate('() => { window.gc && window.gc(); }')
            except:
                pass
            last_gc = scroll_count
        
        # Extract member data with error handling
        try:
            members_data = await page.evaluate('''
                () => {
                    const results = [];
                    const seen = new Set();
                    document.querySelectorAll('[role="listitem"]').forEach(item => {
                        const profileLinks = item.querySelectorAll('a[href*="/user/"]');
                        if (profileLinks.length > 0) {
                            const href = profileLinks[0].href;
                            if (seen.has(href)) return;
                            seen.add(href);
                            
                            let name = '';
                            for (const link of profileLinks) {
                                if (link.innerText && link.innerText.trim().length > 0) {
                                    name = link.innerText.trim();
                                    break;
                                }
                            }
                            
                            const itemText = item.innerText || '';
                            
                            if (href && name) {
                                results.push({
                                    href: href,
                                    name: name,
                                    context: itemText.substring(0, 300)
                                });
                            }
                        }
                    });
                    return results;
                }
            ''')
            consecutive_errors = 0  # Reset on success
            
        except Exception as e:
            consecutive_errors += 1
            error_msg = str(e)
            logger.warning(f"Stage 1 extraction error ({consecutive_errors}): {error_msg[:100]}")
            
            # Handle specific errors
            if 'Execution context was destroyed' in error_msg:
                logger.error("Page navigation detected during collection")
                # Try to recover by going back to members page
                try:
                    current_url = page.url
                    if '/members' not in current_url:
                        # Navigate back to members page
                        await page.go_back()
                        await asyncio.sleep(2)
                except:
                    pass
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping Stage 1")
                break
            
            await asyncio.sleep(1)
            continue
        
        new_found = 0
        for item in members_data:
            href = item['href']
            name = item['name']
            context = item.get('context', '')
            
            # Skip if already seen
            if href in all_scanned:
                continue
            # Skip invalid names
            if len(name) < 2 or name.lower() in ['see more', 'view profile', 'message', 'add friend']:
                continue
                
            all_scanned.add(href)
            new_found += 1
            
            # Combine name and context for matching
            full_text = f"{name} {context}"
            
            # FILTER: Only collect if they appear to be a business prospect
            if is_qualified_prospect(full_text, industry):
                matches.append({
                    'url': href, 
                    'text': name,
                    'context': context
                })
        
        if new_found == 0:
            no_new_count += 1
        else:
            no_new_count = 0
        
        # Update progress
        benchmark_segment = min(len(all_scanned) // 50, 10)
        status_callback({
            'status': 'running',
            'message': f'Scanning... {len(matches)} business prospects found from {len(all_scanned)} members',
            'job_id': job_id,
            'members_scanned': len(all_scanned),
            'matches_found': len(matches),
            'benchmark_progress': f"{benchmark_segment}{'0+' if benchmark_segment >= 10 else ''}",
            'stage': 'collecting'
        })
        
        # Scroll with error handling
        try:
            await page.evaluate('window.scrollBy(0, 1500)')
            await asyncio.sleep(SCROLL_DELAY)
            scroll_count += 1
            
            # Every 5 scrolls, do a bigger jump
            if scroll_count % 5 == 0:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.3)
        except Exception as scroll_error:
            logger.warning(f"Scroll error: {scroll_error}")
            await asyncio.sleep(1)
    
    logger.info(f"Stage 1 complete: {len(all_scanned)} scanned, {len(matches)} matches")
    
    return {
        'all_scanned': list(all_scanned),
        'matches': matches
    }


async def scrape_single_profile(page: Page, match: Dict) -> Dict:
    """Scrape a single profile - IMPROVED DATA EXTRACTION"""
    original_url = match['url']
    name = match.get('text', '').split('\n')[0].strip()[:100]
    
    phone = ''
    website = ''
    about = ''
    profile_url = original_url
    
    try:
        user_id_match = re.search(r'/user/(\d+)', original_url)
        if user_id_match:
            user_id = user_id_match.group(1)
            profile_url = f"https://www.facebook.com/profile.php?id={user_id}"
        
        await page.goto(profile_url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(1.0)  # Increased wait for content to load
        
        # Try to click "About" or "See About" to load more info
        try:
            about_btn = await page.query_selector('a[href*="/about"], span:has-text("See About"), span:has-text("About")')
            if about_btn:
                await about_btn.click()
                await asyncio.sleep(0.8)
        except:
            pass
        
        # IMPROVED extraction with multiple phone patterns and better website detection
        extracted = await page.evaluate('''
            () => {
                const text = document.body.innerText || '';
                const html = document.body.innerHTML || '';
                let phone = '', website = '', followers = '', bio = '', email = '';
                
                // IMPROVED PHONE PATTERNS - More comprehensive
                const phonePatterns = [
                    /\\b(\\d{3}[-.]\\d{3}[-.]\\d{4})\\b/,                    // 555-555-5555
                    /\\((\\d{3})\\)\\s*(\\d{3})[-.]?(\\d{4})/,               // (555) 555-5555
                    /\\b(\\d{3})\\s+(\\d{3})\\s+(\\d{4})\\b/,                // 555 555 5555
                    /\\b(\\d{10})\\b/,                                        // 5555555555
                    /\\+1[-.]?(\\d{3})[-.]?(\\d{3})[-.]?(\\d{4})/,           // +1-555-555-5555
                    /\\b1[-.]?(\\d{3})[-.]?(\\d{3})[-.]?(\\d{4})/,           // 1-555-555-5555
                    /Mobile\\s*[:\\n]?\\s*(\\d[\\d\\s.-]+\\d)/i,             // Mobile: number
                    /Phone\\s*[:\\n]?\\s*(\\d[\\d\\s.-]+\\d)/i,              // Phone: number
                    /Call\\s*[:\\n]?\\s*(\\d[\\d\\s.-]+\\d)/i,               // Call: number
                    /Contact\\s*[:\\n]?\\s*(\\d[\\d\\s.-]+\\d)/i,            // Contact: number
                    /Tel\\s*[:\\n]?\\s*(\\d[\\d\\s.-]+\\d)/i,                // Tel: number
                ];
                
                for (const pattern of phonePatterns) {
                    const match = text.match(pattern);
                    if (match) {
                        // Clean up the phone number
                        let rawPhone = match[0];
                        // Extract just the digits
                        let digits = rawPhone.replace(/\\D/g, '');
                        // Format if we have 10 or 11 digits
                        if (digits.length === 10) {
                            phone = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6);
                            break;
                        } else if (digits.length === 11 && digits[0] === '1') {
                            phone = digits.slice(1,4) + '-' + digits.slice(4,7) + '-' + digits.slice(7);
                            break;
                        } else if (digits.length >= 10) {
                            // Take last 10 digits
                            digits = digits.slice(-10);
                            phone = digits.slice(0,3) + '-' + digits.slice(3,6) + '-' + digits.slice(6);
                            break;
                        }
                    }
                }
                
                // Domains to skip (social media and messaging platforms)
                const skipDomains = /facebook|instagram|twitter|youtube|tiktok|linkedin|whatsapp|wa\\.me|t\\.me|telegram|messenger|bit\\.ly|linktr\\.ee/i;
                
                // Method 1: External links via Facebook's redirect
                document.querySelectorAll('a[href*="l.facebook.com/l.php"]').forEach(a => {
                    if (website) return;
                    try {
                        const decoded = decodeURIComponent(new URL(a.href).searchParams.get('u') || '');
                        if (decoded && !decoded.match(skipDomains)) {
                            website = decoded.split('?')[0];
                        }
                    } catch(e) {}
                });
                
                // Method 2: Look for website mentions in text
                if (!website) {
                    const urlPattern = /(?:Website|Site|Web)[:\\s]*([a-zA-Z0-9][a-zA-Z0-9-]*\\.[a-zA-Z]{2,}(?:\\/[^\\s]*)?)/i;
                    const urlMatch = text.match(urlPattern);
                    if (urlMatch && !urlMatch[1].match(skipDomains)) {
                        website = urlMatch[1].startsWith('http') ? urlMatch[1] : 'https://' + urlMatch[1];
                    }
                }
                
                // Method 3: Look for any .com/.net/.org links in the visible text
                if (!website) {
                    const domainPattern = /\\b([a-zA-Z0-9][a-zA-Z0-9-]*\\.(?:com|net|org|io|co|biz|info|us))\\b/gi;
                    const domains = text.match(domainPattern);
                    if (domains) {
                        for (const domain of domains) {
                            if (!domain.match(skipDomains) && !domain.match(/facebook|google|apple/i)) {
                                website = 'https://' + domain.toLowerCase();
                                break;
                            }
                        }
                    }
                }
                
                // Extract followers
                const fm = text.match(/([\\d,\\.]+[KkMm]?)\\s*followers/i);
                if (fm) followers = fm[1] + ' followers';
                
                // Extract bio/intro - multiple patterns
                const bioPatterns = [
                    /Intro\\n([^\\n]+)/i,
                    /About\\n([^\\n]+)/i,
                    /Bio\\n([^\\n]+)/i,
                    /Overview\\n([^\\n]+)/i,
                ];
                for (const pattern of bioPatterns) {
                    const bm = text.match(pattern);
                    if (bm) {
                        bio = bm[1].trim().substring(0, 150);
                        break;
                    }
                }
                
                // Extract email if present
                const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                if (emailMatch) email = emailMatch[0];
                
                return { phone, website, followers, bio, email };
            }
        ''')
        
        phone = extracted.get('phone', '')
        website = extracted.get('website', '')
        email = extracted.get('email', '')
        
        # Build about string
        about_parts = []
        if extracted.get('followers'):
            about_parts.append(extracted.get('followers'))
        if extracted.get('bio'):
            about_parts.append(extracted.get('bio'))
        if email:
            about_parts.append(f"Email: {email}")
        about = ' | '.join(about_parts)
        
    except asyncio.TimeoutError:
        logger.debug(f"Timeout scraping {name}")
    except Exception as e:
        logger.debug(f"Error scraping {name}: {str(e)[:50]}")
    
    return {
        'name': name,
        'url': profile_url,
        'phone': phone,
        'website': website,
        'has_website': 'Yes' if website else 'No',
        'about': about,
        'work': ''
    }


async def stage2_deep_scrape(
    page: Page,
    matches: List[Dict],
    status_callback: Callable,
    job_id: str,
    start_time: datetime = None,
    industry: str = 'unknown',
    group_name: str = 'unknown'
) -> List[Dict]:
    """Stage 2: Deep scrape profiles - WITH CHECKPOINT SAVING & SPEED OPTIMIZATION"""
    
    results = []
    total = len(matches)
    errors_in_row = 0
    max_errors = 5
    checkpoint_interval = 50  # Save every 50 profiles (changed from 25)
    last_checkpoint = 0
    
    if start_time is None:
        start_time = datetime.now(timezone.utc)
    
    # Generate checkpoint filename
    checkpoint_suffix = secrets.token_hex(4)
    checkpoint_base = f"{industry}_{slugify(group_name)}_{checkpoint_suffix}"
    
    for idx, match in enumerate(matches):
        # Check timeout every 50 profiles
        if idx % 50 == 0:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > 14400:  # 4 hours max total
                logger.info(f"Stage 2 timeout after {elapsed:.0f}s, {idx}/{total} profiles done")
                break
        
        # SPEED OPTIMIZATION: After 1000 profiles, reduce delays to maintain speed
        if idx >= 1000 and idx % 500 == 0:
            # Clear browser cache/memory periodically for long scrapes
            try:
                await page.evaluate('() => { if (window.gc) window.gc(); }')
                logger.info(f"Memory cleanup at profile {idx}")
            except:
                pass
        
        # Status update every 10 profiles
        if idx % 10 == 0:
            status_callback({
                'status': 'running',
                'message': f'Deep scraping: {idx+1}/{total} profiles',
                'job_id': job_id,
                'deep_scrape_progress': f'{idx+1}/{total}',
                'stage': 'deep_scraping'
            })
        
        # CHECKPOINT SAVE - Save progress every 50 profiles
        if len(results) > 0 and len(results) - last_checkpoint >= checkpoint_interval:
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                checkpoint_file = f"{checkpoint_base}_checkpoint_{timestamp}.csv"
                checkpoint_path = os.path.join(SCRAPE_DIR, checkpoint_file)
                save_to_csv(results.copy(), checkpoint_path)
                last_checkpoint = len(results)
                logger.info(f"Checkpoint saved: {len(results)} profiles to {checkpoint_file}")
                
                # Update status with checkpoint info
                status_callback({
                    'status': 'running',
                    'message': f'Checkpoint saved ({len(results)} leads). Continuing...',
                    'job_id': job_id,
                    'checkpoint_file': checkpoint_file,
                    'checkpoint_count': len(results)
                })
            except Exception as e:
                logger.warning(f"Checkpoint save failed: {e}")
        
        try:
            result = await scrape_single_profile(page, match)
            results.append(result)
            errors_in_row = 0
            
        except Exception as e:
            errors_in_row += 1
            error_msg = str(e)[:100]
            logger.warning(f"Profile scrape error ({errors_in_row}): {error_msg}")
            
            # Check for fatal errors that need immediate handling
            if 'Execution context was destroyed' in error_msg:
                logger.error("Page navigation detected - attempting recovery")
                try:
                    await page.goto('https://www.facebook.com', wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(1)
                    errors_in_row = 0
                except:
                    pass
            
            # If too many errors, try refreshing
            elif errors_in_row >= max_errors:
                try:
                    logger.info(f"Too many errors ({errors_in_row}), refreshing page...")
                    await page.reload(wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(1)
                    errors_in_row = 0
                except:
                    pass
        
        # Minimal delay
        await asyncio.sleep(0.3)
    
    # Delete checkpoint files if we completed successfully (final save will happen in main function)
    if len(results) == total:
        try:
            import glob
            checkpoint_pattern = os.path.join(SCRAPE_DIR, f"{checkpoint_base}_checkpoint_*.csv")
            for f in glob.glob(checkpoint_pattern):
                os.remove(f)
                logger.info(f"Removed checkpoint: {f}")
        except:
            pass
    
    return results


def save_to_csv(data: List[Dict], filepath: str):
    """Save scraped data to CSV file - optimized for prospects with phones, no websites"""
    if not data:
        return
    
    # Sort data: prioritize those WITH phone and WITHOUT website (best prospects)
    def prospect_score(item):
        has_phone = 1 if item.get('phone') else 0
        no_website = 1 if not item.get('website') else 0
        return (has_phone + no_website, has_phone)  # Best: phone + no website
    
    sorted_data = sorted(data, key=prospect_score, reverse=True)
    
    # Add prospect quality indicator
    for item in sorted_data:
        has_phone = bool(item.get('phone'))
        has_website = bool(item.get('website'))
        if has_phone and not has_website:
            item['prospect_quality'] = 'HOT'  # Has phone, no website = best lead
        elif has_phone:
            item['prospect_quality'] = 'WARM'  # Has phone + website
        elif not has_website:
            item['prospect_quality'] = 'COLD'  # No phone, no website
        else:
            item['prospect_quality'] = 'LOW'   # No phone but has website
    
    fieldnames = ['prospect_quality', 'name', 'phone', 'website', 'has_website', 'about', 'work', 'url']
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sorted_data)
    
    # Count stats
    hot_leads = sum(1 for d in sorted_data if d.get('prospect_quality') == 'HOT')
    warm_leads = sum(1 for d in sorted_data if d.get('prospect_quality') == 'WARM')
    with_phone = sum(1 for d in sorted_data if d.get('phone'))
    
    logger.info(f"Saved {len(sorted_data)} records to {filepath}")
    logger.info(f"  HOT leads (phone, no website): {hot_leads}")
    logger.info(f"  WARM leads (phone + website): {warm_leads}")
    logger.info(f"  Total with phone: {with_phone}")
