import os
import re
import tempfile
from fastapi import  File, UploadFile, HTTPException
from decouple import config
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from bs4 import BeautifulSoup
from bs4.element import Tag
import feedparser
import requests
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse


SECRET_KEY = config('SECRET_KEY')
BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')
def convert_relative_time_to_date(relative_time):
    """Convert relative time strings to UTC datetime objects"""
    try:
        # Try parsing absolute dates first
        parsed_date = parse(relative_time)
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        else:
            parsed_date = parsed_date.astimezone(timezone.utc)
        return parsed_date
    except (ValueError, OverflowError):
        pass  # Continue to relative time parsing
    
    # Handle relative time patterns
    match = re.match(
        r'(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago', 
        relative_time.lower().strip()
    )
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    unit_conversion = {
        'second': 'seconds',
        'minute': 'minutes',
        'hour': 'hours',
        'day': 'days',
        'week': 'weeks',
        'month': 'months',
        'year': 'years'
    }

    try:
        now = datetime.now(timezone.utc)
        kwargs = {unit_conversion[unit]: value}
        return now - relativedelta(**kwargs)
    except KeyError:
        return None

def upload_image_to_backblaze(file: UploadFile, bucket_name: str = BUCKET_NAME):
    # Validate the file
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed.")
    
    # Delete existing image if applicable
    
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        content = file.file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    # Authorize Backblaze account
    application_key_id = AWS_ACCESS_KEY_ID
    application_key = AWS_SECRET_ACCESS_KEY
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account("production", application_key_id, application_key)
    
    # Upload the image to Backblaze
    bucket = b2_api.get_bucket_by_name(bucket_name)
    uploaded_file = bucket.upload_local_file(local_file=temp_file_path, file_name=file.filename)
    
    # Retrieve the uploaded file URL
    image_url = b2_api.get_download_url_for_fileid(uploaded_file.id_)
    
    # Clean up the temporary file
    os.remove(temp_file_path)
    
    return image_url


def scrape_pcworld():
    base_url = "https://www.pcworld.com/news/page/{}"
    all_articles = []

    for page in range(1, 9):
        url = base_url.format(page)
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        articles_section = soup.find("div", class_="articleFeed-inner")
        if not articles_section:
            continue

        for article in articles_section.find_all("article", class_="item"):
            title = article.find("h3").get_text(strip=True) if article.find("h3") else None
            link = article.find("a", href=True)["href"] if article.find("a", href=True) else None
            image = article.find("img")["src"] if article.find("img") else None
            excerpt = article.find("span", class_="item-excerpt").get_text(strip=True) if article.find("span", class_="item-excerpt") else None

            meta = article.find("div", class_="item-meta")
            author = meta.find("span", class_="item-byline").get_text(strip=True) if meta and meta.find("span", class_="item-byline") else None
            date = meta.find("span", class_="item-date").get_text(strip=True) if meta and meta.find("span", class_="item-date") else None

            all_articles.append({
                "source": "PCWorld",
                "title": title,
                "link": link,
                "image": image,
                "excerpt": excerpt,
                "author": author,
                "date": date,
            })
    return all_articles


RSS_FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Dev.to": "https://dev.to/feed"
}


def extract_image(entry):
    """
    Extracts image URL from an RSS entry using common methods:
    media_content, enclosures, or first <img> tag in summary or content.
    """
    # Check for media content
    media = entry.get('media_content')
    if isinstance(media, list):
        for item in media:
            url = item.get('url')
            if url:
                return url

    # Check for enclosures
    enclosures = entry.get('enclosures')
    if isinstance(enclosures, list):
        for enclosure in enclosures:
            url = enclosure.get('url')
            if url:
                return url

    # Fallback: find image in HTML summary
    summary = entry.get('summary', '')
    if summary:
        soup = BeautifulSoup(summary, 'html.parser')
        img_tag = soup.find('img')
        if isinstance(img_tag, Tag):
            src = img_tag.get('src')
            if src:
                return src

    # Additional fallback: check 'content' field if available
    content = entry.get('content')
    if isinstance(content, list):
        for item in content:
            value = item.get('value', '')
            if value:
                soup = BeautifulSoup(value, 'html.parser')
                img_tag = soup.find('img')
                if isinstance(img_tag, Tag):
                    src = img_tag.get('src')
                    if src:
                        return src

    return None

def clean_excerpt(html, limit=500):
    """
    Converts HTML summary to plain text and trims it to a set length.
    """
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
    return text[:limit]

def fetch_rss_articles():
    """
    Parses all RSS feeds and returns a list of article dicts.
    """
    articles = []

    for source_name, feed_url in RSS_FEEDS.items():
        feed = feedparser.parse(feed_url)
        # print("Feeds",feed)

        for entry in feed.entries:
            article = {
                "source": source_name,
                "title": entry.get("title", "No Title"),
                "link": entry.get("link"),
                "image": extract_image(entry),
                "excerpt": clean_excerpt(entry.get("summary", "")),
                "author": entry.get("author", None),
                "date": entry.get("published", "")
            }
            articles.append(article)
            # print("Article", article)
    # print("Total articles fetched:", len(articles))

    return articles