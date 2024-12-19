import os
import argparse
import logging
import boto3
import json
from typing import Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add thread-local storage for boto3 clients
thread_local = threading.local()

# Modify get_bedrock_client to use thread-local storage
def get_bedrock_client():
    """Initialize and return the Bedrock client using thread-local storage"""
    if not hasattr(thread_local, "client"):
        thread_local.client = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-east-1'  # Change this to your preferred region
        )
    return thread_local.client

def split_content(content: str, max_chunk_size: int = 6000) -> list:
    """Split content into chunks that respect markdown structure"""
    # First try to split on double newlines
    sections = content.split('\n\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    logger.info(f"Original content size: {len(content)} characters")
    logger.info(f"Split into {len(sections)} initial sections")
    
    for section in sections:
        # If a single section is too large, split it further on single newlines
        if len(section) > max_chunk_size:
            logger.info(f"Found large section of size {len(section)}, splitting further")
            subsections = section.split('\n')
            
            for subsection in subsections:
                # If still too large, split on periods, preserving them
                if len(subsection) > max_chunk_size:
                    logger.info(f"Found large subsection of size {len(subsection)}, splitting on sentences")
                    sentences = [s + '.' for s in subsection.split('.') if s]
                    for sentence in sentences:
                        if current_size + len(sentence) > max_chunk_size and current_chunk:
                            chunk_content = '\n'.join(current_chunk)
                            logger.info(f"Creating chunk {len(chunks)}: {len(chunk_content)} characters")
                            chunks.append(chunk_content)
                            current_chunk = []
                            current_size = 0
                        current_chunk.append(sentence)
                        current_size += len(sentence)
                else:
                    if current_size + len(subsection) > max_chunk_size and current_chunk:
                        chunk_content = '\n'.join(current_chunk)
                        logger.info(f"Creating chunk {len(chunks)}: {len(chunk_content)} characters")
                        chunks.append(chunk_content)
                        current_chunk = []
                        current_size = 0
                    current_chunk.append(subsection)
                    current_size += len(subsection)
        else:
            if current_size + len(section) > max_chunk_size and current_chunk:
                chunk_content = '\n\n'.join(current_chunk)
                logger.info(f"Creating chunk {len(chunks)}: {len(chunk_content)} characters")
                chunks.append(chunk_content)
                current_chunk = []
                current_size = 0
            current_chunk.append(section)
            current_size += len(section)
    
    if current_chunk:
        chunk_content = '\n\n'.join(current_chunk)
        logger.info(f"Creating final chunk {len(chunks)}: {len(chunk_content)} characters")
        chunks.append(chunk_content)
    
    logger.info(f"Split content into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        logger.info(f"Chunk {i} size: {len(chunk)} characters")
    
    return chunks

def clean_content_with_claude(content: str, client) -> Optional[str]:
    """
    Use Claude Haiku to clean the markdown content, handling large files by splitting into chunks
    """
    try:
        # Reduce max chunk size to ensure we stay well within Claude's context window
        chunks = split_content(content, max_chunk_size=6000)
        cleaned_chunks = []
        
        # Process first chunk (containing frontmatter) differently
        first_chunk = chunks[0]
        logger.info(f"Processing first chunk ({len(first_chunk)} characters)")
        
        prompt = f"""Please clean up this markdown content by:
1. Preserving any YAML frontmatter/metadata block at the start of the file EXACTLY as is, with no changes
2. Removing any remaining HTML tags in the main content
3. Fixing any formatting issues in the main content
4. Ensuring proper markdown syntax
5. Maintaining the original text and structure. Do not change the text.

IMPORTANT: If the file starts with a YAML block (enclosed in --- or +++ markers), you must keep it 
completely unchanged, preserving all whitespace, indentation, and values exactly as they appear 
in the original.

Here's the content to clean:

{first_chunk}

Please respond with only the cleaned markdown content, no explanations or other text."""

        # Process first chunk
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ]
        })

        response = client.invoke_model(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        cleaned_chunks.append(response_body['content'][0]['text'])

        # Process remaining chunks with a simpler prompt
        for i, chunk in enumerate(chunks[1:], 1):
            logger.info(f"Processing chunk {i} ({len(chunk)} characters)")
            prompt = f"""Please clean up this markdown content by:
1. Removing any HTML tags
2. Fixing any formatting issues
3. Ensuring proper markdown syntax
4. Maintaining the original text and structure

Here's the content to clean:

{chunk}

Please respond with only the cleaned markdown content, no explanations or other text."""

            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }
                ]
            })

            response = client.invoke_model(
                modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                body=body
            )
            
            response_body = json.loads(response['body'].read())
            cleaned_chunks.append(response_body['content'][0]['text'])

        # Combine cleaned chunks
        result = '\n\n'.join(cleaned_chunks)
        logger.info(f"Final cleaned content size: {len(result)} characters")
        return result

    except Exception as e:
        logger.error(f"Error cleaning content with Claude: {e}")
        return None

