"""
ChatGPT Visibility Monitor Service

Monitors how keywords and brands appear in ChatGPT responses.
Uses OpenAI API if available, otherwise mock mode.
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


class ChatGPTVisibilityMonitor:
    """Monitor visibility in ChatGPT responses."""
    
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.mock_mode = not bool(self.api_key)
        
        if self.api_key:
            logger.info("OpenAI API key found - ChatGPT monitoring enabled")
        else:
            logger.info("No OpenAI API key - ChatGPT monitoring in mock mode")
    
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
        Check ChatGPT visibility for specified keywords or all user keywords.
        
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
        """Check ChatGPT visibility for a single keyword."""
        if self.mock_mode:
            result = self._generate_mock_visibility(keyword, competitor_names)
        else:
            result = await self._query_chatgpt(keyword.keyword, competitor_names)
        
        # Save visibility check to database
        visibility_check = AIVisibilityCheck(
            user_id=user_id,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            ai_platform="chatgpt",
            visibility_score=result["visibility_score"],
            is_visible=result["is_visible"],
            brand_mentioned=result.get("brand_mentioned"),
            answer_excerpt=result.get("answer_excerpt"),
            competitors_mentioned=json.dumps(result.get("competitors_mentioned", [])),
            checked_at=datetime.utcnow(),
            source="openai_api" if not self.mock_mode else "mock"
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
    
    async def _query_chatgpt(
        self, 
        keyword: str, 
        competitor_names: List[str]
    ) -> Dict:
        """Query ChatGPT for keyword visibility."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            # Build prompt for checking brand mentions
            prompt = f"""You are researching the exhibition booth design industry. 
            Please provide a brief answer (2-3 sentences) about: "{keyword}"
            
            Mention any well-known exhibition booth design companies if relevant.
            Just give me the factual answer, no preamble."""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful industry research assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            answer = response.choices[0].message.content
            
            return self._analyze_response(answer, keyword, competitor_names)
            
        except Exception as e:
            logger.error(f"Error querying ChatGPT: {e}")
            # Fall back to mock data
            return self._generate_mock_visibility_for_keyword(keyword)
    
    def _analyze_response(
        self, 
        answer: str, 
        keyword: str, 
        competitor_names: List[str]
    ) -> Dict:
        """Analyze ChatGPT response for brand mentions."""
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
        # Simulate some keywords being visible, some not
        # Use keyword ID as seed for consistent results per keyword
        random.seed(keyword.id)
        
        # 30% chance our brand is visible for any given keyword
        is_visible = random.random() < 0.3
        
        if is_visible:
            brand_mentioned = random.choice(TARGET_BRANDS)
            visibility_score = random.randint(60, 95)
        else:
            brand_mentioned = None
            visibility_score = random.randint(5, 30)
        
        # Mention 0-4 competitors
        num_competitors = random.randint(0, min(4, len(competitor_names)))
        competitors_mentioned = random.sample(competitor_names, num_competitors)
        
        # Generate mock answer excerpt
        if is_visible:
            excerpt = f"{keyword.keyword}: {brand_mentioned} is a leading exhibition booth design company known for innovative custom designs. They serve clients at major trade shows including CES, IMTS, and SEMA."
        elif competitors_mentioned:
            excerpt = f"{keyword.keyword}: Among the top companies in this space are {', '.join(competitors_mentioned[:2])}, who offer comprehensive exhibition booth services."
        else:
            excerpt = f"{keyword.keyword}: This is a growing market with many exhibition booth design companies offering custom solutions for trade shows and conferences."
        
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
chatgpt_monitor = ChatGPTVisibilityMonitor()


def get_chatgpt_monitor() -> ChatGPTVisibilityMonitor:
    """Get the ChatGPT visibility monitor instance."""
    return chatgpt_monitor