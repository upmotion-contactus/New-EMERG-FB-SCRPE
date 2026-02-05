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
        title = await page.title()
        if 'log in' in title.lower() or 'login' in title.lower():
            return True
        
        # Check for login form elements
        login_form = await page.query_selector('form[action*="login"]')
        if login_form:
            return True
        
        # Check page content
        content = await page.content()
        if 'id="loginbutton"' in content or 'name="login"' in content:
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
    """Main scraping function for Facebook groups"""
    
    results = []
    all_matches = []
    total_scanned = 0
    
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
            # Launch browser - use dynamic path or let Playwright find it
            launch_options = {
                'headless': True,
                'args': [
                    '--no-sandbox', 
                    '--disable-setuid-sandbox', 
                    '--disable-gpu', 
                    '--disable-dev-shm-usage',
                    '--disable-software-rasterizer',
                    '--single-process'
                ]
            }
            
            if chromium_path:
                launch_options['executable_path'] = chromium_path
                logger.info(f"Launching Chromium from custom path: {chromium_path}")
            else:
                # In production Kubernetes, Playwright will use its own browser discovery
                logger.info("Launching Chromium using Playwright's default browser discovery")
            
            try:
                browser = await p.chromium.launch(**launch_options)
            except Exception as launch_error:
                # If custom path fails, try without it (let Playwright find browser)
                if chromium_path:
                    logger.warning(f"Custom path failed ({launch_error}), trying Playwright default...")
                    del launch_options['executable_path']
                    browser = await p.chromium.launch(**launch_options)
                else:
                    raise launch_error
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Add cookies
            await context.add_cookies(formatted_cookies)
            
            page = await context.new_page()
            
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
                    
                    # Stage 1: Collect member links with infinite scroll
                    status_callback({
                        'status': 'running',
                        'message': f'Stage 1: Collecting member links from {group_name}...',
                        'job_id': job_id,
                        'stage': 'collecting'
                    })
                    
                    member_links = await stage1_collect_links(
                        page, industry, status_callback, job_id
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
                        # For very large groups, this runs in background
                        profiles_to_scrape = member_links['matches']
                        
                        scraped_data = await stage2_deep_scrape(
                            page, profiles_to_scrape, status_callback, job_id
                        )
                        
                        all_matches.extend(scraped_data)
                        
                        # Save to CSV
                        if scraped_data:
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
                        results.append({
                            'url': url,
                            'group_name': group_name,
                            'members_scanned': len(member_links.get('all_scanned', [])),
                            'matches_found': 0,
                            'file': None
                        })
                
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {e}")
                    await take_debug_screenshot(page, 'url_error')
                    results.append({
                        'url': url,
                        'error': str(e),
                        'matches_found': 0
                    })
            
            await browser.close()
            
        except Exception as e:
            logger.error(f"Browser error: {e}")
            status_callback({
                'status': 'error',
                'message': f'Browser error: {str(e)}',
                'job_id': job_id
            })
            return {'success': False, 'error': str(e)}
    
    # Final status
    status_callback({
        'status': 'completed',
        'message': f'Completed! Found {len(all_matches)} leads from {len(urls)} groups.',
        'job_id': job_id,
        'total_matches': len(all_matches),
        'total_scanned': total_scanned
    })
    
    return {
        'success': True,
        'results': results,
        'total_matches': len(all_matches),
        'total_scanned': total_scanned
    }


async def stage1_collect_links(
    page: Page,
    industry: str,
    status_callback: Callable,
    job_id: str,
    collect_all: bool = False  # Changed to False - now filters for business prospects only
) -> Dict:
    """Stage 1: Infinite scroll and collect member links - FILTERS FOR BUSINESSES ONLY"""
    
    all_scanned = set()
    matches = []
    no_new_count = 0
    scroll_count = 0
    max_scrolls = 50000  # Effectively unlimited - can handle 2M+ members
    
    # Try to click "New to the group" section if available
    try:
        new_members_btn = await page.query_selector('text="New to the group"')
        if new_members_btn:
            await new_members_btn.click()
            await asyncio.sleep(2)
    except:
        pass
    
    while scroll_count < max_scrolls and no_new_count < 20:  # Increased patience for large groups
        # Extract member data from listitem elements (Facebook's member card structure)
        members_data = await page.evaluate('''
            () => {
                const results = [];
                document.querySelectorAll('[role="listitem"]').forEach(item => {
                    // Find profile link within the listitem
                    const profileLinks = item.querySelectorAll('a[href*="/user/"]');
                    if (profileLinks.length > 0) {
                        const profileLink = profileLinks[0];
                        const href = profileLink.href;
                        
                        // Get the name (usually in the second link with text)
                        let name = '';
                        for (const link of profileLinks) {
                            if (link.innerText && link.innerText.trim().length > 0) {
                                name = link.innerText.trim();
                                break;
                            }
                        }
                        
                        // Get additional context from the listitem
                        const itemText = item.innerText || '';
                        
                        if (href && name) {
                            results.push({
                                href: href,
                                name: name,
                                context: itemText.substring(0, 500)
                            });
                        }
                    }
                });
                return results;
            }
        ''')
        
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
            # Must have either: industry keywords OR business indicators (Works at, Owner, LLC, etc.)
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
        
        # Update progress with benchmark (50-member segments)
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
        
        # Scroll down
        await page.evaluate('window.scrollBy(0, 800)')
        await asyncio.sleep(0.8)
        scroll_count += 1
    
    logger.info(f"Stage 1 complete: {len(all_scanned)} scanned, {len(matches)} matches")
    
    return {
        'all_scanned': list(all_scanned),
        'matches': matches
    }


async def stage2_deep_scrape(
    page: Page,
    matches: List[Dict],
    status_callback: Callable,
    job_id: str
) -> List[Dict]:
    """Stage 2: Visit each PROFILE page and extract contact info"""
    
    results = []
    
    for idx, match in enumerate(matches):
        original_url = match['url']
        name = match.get('text', '').split('\n')[0].strip()[:100]
        
        status_callback({
            'status': 'running',
            'message': f'Scraping {idx + 1}/{len(matches)}: {name[:30]}...',
            'job_id': job_id,
            'deep_scrape_progress': f'{idx + 1}/{len(matches)}',
            'stage': 'deep_scraping'
        })
        
        phone = ''
        website = ''
        about = ''
        work = ''
        profile_url = original_url
        
        try:
            # IMPORTANT: Convert group user URL to direct profile URL
            # Group URLs show limited popup, profile URLs show full page with contact info
            user_id_match = re.search(r'/user/(\d+)', original_url)
            if user_id_match:
                user_id = user_id_match.group(1)
                profile_url = f"https://www.facebook.com/profile.php?id={user_id}"
                logger.info(f"Converted {original_url} -> {profile_url}")
            
            # Navigate to profile page
            await page.goto(profile_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
            
            # Get page text content
            page_text = await page.evaluate('() => document.body.innerText || ""')
            
            # Extract phone - multiple patterns
            phone_patterns = [
                r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b',
                r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}',
                r'\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
            ]
            for pattern in phone_patterns:
                phone_match = re.search(pattern, page_text)
                if phone_match:
                    phone = phone_match.group(0)
                    logger.info(f"Found phone for {name}: {phone}")
                    break
            
            # Extract website from external links
            external_links = await page.evaluate('''
                () => {
                    const links = [];
                    document.querySelectorAll('a[href*="l.facebook.com/l.php"]').forEach(a => {
                        try {
                            const url = new URL(a.href);
                            const decoded = decodeURIComponent(url.searchParams.get('u') || '');
                            if (decoded) links.push(decoded);
                        } catch(e) {}
                    });
                    return links;
                }
            ''')
            
            for link in external_links:
                if not any(x in link.lower() for x in ['facebook.com', 'instagram.com', 'twitter.com', 'youtube.com', 'tiktok.com', 'linkedin.com']):
                    website = link.split('?')[0]  # Remove tracking params
                    logger.info(f"Found website for {name}: {website}")
                    break
            
            # Extract ABOUT info: follower count and bio
            about_data = await page.evaluate('''
                () => {
                    const text = document.body.innerText || '';
                    let followers = '';
                    let bio = '';
                    
                    // Extract follower count - various formats
                    const followerPatterns = [
                        /([\\d,\\.]+[KkMm]?)\\s*followers/i,
                        /Followed by ([\\d,\\.]+[KkMm]?)\\s*people/i,
                        /([\\d,\\.]+)\\s*people follow/i,
                    ];
                    
                    for (const pattern of followerPatterns) {
                        const match = text.match(pattern);
                        if (match) {
                            followers = match[1] + ' followers';
                            break;
                        }
                    }
                    
                    // Extract bio/intro - look for intro section or first meaningful text
                    const bioPatterns = [
                        /Intro\\n([^\\n]+)/i,
                        /About\\n([^\\n]+)/i,
                        /Bio\\n([^\\n]+)/i,
                    ];
                    
                    for (const pattern of bioPatterns) {
                        const match = text.match(pattern);
                        if (match) {
                            bio = match[1].trim().substring(0, 150);
                            break;
                        }
                    }
                    
                    // If no bio found, try to get description from meta or page content
                    if (!bio) {
                        const metaDesc = document.querySelector('meta[name="description"]');
                        if (metaDesc && metaDesc.content) {
                            bio = metaDesc.content.substring(0, 150);
                        }
                    }
                    
                    return { followers, bio };
                }
            ''')
            
            # Combine follower count and bio into about field
            follower_str = about_data.get('followers', '')
            bio_str = about_data.get('bio', '')
            
            if follower_str and bio_str:
                about = f"{follower_str} | {bio_str}"
            elif follower_str:
                about = follower_str
            elif bio_str:
                about = bio_str
            
            if about:
                logger.info(f"Found about for {name}: {about[:50]}...")
            
        except Exception as e:
            logger.error(f"Error scraping {name} at {profile_url}: {str(e)}")
        
        # Always append result even if extraction failed
        results.append({
            'name': name,
            'url': profile_url,
            'phone': phone,
            'website': website,
            'has_website': 'Yes' if website else 'No',
            'about': about,
            'work': work
        })
        
        # Small delay between requests to avoid rate limiting
        await asyncio.sleep(1.5)
    
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
