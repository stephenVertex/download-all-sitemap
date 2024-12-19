# Download all sitemap

This program iterates over a sitemap.xml file and downloads all of the pages in the sitemap as markdown.

## Setup

1. Create a Python virtual environment:
```bash
python3 -m venv .venv
```

2. Activate the virtual environment:
```bash
# On Linux/Mac:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set your RapidAPI key:
```bash
# On Linux/Mac:
export RAPID_API_KEY='your-api-key'

# On Windows:
set RAPID_API_KEY=your-api-key
```

## Usage

```bash
python download_sitemap.py --sitemap_url https://www.example.com/sitemap.xml
```

You can also pass the API key directly:
```bash
python download_sitemap.py --sitemap_url https://www.example.com/sitemap.xml --api_key your-api-key
```


Typical usage:
```bash
python3 download_sitemap.py \
  --sitemap_url https://cloudfix.com/sitemap.xml \
  --limit 20 \
  --filter blog \
  --parser article-extractor2
```

TODO - Use Claude Haiku to do some cleanup on the .md to remove leftover HTML tags


## Output

The script will create a directory structure under `output/${DOMAIN}/` containing all the downloaded pages as markdown files.



