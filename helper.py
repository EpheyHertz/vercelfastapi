import os
import tempfile
from fastapi import  File, UploadFile, HTTPException
from decouple import config
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from bs4 import BeautifulSoup
import feedparser
import requests


SECRET_KEY = config('SECRET_KEY')
BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME')

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
                "image_url": image,
                "excerpt": excerpt,
                "author": author,
                "published": date,
            })
    return all_articles


RSS_FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Reuters": "http://feeds.reuters.com/reuters/topNews",
    "Hacker News": "https://hnrss.org/newest",
    "Dev.to": "https://dev.to/feed"
}

def extract_image(entry):
    """
    Extracts image URL from an RSS entry using common methods:
    media_content, enclosures, or first <img> tag in summary.
    """
    # Check for media content
    media = entry.get('media_content')
    if media and isinstance(media, list) and media[0].get('url'):
        return media[0]['url']

    # Check for enclosure
    enclosures = entry.get('enclosures')
    if enclosures and isinstance(enclosures, list) and enclosures[0].get('url'):
        return enclosures[0]['url']

    # Fallback: find image in HTML summary
    summary = entry.get('summary', '')
    soup = BeautifulSoup(summary, 'html.parser')
    img_tag = soup.find('img')
    from bs4.element import Tag
    if isinstance(img_tag, Tag):
        src = img_tag.get('src')
        if src:
            return src

    return None

def clean_excerpt(html, limit=300):
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
                "image_url": extract_image(entry),
                "excerpt": clean_excerpt(entry.get("summary", "")),
                "author": entry.get("author", None),
                "published": entry.get("published", "")
            }
            articles.append(article)

    return articles