def process_markdown_file(input_file: str, output_file: Optional[str] = None, skip_existing: bool = False):
    """
    Process a single markdown file
    Args:
        input_file: Input file path
        output_file: Output file path (optional)
        skip_existing: Skip processing if output file already exists
    """
    client = get_bedrock_client()
    input_path = Path(input_file)
    
    # If no output file specified, create one in output_clean directory
    if output_file is None:
        # Get the relative path from the input directory to the file
        if 'downloaded_sites' in str(input_path.parent):
            # Replace 'downloaded_sites' with 'output_clean' in the path
            output_path = Path(str(input_path).replace('downloaded_sites', 'output_clean'))
        elif 'output' in str(input_path.parent):
            # Replace the first occurrence of 'output' with 'output_clean'
            parts = input_path.parts
            output_index = parts.index('output')
            new_parts = parts[:output_index] + ('output_clean',) + parts[output_index + 1:]
            output_path = Path(*new_parts)
        else:
            # Create output path in 'output_clean' directory parallel to input file
            output_path = input_path.parent.parent / 'output_clean' / input_path.name
    else:
        output_path = Path(output_file)
    
    # Skip if file exists and skip-existing is enabled
    if skip_existing and os.path.exists(output_path):
        print(f"Skipping existing file: {output_path}")
        return
    
    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Read content
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Clean content
        logger.info(f"Processing: {input_path}")
        cleaned_content = clean_content_with_claude(content, client)
        
        if cleaned_content:
            # Save cleaned content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
            logger.info(f"Saved cleaned file: {output_path}")
        else:
            logger.error(f"Failed to clean: {input_path}")
                
    except Exception as e:
        logger.error(f"Error processing {input_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description='Clean markdown files using Claude Haiku')
    parser.add_argument('--input', required=True, help='Input markdown file or directory path')
    parser.add_argument('--output', help='Output file path (default: parallel output_clean directory)')
    parser.add_argument('--skip-existing', action='store_true', 
                       help='Skip processing if output file already exists')
    parser.add_argument('--workers', type=int, default=4,
                       help='Number of parallel workers (default: 4)')
    
    args = parser.parse_args()
    
    # Handle both single file and directory inputs
    input_path = Path(args.input)
    if input_path.is_file():
        files_to_process = [input_path]
    else:
        files_to_process = list(input_path.rglob('*.md'))
    
    logger.info(f"Found {len(files_to_process)} files to process")
    
    # Process files in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Create a list of futures
        futures = [
            executor.submit(
                process_markdown_file,
                str(file_path),
                args.output,
                args.skip_existing
            )
            for file_path in files_to_process
        ]
        
        # Wait for all futures to complete
        for future in futures:
            try:
                future.result()  # This will raise any exceptions that occurred
            except Exception as e:
                logger.error(f"Error processing file: {e}")

if __name__ == '__main__':
    main() 