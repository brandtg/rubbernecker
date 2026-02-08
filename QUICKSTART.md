<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Quick Start Guide

Welcome to Rubbernecker! This guide will get you up and running in minutes with a basic web scraping workflow.

## What You'll Do

1. Install dependencies
2. Create a URL list to crawl
3. Crawl web pages and save HTML
4. Parse structured data from the HTML
5. View the results

## Prerequisites

Before starting, make sure you have:

- **Python 3.12+**
- **Google Chrome** installed (see [README.md](../README.md) for platform-specific install commands)

## Step-by-Step Tutorial

### 1. Install Dependencies

Run the setup command:

```bash
make install
```

This will install all required packages including SeleniumBase, avrokit, and other dependencies using Poetry.

### 2. Create Your First URL List

Create a file with URLs you want to scrape:

```bash
mkdir -p tmp
cat > tmp/requests.txt << EOF
https://news.ycombinator.com/
https://news.ycombinator.com/?p=2
EOF
```

**Tip:** You can add as many URLs as you like, one per line. Rubbernecker supports crawling any public web page.

### 3. Crawl the URLs

Run Rubbernecker to crawl your URLs and save the raw HTML:

```bash
poetry run rubbernecker crawl tmp/requests.txt tmp/output-raw.avro
```

You'll see output like:

```
INFO:Mapping tmp/requests.txt to tmp/output-raw.avro
INFO:Crawling URL: https://news.ycombinator.com/ (depth=0, retries=0)
INFO:Crawling URL: https://news.ycombinator.com/?p=2 (depth=0, retries=0)
INFO:CrawlToolStats(count_input=2, count_output=2, count_error=0) (done)
```

**What happened:**

- Rubbernecker started Chrome in headless mode
- Opened each URL in the browser
- Grabbed the complete HTML source
- Saved it to `tmp/output-raw.avro` with timestamps and metadata

### 4. Parse the Data

Extract structured information from the raw HTML:

```bash
poetry run rubbernecker parse rubbernecker.parse.standard.StandardPageParser \
    tmp/output-raw.avro tmp/output-parsed.avro
```

This uses the built-in `StandardPageParser` to extract:

- Page titles
- Headers (H1-H6)
- Links (with text and URLs)
- Body text content

### 5. View Your Results

See what you scraped by converting the Avro file to JSON:

```bash
poetry run avrokit tojson tmp/output-parsed.avro | head -50
```

You'll see JSON output like:

```json
{
  "url": "https://news.ycombinator.com/",
  "timestamp": 1707830400000,
  "title": "Hacker News",
  "content_length": 45231,
  "body_text": "...",
  "headers": [...],
  "links": [...]
}
```

**Pretty print with jq (optional):**

```bash
poetry run avrokit tojson tmp/output-parsed.avro | jq '.'
```

## What Next?

### Run in Headless Mode

By default, Rubbernecker runs with a visible Chrome window so you can supervise the crawl. For automated/background crawling, enable headless mode:

```bash
poetry run rubbernecker crawl tmp/requests.txt tmp/output-raw.avro --headless
```

### Follow Links Automatically

Crawl deeper by following links (depth-based crawling):

```bash
# Follow links up to 2 levels deep
poetry run rubbernecker crawl tmp/requests.txt tmp/output-raw.avro --max_depth 2
```

**Warning:** This can generate a lot of requests. Start with `--max_depth 1` to test.

### Add Page Interactions

Automate actions like scrolling, clicking, or form filling. Create an actions file:

```bash
cat > tmp/actions.txt << EOF
[news\.ycombinator\.com]
SLEEP 2
SCROLL 500
SLEEP 1
EOF
```

Then use it during crawling:

```bash
poetry run rubbernecker crawl tmp/requests.txt tmp/output-raw.avro \
    --load_actions tmp/actions.txt
```

## Troubleshooting

### "Chrome connection refused" errors

- Rubbernecker automatically starts Chrome, but if you see this error, another process may be using port 9222
- Check if port 9222 is in use: `lsof -i :9222`
- Try a different port: `poetry run rubbernecker crawl tmp/requests.txt tmp/output-raw.avro --chrome_debug_port 9223`

### Empty or corrupted output

- URLs might be blocked or require JavaScript
- Try increasing wait time: add `SLEEP 3` to your actions file
- Check if the page loads correctly in your browser

### Permission errors

- Ensure the `tmp/` directory exists and is writable
- Run with proper user permissions

## Quick Reference

| Command                                      | Purpose                  |
| -------------------------------------------- | ------------------------ |
| `rubbernecker crawl input.txt output.avro`         | Crawl URLs and save HTML |
| `rubbernecker parse PARSER input.avro output.avro` | Extract structured data  |
| `avrokit tojson file.avro`                   | View Avro file as JSON   |

## Learn More

- Full command reference: [README.md](../README.md)
- Advanced usage (proxies, custom parsers, action scripts): [README.md](../README.md#advanced-usage)
- Available parsers and output formats: [README.md](../README.md#output-formats)
