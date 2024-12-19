import argparse
import os
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import logging
import json
from typing import Optional

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

def convert_to_markdown(article_data: dict) -> Optional[str]:
    """
    Convert article data to markdown format
    """
    try:
        if not article_data.get('success'):
            logger.error(f"Article extraction failed: {article_data.get('error', 'Unknown error')}")
            return None

        markdown_content = []
        
        # Add title
        if article_data.get('title'):
            markdown_content.append(f"# {article_data['title']}\n")
        
        # Add metadata if available
        if article_data.get('author'):
            markdown_content.append(f"Author: {article_data['author']}\n")
        if article_data.get('published_date'):
            markdown_content.append(f"Published: {article_data['published_date']}\n")
        
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

def main():
    parser = argparse.ArgumentParser(description='Download sitemap pages as markdown')
    parser.add_argument('--sitemap_url', required=True, help='URL of the sitemap.xml file')
    parser.add_argument('--output_dir', default='output', help='Output directory for markdown files')
    parser.add_argument('--api_key', help='RapidAPI key (can also be set as RAPID_API_KEY env variable)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be downloaded without actually downloading')
    
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
    
    # Process each URL
    for url in urls:
        if args.dry_run:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            path = parsed_url.path.strip('/') or 'index'
            file_path = os.path.join(args.output_dir, domain, path)
            if not file_path.endswith('.md'):
                file_path += '.md'
            logger.info(f"Would download: {url}")
            logger.info(f"Would save to: {file_path}")
        else:
            logger.info(f"Processing: {url}")
            article_data = parse_article(url)
            content = convert_to_markdown(article_data)
            if content:
                save_markdown(content, url, args.output_dir)

if __name__ == '__main__':
    main() 