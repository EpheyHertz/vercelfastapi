from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database.database import Base
from datetime import datetime
 # assuming Base is declared in database.py

class NewsSource(Base):
    __tablename__ = 'aipc_diagnosis_newssource'  # matches Django db_table

    id = Column(Integer, primary_key=True, index=True)  # Django auto PK
    source_id = Column(String(255), nullable=True)
    name = Column(String(255), nullable=False)

    articles = relationship("NewsArticle", back_populates="source")



class NewsArticle(Base):
    __tablename__ = 'aipc_diagnosis_newsarticle'  # Django's actual table name

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("aipc_diagnosis_newssource.id", ondelete="CASCADE"), nullable=True)
    author = Column(String(255), nullable=True)
    title = Column(String(500), unique=True, nullable=False, default='No title')
    description = Column(Text, nullable=True)
    url = Column(String(1000), nullable=False)
    image_url = Column(String(1000), nullable=True)
    published_at = Column(DateTime, nullable=False)
    content = Column(Text, nullable=True)

    source = relationship("NewsSource", back_populates="articles")

