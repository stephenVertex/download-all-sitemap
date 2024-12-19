import argparse
import os
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import logging
import json
from typing import Optional
import time
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# This should be set as an environment variable or passed as an argument
RAPID_API_KEY = os.getenv('RAPID_API_KEY')

def parse_sitemap(sitemap_url):
    """
    Parse the sitemap XML and return a list of URLs
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(sitemap_url, headers=headers)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        # Remove namespace for easier parsing
        namespace = root.tag.split('}')[0] + '}'
        
        urls = []
        for url in root.findall(f'.//{namespace}url'):
            loc = url.find(f'{namespace}loc')
            if loc is not None:
                urls.append(loc.text)
        
        return urls
    except Exception as e:
        logger.error(f"Error parsing sitemap: {e}")
        return []

def parse_article(article_url):
    """
    Parse article using the article-extractor2 API
    """
    url = "https://article-extractor2.p.rapidapi.com/article/parse"
    querystring = { 
        "url": article_url,
        "word_per_minute":"300",
        "desc_truncate_len":"210",
        "desc_len_min":"180",
        "content_len_min":"200" 
    }
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "article-extractor2.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers, params=querystring)
    return response.json()

def download_with_semareader(article_url: str) -> dict:
    """
    Parse article using the Sema Reader API
    
    Args:
        article_url: URL of the article to parse
        
    Returns:
        dict: Parsed article data
    """
    url = "https://semareader.p.rapidapi.com/scrape"
    
    querystring = {"url": article_url}
    
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "semareader.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error parsing article with Sema Reader: {e}")
        return {"success": False, "error": str(e)}

def convert_to_markdown(article_data: dict) -> Optional[str]:
    """
    Convert article data to markdown format
    """
    try:
        # Handle article-extractor2 format
        if 'error' in article_data:
            if article_data['error'] != 0:  # Non-zero means error
                logger.error(f"Article extraction failed: {article_data.get('message', 'Unknown error')}")
                return None
            # Success case - get the actual data
            article_data = article_data.get('data', {})
        
        # Handle semareader format
        elif not article_data.get('success', True):  # Keep existing check for semareader
            logger.error(f"Article extraction failed: {article_data.get('error', 'Unknown error')}")
            return None

        markdown_content = []
        
        # Add title
        if article_data.get('title'):
            markdown_content.append(f"# {article_data['title']}\n")
        
        # Add metadata if available
        if article_data.get('author'):
            markdown_content.append(f"Author: {article_data['author']}\n")
        if article_data.get('published') or article_data.get('published_date'):
            published = article_data.get('published') or article_data.get('published_date')
            markdown_content.append(f"Published: {published}\n")
        
        # Add main content
        if article_data.get('content'):
            markdown_content.append(article_data['content'])
        
        return '\n'.join(markdown_content)
    except Exception as e:
        logger.error(f"Error converting to markdown: {e}")
        return None

def save_markdown(content, url, output_dir):
    """
    Save markdown content to a file
    """
    try:
        # Parse the URL to create directory structure
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path.strip('/')
        
        if not path:
            path = 'index'
        
        # Create directory structure
        file_path = os.path.join(output_dir, domain, path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Add .md extension if not present
        if not file_path.endswith('.md'):
            file_path += '.md'
        
        # Save the content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        logger.info(f"Saved: {file_path}")
    except Exception as e:
        logger.error(f"Error saving file for {url}: {e}")

def save_json_response(article_data: dict, url: str, output_dir: str, parser: str):
    """
    Save the raw JSON response along with metadata about the parser used
    """
    try:
        # Parse the URL to create directory structure
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path.strip('/') or 'index'
        
        # Create directory structure
        file_path = os.path.join(output_dir, domain, path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Add .json extension
        file_path += '.json'
        
        # Add metadata about the parser used
        response_data = {
            'parser': parser,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'url': url,
            'response': article_data
        }
        
        # Save the content
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Saved JSON: {file_path}")
    except Exception as e:
        logger.error(f"Error saving JSON file for {url}: {e}")

def get_markdown_path(url: str, output_dir: str) -> str:
    """
    Generate the markdown file path for a given URL
    
    Args:
        url: The URL to generate path for
        output_dir: Base output directory
        
    Returns:
        str: Full path where markdown file should be saved
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path.strip('/') or 'index'
    
    # Create file path
    file_path = os.path.join(output_dir, domain, path)
    if not file_path.endswith('.md'):
        file_path += '.md'
        
    return file_path

def main():
    parser = argparse.ArgumentParser(description='Download sitemap pages as markdown')
    parser.add_argument('--sitemap_url', required=True, help='URL of the sitemap.xml file')
    parser.add_argument('--output_dir', default='output', help='Output directory for markdown files')
    parser.add_argument('--api_key', help='RapidAPI key (can also be set as RAPID_API_KEY env variable)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be downloaded without actually downloading')
    parser.add_argument('--no-random-sleep', action='store_true', help='Disable random sleep between requests')
    parser.add_argument('--parser', choices=['article-extractor2', 'semareader'], 
                       default='article-extractor2',
                       help='Choose which parser to use')
    parser.add_argument('--force', action='store_true', 
                       help='Override existing files instead of skipping them')
    parser.add_argument('--limit', type=int, 
                       help='Limit the number of articles to download')
    parser.add_argument('--filter', type=str,
                       help='Only process URLs containing this string (e.g. "blog")')
    
    args = parser.parse_args()
    
    # Set API key
    global RAPID_API_KEY
    RAPID_API_KEY = args.api_key or RAPID_API_KEY
    
    if not RAPID_API_KEY:
        logger.error("RapidAPI key is required. Set it as RAPID_API_KEY environment variable or pass --api_key")
        return
    
    # Create output directory (skip in dry run)
    if not args.dry_run:
        os.makedirs(args.output_dir, exist_ok=True)
    
    # Get URLs from sitemap
    urls = parse_sitemap(args.sitemap_url)
    logger.info(f"Found {len(urls)} URLs in sitemap")
    
    # Filter URLs if filter argument is provided
    if args.filter:
        urls = [url for url in urls if args.filter in url]
        logger.info(f"After filtering for '{args.filter}': {len(urls)} URLs remain")
    
    # Process each URL
    attempts = 0  # Track total attempts instead of successful downloads
    for url in urls:
        if args.limit and attempts >= args.limit:
            logger.info(f"Reached limit of {args.limit} attempts, stopping.")
            break
            
        attempts += 1  # Increment attempts counter before processing
            
        if args.dry_run:
            file_path = get_markdown_path(url, args.output_dir)
            logger.info(f"Would download: {url}")
            logger.info(f"Would save to: {file_path}")
        else:
            logger.info(f"Processing: {url}")
            
            # Check if file already exists
            file_path = get_markdown_path(url, args.output_dir)
            if os.path.exists(file_path) and not args.force:
                logger.info(f"File already exists, skipping: {file_path}")
                continue
                
            # Add random sleep unless --no-random-sleep is specified
            if not args.no_random_sleep:
                sleep_time = random.uniform(1, 12)
                logger.info(f"Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
            
            # Choose parser based on argument
            if args.parser == 'semareader':
                article_data = download_with_semareader(url)
            else:
                article_data = parse_article(url)
                
            # Save the raw JSON response first
            save_json_response(article_data, url, args.output_dir, args.parser)
                
            content = convert_to_markdown(article_data)
            if content:
                save_markdown(content, url, args.output_dir)

if __name__ == '__main__':
    main() 