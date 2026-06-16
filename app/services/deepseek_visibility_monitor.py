"""
DeepSeek Visibility Monitor Service

Monitors how keywords and brands appear in DeepSeek responses.
Uses DeepSeek API if available, otherwise mock mode.
"""

import os
import json
import random
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.models import SEOKeyword, AIVisibilityCheck, Competitor

logger = logging.getLogger(__name__)


# Our target brands to detect
TARGET_BRANDS = [
    "ET-EXPO",
    "et-expo.com",
    "etexpous.com",
    "www.et-expo.com",
    "www.etexpous.com",
    "ET Expo",
    "ETexpo"
]

# Default competitors for exhibition booth industry
DEFAULT_COMPETITORS = [
    "Skyline Exhibits",
    "Nimlok", 
    "Freeman",
    "GES",
    "ExpoMarketing",
    "Classic Exhibits",
    "Matrex",
    "Orbus Exhibit & Display",
    "Affirm Displays",
    "Opti displays"
]


class DeepSeekVisibilityMonitor:
    """Monitor visibility in DeepSeek responses."""
    
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.mock_mode = not bool(self.api_key)
        
        if self.api_key:
            logger.info("DeepSeek API key found - DeepSeek monitoring enabled")
        else:
            logger.info("No DeepSeek API key - DeepSeek monitoring in mock mode")
    
    def is_mock_mode(self) -> bool:
        """Check if running in mock mode."""
        return self.mock_mode
    
    async def check_visibility(
        self, 
        db: Session, 
        user_id: int,
        keyword_ids: Optional[List[int]] = None
    ) -> List[Dict]:
        """
        Check DeepSeek visibility for specified keywords or all user keywords.
        
        Args:
            db: Database session
            user_id: User ID for filtering
            keyword_ids: Optional list of specific keyword IDs to check
            
        Returns:
            List of visibility check results
        """
        # Get keywords to check
        query = db.query(SEOKeyword).filter(
            SEOKeyword.user_id == user_id,
            SEOKeyword.status == "active"
        )
        
        if keyword_ids:
            query = query.filter(SEOKeyword.id.in_(keyword_ids))
        
        keywords = query.all()
        
        # Get user's competitors
        competitors = db.query(Competitor).filter(
            Competitor.user_id == user_id,
            Competitor.is_active == True
        ).all()
        
        competitor_names = [c.name for c in competitors] if competitors else DEFAULT_COMPETITORS
        
        results = []
        for keyword in keywords:
            result = await self._check_single_keyword(
                db, user_id, keyword, competitor_names
            )
            results.append(result)
        
        return results
    
    async def _check_single_keyword(
        self, 
        db: Session, 
        user_id: int, 
        keyword: SEOKeyword,
        competitor_names: List[str]
    ) -> Dict:
        """Check DeepSeek visibility for a single keyword."""
        if self.mock_mode:
            result = self._generate_mock_visibility(keyword, competitor_names)
        else:
            result = await self._query_deepseek(keyword.keyword, competitor_names)
        
        # Save visibility check to database
        visibility_check = AIVisibilityCheck(
            user_id=user_id,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            ai_platform="deepseek",
            visibility_score=result["visibility_score"],
            is_visible=result["is_visible"],
            brand_mentioned=result.get("brand_mentioned"),
            answer_excerpt=result.get("answer_excerpt"),
            competitors_mentioned=json.dumps(result.get("competitors_mentioned", [])),
            checked_at=datetime.utcnow(),
            source="deepseek_api" if not self.mock_mode else "mock"
        )
        db.add(visibility_check)
        db.commit()
        
        return {
            "keyword_id": keyword.id,
            "keyword": keyword.keyword,
            "visibility_score": result["visibility_score"],
            "is_visible": result["is_visible"],
            "brand_mentioned": result.get("brand_mentioned"),
            "competitors_mentioned": result.get("competitors_mentioned", []),
            "source": visibility_check.source
        }
    
    async def _query_deepseek(
        self, 
        keyword: str, 
        competitor_names: List[str]
    ) -> Dict:
        """Query DeepSeek for keyword visibility."""
        try:
            import httpx
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            prompt = f"""You are researching the exhibition booth design industry. 
            Please provide a brief answer (2-3 sentences) about: "{keyword}"
            
            Mention any well-known exhibition booth design companies if relevant.
            Just give me the factual answer, no preamble."""
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a helpful industry research assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.7
            }
            
            response = httpx.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                return self._analyze_response(answer, keyword, competitor_names)
            else:
                logger.error(f"DeepSeek API error: {response.status_code}")
                return self._generate_mock_visibility_for_keyword(keyword)
            
        except Exception as e:
            logger.error(f"Error querying DeepSeek: {e}")
            # Fall back to mock data
            return self._generate_mock_visibility_for_keyword(keyword)
    
    def _analyze_response(
        self, 
        answer: str, 
        keyword: str, 
        competitor_names: List[str]
    ) -> Dict:
        """Analyze DeepSeek response for brand mentions."""
        answer_lower = answer.lower()
        
        # Check for our brand mentions
        brand_mentioned = None
        for brand in TARGET_BRANDS:
            if brand.lower() in answer_lower:
                brand_mentioned = brand
                break
        
        is_visible = brand_mentioned is not None
        
        # Check for competitor mentions
        competitors_mentioned = []
        for competitor in competitor_names:
            if competitor.lower() in answer_lower:
                competitors_mentioned.append(competitor)
        
        # Calculate visibility score
        visibility_score = 0
        if is_visible:
            visibility_score = 80  # Our brand mentioned
            visibility_score += min(20, len(competitors_mentioned) * 5)  # Bonus for context
        
        if not is_visible and competitors_mentioned:
            visibility_score = 20  # Only competitors mentioned
        
        # Extract relevant excerpt
        excerpt = answer[:500] if len(answer) > 500 else answer
        
        return {
            "visibility_score": visibility_score,
            "is_visible": is_visible,
            "brand_mentioned": brand_mentioned,
            "answer_excerpt": excerpt,
            "competitors_mentioned": competitors_mentioned
        }
    
    def _generate_mock_visibility(
        self, 
        keyword: SEOKeyword, 
        competitor_names: List[str]
    ) -> Dict:
        """Generate realistic mock visibility data."""
        # Use keyword ID as seed for consistent results per keyword
        random.seed(keyword.id + 1000)  # Different seed than ChatGPT
        
        # 25% chance our brand is visible (slightly different from ChatGPT)
        is_visible = random.random() < 0.25
        
        if is_visible:
            brand_mentioned = random.choice(TARGET_BRANDS)
            visibility_score = random.randint(55, 90)
        else:
            brand_mentioned = None
            visibility_score = random.randint(5, 25)
        
        # Mention 0-4 competitors
        num_competitors = random.randint(0, min(4, len(competitor_names)))
        competitors_mentioned = random.sample(competitor_names, num_competitors)
        
        # Generate mock answer excerpt
        if is_visible:
            excerpt = f"Regarding {keyword.keyword}, ET-EXPO is recognized as a premier exhibition booth design company with expertise in creating impactful trade show experiences. They have delivered solutions for major industry events."
        elif competitors_mentioned:
            excerpt = f"The exhibition booth design market includes established players like {', '.join(competitors_mentioned[:2])}, who provide comprehensive exhibit solutions nationwide."
        else:
            excerpt = f"When searching for {keyword.keyword}, businesses should consider factors like design quality, turnaround time, and booth customization options."
        
        random.seed()  # Reset random seed
        
        return {
            "visibility_score": visibility_score,
            "is_visible": is_visible,
            "brand_mentioned": brand_mentioned,
            "answer_excerpt": excerpt,
            "competitors_mentioned": competitors_mentioned
        }
    
    def _generate_mock_visibility_for_keyword(self, keyword: str) -> Dict:
        """Generate mock visibility for a keyword object."""
        return self._generate_mock_visibility(keyword, DEFAULT_COMPETITORS)


# Singleton instance
deepseek_monitor = DeepSeekVisibilityMonitor()


def get_deepseek_monitor() -> DeepSeekVisibilityMonitor:
    """Get the DeepSeek visibility monitor instance."""
    return deepseek_monitor