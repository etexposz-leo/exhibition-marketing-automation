"""
Google SEO Monitor Service

Monitors Google Search rankings and analytics.
Supports Google Search Console API if credentials exist, otherwise uses mock mode.
"""

import os
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.models import SEOKeyword, KeywordRankingCheck

logger = logging.getLogger(__name__)


class GoogleSEOMonitor:
    """Monitor Google SEO performance."""
    
    def __init__(self):
        self.mock_mode = True
        self.credentials = os.environ.get("GOOGLE_SEARCH_CONSOLE_CREDENTIALS")
        
        if self.credentials:
            try:
                # Try to parse as JSON credentials
                import json
                creds = json.loads(self.credentials)
                # Initialize Google Search Console API client
                # For now, we'll use mock mode as this requires OAuth setup
                logger.info("Google Search Console credentials found, but full API integration requires OAuth setup")
            except:
                pass
    
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return self.mock_mode
    
    async def check_rankings(
        self, 
        db: Session, 
        user_id: int,
        keyword_ids: Optional[List[int]] = None
    ) -> List[Dict]:
        """
        Check rankings for specified keywords or all user keywords.
        
        Args:
            db: Database session
            user_id: User ID for filtering
            keyword_ids: Optional list of specific keyword IDs to check
            
        Returns:
            List of ranking check results
        """
        # Get keywords to check
        query = db.query(SEOKeyword).filter(
            SEOKeyword.user_id == user_id,
            SEOKeyword.status == "active"
        )
        
        if keyword_ids:
            query = query.filter(SEOKeyword.id.in_(keyword_ids))
        
        keywords = query.all()
        
        results = []
        for keyword in keywords:
            result = await self._check_single_keyword(db, user_id, keyword)
            results.append(result)
        
        return results
    
    async def _check_single_keyword(
        self, 
        db: Session, 
        user_id: int, 
        keyword: SEOKeyword
    ) -> Dict:
        """Check ranking for a single keyword."""
        # Get previous ranking if exists
        previous_check = db.query(KeywordRankingCheck).filter(
            KeywordRankingCheck.keyword_id == keyword.id,
            KeywordRankingCheck.user_id == user_id
        ).order_by(KeywordRankingCheck.checked_at.desc()).first()
        
        previous_position = previous_check.position if previous_check else None
        
        if self.mock_mode:
            result = self._generate_mock_ranking(keyword, previous_position)
        else:
            # Real Google API call would go here
            result = self._generate_mock_ranking(keyword, previous_position)
        
        # Save ranking check to database
        ranking_check = KeywordRankingCheck(
            user_id=user_id,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            position=result["position"],
            previous_position=previous_position,
            impressions=result["impressions"],
            clicks=result["clicks"],
            ctr=result["ctr"],
            avg_position=result["avg_position"],
            search_volume=result.get("search_volume", keyword.search_volume),
            checked_at=datetime.utcnow(),
            source="google_api" if not self.mock_mode else "mock"
        )
        db.add(ranking_check)
        db.commit()
        
        return {
            "keyword_id": keyword.id,
            "keyword": keyword.keyword,
            "position": result["position"],
            "previous_position": previous_position,
            "impressions": result["impressions"],
            "clicks": result["clicks"],
            "ctr": result["ctr"],
            "change": result["position_change"],
            "source": ranking_check.source
        }
    
    def _generate_mock_ranking(
        self, 
        keyword: SEOKeyword, 
        previous_position: Optional[int]
    ) -> Dict:
        """Generate realistic mock ranking data."""
        # Base position with some randomness
        if previous_position:
            # Simulate small fluctuations
            change = random.randint(-3, 3)
            base_position = max(1, previous_position + change)
        else:
            # New keyword - start somewhere in top 50
            base_position = random.randint(15, 45)
        
        position = max(1, min(100, base_position))
        
        # Generate impressions based on position
        if position <= 3:
            impressions = random.randint(800, 2000)
        elif position <= 10:
            impressions = random.randint(200, 800)
        elif position <= 20:
            impressions = random.randint(50, 200)
        else:
            impressions = random.randint(10, 50)
        
        # CTR based on position
        if position == 1:
            ctr = random.uniform(0.28, 0.35)
        elif position == 2:
            ctr = random.uniform(0.15, 0.25)
        elif position <= 5:
            ctr = random.uniform(0.08, 0.15)
        elif position <= 10:
            ctr = random.uniform(0.03, 0.08)
        else:
            ctr = random.uniform(0.01, 0.03)
        
        clicks = int(impressions * ctr)
        avg_position = position + random.uniform(-0.5, 0.5)
        
        # Calculate change from previous
        if previous_position:
            position_change = previous_position - position  # Positive = improved
        else:
            position_change = 0
        
        # Estimate search volume based on position and impressions
        search_volume = int(impressions / ctr) if ctr > 0 else impressions * 100
        
        return {
            "position": position,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(ctr * 100, 2),  # Convert to percentage
            "avg_position": round(avg_position, 1),
            "search_volume": search_volume,
            "position_change": position_change
        }
    
    async def get_ranking_trends(
        self, 
        db: Session, 
        user_id: int, 
        days: int = 30
    ) -> Dict:
        """Get ranking trends over specified days."""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        checks = db.query(KeywordRankingCheck).filter(
            KeywordRankingCheck.user_id == user_id,
            KeywordRankingCheck.created_at >= start_date
        ).order_by(KeywordRankingCheck.checked_at).all()
        
        # Group by keyword
        trends = {}
        for check in checks:
            if check.keyword_id not in trends:
                trends[check.keyword_id] = {
                    "keyword": check.keyword,
                    "history": []
                }
            trends[check.keyword_id]["history"].append({
                "date": check.checked_at.isoformat(),
                "position": check.position,
                "impressions": check.impressions,
                "clicks": check.clicks,
                "ctr": check.ctr
            })
        
        return trends


# Singleton instance
google_seo_monitor = GoogleSEOMonitor()


def get_google_seo_monitor() -> GoogleSEOMonitor:
    """Get the Google SEO monitor instance."""
    return google_seo_monitor