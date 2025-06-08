from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from ..database.database import get_db
from ..models import NewsSource, NewsArticle
from contextlib import asynccontextmanager
from sqlalchemy.exc import IntegrityError
import logging
from ..helper import scrape_pcworld, fetch_rss_articles, convert_relative_time_to_date
import re
from typing import Optional

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global variable to track executions
NEWS_EXECUTION_STATS = {
    "last_run": None,
    "total_runs": 0,
    "total_articles_fetched": 0,
    "total_articles_saved": 0,
    "total_articles_deleted": 0,
    "last_error": None
}

# Create the router
router = APIRouter(
    prefix="/news-workflows",
    tags=["News Automation"],
    responses={404: {"description": "Not found"}}
)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app:FastAPI):
    # Start scheduler on app startup
    if not scheduler.running:
        scheduler.start()
        logger.info("News Scheduler started at: %s", datetime.now())
    
    # Add main news job (runs hourly)
    news_job = scheduler.add_job(
        news_scraping_job_wrapper,
        IntervalTrigger(hours=1),
        id="news_scraping_hourly",
        replace_existing=True
    )
    
    logger.info("News scraping job scheduled. Next run: %s", news_job.next_run_time)
    
    yield
    
    # Cleanup on shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("News Scheduler stopped at: %s", datetime.now())

async def news_scraping_job_wrapper():
    """Wrapper for the news scraping job with proper error handling"""
    start_time = datetime.now()
    NEWS_EXECUTION_STATS["last_run"] = start_time
    NEWS_EXECUTION_STATS["total_runs"] += 1
    
    try:
        async with get_db() as db:
            # First clean old articles
            delete_result = clean_old_articles(db)
            NEWS_EXECUTION_STATS["total_articles_deleted"] += delete_result["deleted"]
            
            # Then fetch and store new articles
            fetch_result = await fetch_and_store_news(db)
            NEWS_EXECUTION_STATS["total_articles_fetched"] += fetch_result["fetched"]
            NEWS_EXECUTION_STATS["total_articles_saved"] += fetch_result["saved"]
            
            logger.info(
                "News job completed in %.2f seconds: %d fetched, %d saved, %d deleted",
                (datetime.now() - start_time).total_seconds(),
                fetch_result["fetched"],
                fetch_result["saved"],
                delete_result["deleted"]
            )
            
    except Exception as e:
        error_msg = f"News job failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        NEWS_EXECUTION_STATS["last_error"] = error_msg
        raise  # Re-raise to let APScheduler handle retries

def clean_old_articles(db: Session, days: int = 7) -> dict:
    """Delete articles older than specified days"""
    cutoff_date = datetime.now() - timedelta(days=days)

    stmt = delete(NewsArticle).where(NewsArticle.published_at < cutoff_date)
    result = db.execute(stmt)
    db.commit()

    deleted_count = result.rowcount if result and hasattr(result, "rowcount") else 0

    logger.info("Deleted %d articles older than %s", deleted_count, cutoff_date)

    return {
        "deleted": deleted_count,
        "cutoff_date": cutoff_date.isoformat(),
        "timestamp": datetime.now().isoformat()
    }


async def fetch_and_store_news(db: Session) -> dict:
    """Main news fetching and storage logic"""
    pcworld_articles = scrape_pcworld()
    rss_articles = fetch_rss_articles()
    all_articles = pcworld_articles + rss_articles

    if not all_articles:
        logger.info("No new articles found in this run")
        return {"fetched": 0, "saved": 0}

    saved_count = 0

    for article in all_articles:
        try:
            # Check for duplicate by title before saving
            existing_article = db.execute(
                select(NewsArticle).where(NewsArticle.title == article["title"])
            ).scalar_one_or_none()

            if existing_article:
                logger.info(f"Duplicate found, skipping: {article['title']}")
                continue

            saved = await process_single_article(db, article)
            if saved:
                saved_count += 1

        except IntegrityError as ie:
            db.rollback()
            logger.warning(f"IntegrityError (possibly duplicate): {article['title']} — {ie}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process article '{article.get('title')}': {str(e)}")

    db.commit()

    return {
        "fetched": len(all_articles),
        "saved": saved_count,
        "timestamp": datetime.now().isoformat()
    }

async def process_single_article(db:Session, article: dict) -> bool:
    """Process and save a single article with proper validation"""
    # Validate required fields
    if not article.get("title") or not article.get("link"):
        logger.warning("Skipping article missing title or URL")
        return False
    
    # Check for existing article
    existing = db.execute(
        select(NewsArticle).where(NewsArticle.title == article["title"])
    )
    if existing.scalar_one_or_none():
        return False  # Already exists
    
    # Handle source
    source_name = article.get("source", "Unknown")
    source =  db.execute(
        select(NewsSource).where(NewsSource.name == source_name)
    )
    source = source.scalar_one_or_none()
    
    if not source:
        source = NewsSource(name=source_name)
        db.add(source)
        db.commit()
        db.refresh(source)
    
    # Parse date
    published_at = None
    if article.get("date"):
        published_at = convert_relative_time_to_date(article["date"])
    
    # Create article
    new_article = NewsArticle(
        source=article.get("source", 'Unknown'),
        author=article.get("author"),
        title=article["title"],
        description=article.get("excerpt"),
        url=article["link"],
        image_url=article.get("image"),
        published_at=published_at or datetime.now(),
        content=article.get("content", "")
    )
    
    db.add(new_article)
    return True

@router.get("/stats")
async def get_news_stats():
    """Get current scheduler statistics"""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "function": job.func.__name__
        })
    
    return {
        "scheduler_running": scheduler.running,
        "jobs": jobs,
        "stats": NEWS_EXECUTION_STATS,
        "current_time": datetime.now().isoformat()
    }
# def setup_scheduler(app: FastAPI):
#     # Attach the lifespan to the app
#     app.lifespan = lifespan
    
#     # Include the router in the app
#     app.include_router(router)
    
#     logger.info("Scheduler setup completed for the application")
#     return app

@router.post("/trigger-scraping")
async def trigger_scraping(
    clean_first: bool = True,
    days_to_keep: Optional[int] = 7,
    db: Session = Depends(get_db)
):
    """Manually trigger the news scraping job"""
    try:
        start_time = datetime.now()
        
        if clean_first:
             clean_old_articles(db, days=days_to_keep)
        
        result = await fetch_and_store_news(db)
        
        return {
            "status": "success",
            "time_elapsed": str(datetime.now() - start_time),
            "result": result
        }
    except Exception as e:
        logger.error("Manual scraping failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))