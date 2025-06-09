from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, FastAPI, HTTPException,BackgroundTasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from ..database.database import get_db,SessionLocal
from ..models import NewsSource, NewsArticle
from contextlib import asynccontextmanager
from sqlalchemy.exc import IntegrityError
import logging
from ..helper import scrape_pcworld, fetch_rss_articles, convert_relative_time_to_date
import re
from typing import Optional
import logging
import asyncio

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
            link = article.get("link")
            if not link:
                logger.warning("Skipping article with missing URL: %s", article)
                continue

            # Check for duplicate by URL
            existing_article = db.execute(
                select(NewsArticle).where(NewsArticle.url == link)
            ).scalar_one_or_none()

            if existing_article:
                logger.info("Duplicate found by URL, skipping: %s", link)
                continue

            saved = await process_single_article(db, article)
            if saved:
                saved_count += 1

        except IntegrityError as ie:
            db.rollback()
            logger.warning(f"IntegrityError (possibly duplicate): {article.get('link')} — {ie}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process article '{article.get('link')}': {str(e)}")

    db.commit()

    return {
        "fetched": len(all_articles),
        "saved": saved_count,
        "timestamp": datetime.now().isoformat()
    }


async def process_single_article(db: Session, article: dict) -> bool:
    """Process and save a single article with proper validation"""
    link = article.get("link")
    title = article.get("title")

    if not link or not title:
        logger.warning("Skipping article missing link or title")
        return False

    # Double-check for duplicate by URL
    existing = db.execute(
        select(NewsArticle).where(NewsArticle.url == link)
    ).scalar_one_or_none()
    if existing:
        return False

    source_name = article.get("source", "Unknown")

    # Parse published date if available
    published_at = None
    if article.get("date"):
        published_at = convert_relative_time_to_date(article["date"])

    # Create and add new article
    new_article = NewsArticle(
        source=source_name,
        author=article.get("author"),
        title=title,
        description=article.get("excerpt") or article.get("description"),
        url=link,
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





def run_scraping_task(clean_first: bool, days_to_keep: int = 7):
    """Run scraping logic synchronously within a background task"""
    try:
        with SessionLocal() as db:
            if clean_first:
                clean_old_articles(db, days=days_to_keep)
            asyncio.run(fetch_and_store_news(db))
            logger.info("Scraping completed successfully")
    except Exception as e:
        logger.error(f"Background scraping failed: {str(e)}", exc_info=True)

@router.post("/trigger-scraping")
async def trigger_scraping(
    background_tasks: BackgroundTasks,
    clean_first: bool = True,
    days_to_keep: Optional[int] = 7
):
    """Trigger news scraping in the background (non-blocking)"""
    background_tasks.add_task(run_scraping_task, clean_first, days_to_keep)
    return {
        "status": "started",
        "message": "Scraping is running in the background. Check logs or DB for updates."
    }
