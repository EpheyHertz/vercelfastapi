
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
import requests
from decouple import config
from helper import upload_image_to_backblaze
from bs4 import BeautifulSoup
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
SECRET_KEY = config('SECRET_KEY')
app = FastAPI()

# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,  # Allow credentials (cookies, etc.)
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)



def validate_secret_key(x_secret_key: str = Header(None)):
    if x_secret_key != SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid secret key")
    return True

@app.get("/")
def read_root():
    return {"Hello": "World"}







@app.get("/scrape-newsarticles/")
async def scrape_articles():
    # Base URL of the page to scrape
    base_url = "https://www.pcworld.com/accessories/news/page/{}"

    # Initialize a list to store all articles across pages
    all_articles = []

    # Loop through the first three pages
    for page in range(1, 4):  # Pages 1 to 3
        # Format the URL for each page
        url = base_url.format(page)

        # Make a request to the website
        response = requests.get(url)
        response.raise_for_status()  # ensure we got a successful response

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'lxml')

        # Find the section containing the articles
        articles_section = soup.find("div", class_="articleFeed-inner")

        # Ensure the section was found
        if articles_section:
            # Loop through each article on the current page
            for article in articles_section.find_all("article", class_="item"):
                # Extract title
                title = article.find("h3").get_text(strip=True) if article.find("h3") else None

                # Extract URL
                link = article.find("a", href=True)["href"] if article.find("a", href=True) else None

                # Extract image URL (optional)
                image = article.find("img")["src"] if article.find("img") else None

                # Extract excerpt
                excerpt = article.find("span", class_="item-excerpt").get_text(strip=True) if article.find("span", class_="item-excerpt") else None

                # Extract author and date (within the item-meta div)
                meta = article.find("div", class_="item-meta")
                author = meta.find("span", class_="item-byline").get_text(strip=True) if meta and meta.find("span", class_="item-byline") else None
                date = meta.find("span", class_="item-date").get_text(strip=True) if meta and meta.find("span", class_="item-date") else None

                # Add the article data to the list
                all_articles.append({
                    "title": title,
                    "link": link,
                    "image": image,
                    "excerpt": excerpt,
                    "author": author,
                    "date": date,
                })

    # Return all collected articles as a JSON response
    return JSONResponse(content=all_articles)

@app.get("/scrape-pcworld-windows/")
async def scrape_pcworld_windows():
    # Base URL of the page to scrape
    base_url = "https://www.pcworld.com/windows/news/page/{}"

    # Initialize a list to store all articles across pages
    all_articles = []

    # Loop through the first three pages
    for page in range(1, 4):  # Pages 1 to 3
        # Format the URL for each page
        url = base_url.format(page)

        
        response = requests.get(url)
        response.raise_for_status()  # ensure we got a successful response

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'lxml')

        # Find the section containing the articles
        articles_section = soup.find("div", class_="articleFeed-inner")

        # Ensure the section was found
        if articles_section:
            # Loop through each article on the current page
            for article in articles_section.find_all("article", class_="item"):
                # Extract title
                title = article.find("h3").get_text(strip=True) if article.find("h3") else None

                # Extract URL
                link = article.find("a", href=True)["href"] if article.find("a", href=True) else None

                # Extract image URL (optional)
                image = article.find("img")["src"] if article.find("img") else None

                # Extract excerpt
                excerpt = article.find("span", class_="item-excerpt").get_text(strip=True) if article.find("span", class_="item-excerpt") else None

                # Extract author and date (within the item-meta div)
                meta = article.find("div", class_="item-meta")
                author = meta.find("span", class_="item-byline").get_text(strip=True) if meta and meta.find("span", class_="item-byline") else None
                date = meta.find("span", class_="item-date").get_text(strip=True) if meta and meta.find("span", class_="item-date") else None

                # Add the article data to the list
                all_articles.append({
                    "title": title,
                    "link": link,
                    "image": image,
                    "excerpt": excerpt,
                    "author": author,
                    "date": date,
                })

    # Return all collected articles as a JSON response
    return JSONResponse(content=all_articles)



@app.get("/scrape-pcworld-news/")
async def scrape_pcworld_news():
    # Base URL of the page to scrape
    base_url = "https://www.pcworld.com/news/page/{}"

    # Initialize a list to store all articles across pages
    all_articles = []

    # Loop through the first three pages
    for page in range(1, 9):  # Pages 1 to 3
        # Format the URL for each page
        url = base_url.format(page)

        
        response = requests.get(url)
        response.raise_for_status()  # ensure we got a successful response

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'lxml')

        # Find the section containing the articles
        articles_section = soup.find("div", class_="articleFeed-inner")

        # Ensure the section was found
        if articles_section:
            # Loop through each article on the current page
            for article in articles_section.find_all("article", class_="item"):
                # Extract title
                title = article.find("h3").get_text(strip=True) if article.find("h3") else None

                # Extract URL
                link = article.find("a", href=True)["href"] if article.find("a", href=True) else None

                # Extract image URL (optional)
                image = article.find("img")["src"] if article.find("img") else None

                # Extract excerpt
                excerpt = article.find("span", class_="item-excerpt").get_text(strip=True) if article.find("span", class_="item-excerpt") else None

                # Extract author and date (within the item-meta div)
                meta = article.find("div", class_="item-meta")
                author = meta.find("span", class_="item-byline").get_text(strip=True) if meta and meta.find("span", class_="item-byline") else None
                date = meta.find("span", class_="item-date").get_text(strip=True) if meta and meta.find("span", class_="item-date") else None

                # Add the article data to the list
                all_articles.append({
                    "title": title,
                    "link": link,
                    "image": image,
                    "excerpt": excerpt,
                    "author": author,
                    "date": date,
                })

    # Return all collected articles as a JSON response
    return JSONResponse(content=all_articles)

@app.post("/upload-image/")
async def upload_image(file: UploadFile = File(...)):
    try:
        image_url = upload_image_to_backblaze(file)
        return {"image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))