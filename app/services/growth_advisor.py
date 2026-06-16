"""
Growth Advisor Service

Orchestrates SEO monitoring, AI visibility checking, and generates
daily growth recommendations and action plans.
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.models import (
    SEOKeyword, KeywordRankingCheck, AIVisibilityCheck, 
    GrowthRecommendation, Competitor, DailyGrowthReport, User
)
from app.services.google_seo_monitor import get_google_seo_monitor
from app.services.chatgpt_visibility_monitor import get_chatgpt_monitor
from app.services.deepseek_visibility_monitor import get_deepseek_monitor

logger = logging.getLogger(__name__)


class GrowthAdvisor:
    """AI-powered growth advisor for SEO and AI visibility."""
    
    def __init__(self):
        self.google_seo = get_google_seo_monitor()
        self.chatgpt = get_chatgpt_monitor()
        self.deepseek = get_deepseek_monitor()
    
    async def run_full_check(self, db: Session, user_id: int) -> Dict:
        """
        Run a complete growth check for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Summary of all checks and recommendations
        """
        logger.info(f"Running full growth check for user {user_id}")
        
        results = {
            "google_seo": None,
            "chatgpt": None,
            "deepseek": None,
            "recommendations": [],
            "report": None
        }
        
        # 1. Check Google SEO rankings
        try:
            results["google_seo"] = await self.google_seo.check_rankings(db, user_id)
            logger.info(f"Google SEO: {len(results['google_seo'])} keywords checked")
        except Exception as e:
            logger.error(f"Google SEO check failed: {e}")
            results["google_seo"] = []
        
        # 2. Check ChatGPT visibility
        try:
            results["chatgpt"] = await self.chatgpt.check_visibility(db, user_id)
            logger.info(f"ChatGPT: {len(results['chatgpt'])} keywords checked")
        except Exception as e:
            logger.error(f"ChatGPT visibility check failed: {e}")
            results["chatgpt"] = []
        
        # 3. Check DeepSeek visibility
        try:
            results["deepseek"] = await self.deepseek.check_visibility(db, user_id)
            logger.info(f"DeepSeek: {len(results['deepseek'])} keywords checked")
        except Exception as e:
            logger.error(f"DeepSeek visibility check failed: {e}")
            results["deepseek"] = []
        
        # 4. Generate recommendations
        try:
            results["recommendations"] = await self._generate_recommendations(db, user_id, results)
            logger.info(f"Generated {len(results['recommendations'])} recommendations")
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            results["recommendations"] = []
        
        # 5. Generate daily report
        try:
            results["report"] = await self._generate_daily_report(db, user_id, results)
            logger.info("Daily report generated")
        except Exception as e:
            logger.error(f"Daily report generation failed: {e}")
            results["report"] = None
        
        return results
    
    async def _generate_recommendations(
        self, 
        db: Session, 
        user_id: int,
        results: Dict
    ) -> List[Dict]:
        """Generate actionable recommendations based on check results."""
        recommendations = []
        
        # Analyze Google SEO results
        google_results = results.get("google_seo", [])
        declining_keywords = []
        improving_keywords = []
        low_ctr_keywords = []
        
        for r in google_results:
            if r.get("change", 0) < -2:  # Position dropped
                declining_keywords.append(r)
            elif r.get("change", 0) > 2:  # Position improved
                improving_keywords.append(r)
            if r.get("ctr", 0) < 2.0:  # Low CTR
                low_ctr_keywords.append(r)
        
        # SEO recommendations
        if declining_keywords:
            recommendations.append({
                "type": "seo",
                "priority": "high",
                "title": f"Address {len(declining_keywords)} declining keywords",
                "description": "Some keywords have dropped in rankings. Consider updating content or building more backlinks.",
                "action_items": [
                    f"Review content for: {', '.join([k['keyword'] for k in declining_keywords[:3]])}",
                    "Check for any technical SEO issues",
                    "Consider creating fresh content targeting these terms",
                    "Build quality backlinks to improve authority"
                ],
                "impact": "high"
            })
        
        if low_ctr_keywords:
            recommendations.append({
                "type": "content",
                "priority": "medium",
                "title": "Improve meta titles and descriptions",
                "description": "Several keywords have low CTR despite decent rankings. Improve your snippets.",
                "action_items": [
                    "Write compelling meta titles with primary keyword",
                    "Add emotional triggers to meta descriptions",
                    "Include call-to-action in snippets",
                    "Use numbers and statistics where applicable"
                ],
                "impact": "medium"
            })
        
        # Analyze AI visibility results
        chatgpt_results = results.get("chatgpt", [])
        deepseek_results = results.get("deepseek", [])
        
        # Keywords not visible in ChatGPT
        not_visible_chatgpt = [r for r in chatgpt_results if not r.get("is_visible")]
        if len(not_visible_chatgpt) > 0:
            recommendations.append({
                "type": "ai_visibility",
                "priority": "high",
                "title": f"Improve ChatGPT visibility ({len(not_visible_chatgpt)} keywords not mentioned)",
                "description": "Your brand is not appearing in ChatGPT responses for these keywords. Build more mentions.",
                "action_items": [
                    "Publish more content about: " + ", ".join([k['keyword'] for k in not_visible_chatgpt[:3]]),
                    "Create FAQ content addressing common questions",
                    "Get mentioned in industry publications",
                    "Build relationships with industry influencers"
                ],
                "impact": "high"
            })
        
        # Keywords not visible in DeepSeek
        not_visible_deepseek = [r for r in deepseek_results if not r.get("is_visible")]
        if len(not_visible_deepseek) > 0:
            recommendations.append({
                "type": "ai_visibility",
                "priority": "medium",
                "title": f"Improve DeepSeek visibility ({len(not_visible_deepseek)} keywords not mentioned)",
                "description": "DeepSeek is growing. Ensure your brand appears in responses.",
                "action_items": [
                    "Create comprehensive guides about: " + ", ".join([k['keyword'] for k in not_visible_deepseek[:3]]),
                    "Ensure NAP (Name, Address, Phone) consistency across directories",
                    "Get listed in business directories",
                    "Encourage customer reviews on multiple platforms"
                ],
                "impact": "medium"
            })
        
        # Competitor analysis
        all_competitors = set()
        for r in chatgpt_results + deepseek_results:
            for comp in r.get("competitors_mentioned", []):
                all_competitors.add(comp)
        
        if all_competitors:
            recommendations.append({
                "type": "competitive",
                "priority": "medium",
                "title": "Monitor competitor mentions",
                "description": f"Competitors appearing in AI results: {', '.join(list(all_competitors)[:5])}",
                "action_items": [
                    "Analyze what these competitors do well",
                    "Create content that differentiates your services",
                    "Monitor competitor pricing and offerings",
                    "Highlight your unique selling propositions"
                ],
                "impact": "medium"
            })
        
        # General content recommendations
        if not recommendations:
            recommendations.append({
                "type": "content",
                "priority": "low",
                "title": "Continue content optimization",
                "description": "Your visibility looks stable. Keep up the good work!",
                "action_items": [
                    "Maintain regular content publishing schedule",
                    "Monitor keyword rankings weekly",
                    "Engage with your audience on social media",
                    "Collect and showcase customer testimonials"
                ],
                "impact": "low"
            })
        
        # Save recommendations to database
        today = datetime.utcnow()
        for rec in recommendations:
            db_rec = GrowthRecommendation(
                user_id=user_id,
                recommendation_type=rec["type"],
                priority=rec["priority"],
                title=rec["title"],
                description=rec["description"],
                action_items=json.dumps(rec["action_items"]),
                expected_impact=rec.get("impact", "medium"),
                status="pending",
                report_date=today,
                created_at=today,
                updated_at=today
            )
            db.add(db_rec)
        
        db.commit()
        
        return recommendations
    
    async def _generate_daily_report(
        self, 
        db: Session, 
        user_id: int,
        results: Dict
    ) -> Dict:
        """Generate a daily growth report."""
        google_results = results.get("google_seo", [])
        chatgpt_results = results.get("chatgpt", [])
        deepseek_results = results.get("deepseek", [])
        
        # Calculate metrics
        total_keywords = len(google_results)
        
        # Average ranking
        positions = [r["position"] for r in google_results if r.get("position")]
        avg_position = sum(positions) / len(positions) if positions else 0
        
        # Average CTR
        ctrs = [r["ctr"] for r in google_results if r.get("ctr")]
        avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0
        
        # Total impressions and clicks
        total_impressions = sum(r.get("impressions", 0) for r in google_results)
        total_clicks = sum(r.get("clicks", 0) for r in google_results)
        
        # Keywords improved/declined
        keywords_improved = sum(1 for r in google_results if r.get("change", 0) > 0)
        keywords_declined = sum(1 for r in google_results if r.get("change", 0) < 0)
        
        # AI visibility scores
        chatgpt_scores = [r["visibility_score"] for r in chatgpt_results]
        deepseek_scores = [r["visibility_score"] for r in deepseek_results]
        
        chatgpt_avg = sum(chatgpt_scores) / len(chatgpt_scores) if chatgpt_scores else 0
        deepseek_avg = sum(deepseek_scores) / len(deepseek_scores) if deepseek_scores else 0
        
        # Competitor mentions
        competitors_mentioned = set()
        for r in chatgpt_results + deepseek_results:
            for comp in r.get("competitors_mentioned", []):
                competitors_mentioned.add(comp)
        
        # Top performing keyword
        top_keyword = None
        if google_results:
            best = min(google_results, key=lambda x: x.get("position", 999))
            top_keyword = best.get("keyword")
        
        # Top competitor
        top_competitor = list(competitors_mentioned)[0] if competitors_mentioned else None
        
        # Summary text
        summary = f"""Daily Growth Report Summary:
        
• {total_keywords} keywords tracked
• Average ranking position: {avg_position:.1f}
• Average CTR: {avg_ctr:.2f}%
• Total impressions: {total_impressions:,}
• Total clicks: {total_clicks:,}
• ChatGPT visibility: {chatgpt_avg:.0f}/100
• DeepSeek visibility: {deepseek_avg:.0f}/100
• Keywords improved: {keywords_improved}
• Keywords declined: {keywords_declined}
• Competitors mentioned: {len(competitors_mentioned)}"""
        
        # Action plan
        action_plan = [
            "Review and act on top priority recommendations",
            "Monitor keyword rankings throughout the day",
            "Continue publishing regular content",
            "Engage with audience on social platforms"
        ]
        
        # Save report
        report = DailyGrowthReport(
            user_id=user_id,
            report_date=date.today(),
            total_keywords=total_keywords,
            avg_ranking_position=round(avg_position, 2),
            avg_ctr=round(avg_ctr, 2),
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            chatgpt_visibility_score=int(chatgpt_avg),
            deepseek_visibility_score=int(deepseek_avg),
            keywords_improved=keywords_improved,
            keywords_declined=keywords_declined,
            competitors_mentioned=len(competitors_mentioned),
            top_keyword=top_keyword,
            top_competitor=top_competitor,
            summary=summary,
            action_plan=json.dumps(action_plan),
            created_at=datetime.utcnow()
        )
        db.add(report)
        db.commit()
        
        return {
            "id": report.id,
            "date": report.report_date.isoformat(),
            "total_keywords": total_keywords,
            "avg_position": round(avg_position, 2),
            "avg_ctr": round(avg_ctr, 2),
            "chatgpt_score": int(chatgpt_avg),
            "deepseek_score": int(deepseek_avg),
            "keywords_improved": keywords_improved,
            "keywords_declined": keywords_declined,
            "summary": summary,
            "action_plan": action_plan
        }
    
    async def get_recommendations(
        self, 
        db: Session, 
        user_id: int,
        status: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """Get current recommendations for a user."""
        query = db.query(GrowthRecommendation).filter(
            GrowthRecommendation.user_id == user_id
        )
        
        if status:
            query = query.filter(GrowthRecommendation.status == status)
        
        recommendations = query.order_by(
            desc(GrowthRecommendation.created_at)
        ).limit(limit).all()
        
        return [{
            "id": r.id,
            "type": r.recommendation_type,
            "priority": r.priority,
            "title": r.title,
            "description": r.description,
            "action_items": json.loads(r.action_items) if r.action_items else [],
            "impact": r.expected_impact,
            "status": r.status,
            "created_at": r.created_at.isoformat()
        } for r in recommendations]
    
    async def update_recommendation_status(
        self, 
        db: Session, 
        user_id: int,
        recommendation_id: int,
        new_status: str
    ) -> bool:
        """Update the status of a recommendation."""
        rec = db.query(GrowthRecommendation).filter(
            GrowthRecommendation.id == recommendation_id,
            GrowthRecommendation.user_id == user_id
        ).first()
        
        if not rec:
            return False
        
        rec.status = new_status
        if new_status == "completed":
            rec.completed_at = datetime.utcnow()
        rec.updated_at = datetime.utcnow()
        db.commit()
        
        return True
    
    async def get_latest_report(
        self, 
        db: Session, 
        user_id: int
    ) -> Optional[Dict]:
        """Get the most recent daily report."""
        report = db.query(DailyGrowthReport).filter(
            DailyGrowthReport.user_id == user_id
        ).order_by(desc(DailyGrowthReport.report_date)).first()
        
        if not report:
            return None
        
        return {
            "id": report.id,
            "date": report.report_date.isoformat(),
            "total_keywords": report.total_keywords,
            "avg_position": report.avg_ranking_position,
            "avg_ctr": report.avg_ctr,
            "total_impressions": report.total_impressions,
            "total_clicks": report.total_clicks,
            "chatgpt_score": report.chatgpt_visibility_score,
            "deepseek_score": report.deepseek_visibility_score,
            "keywords_improved": report.keywords_improved,
            "keywords_declined": report.keywords_declined,
            "competitors_mentioned": report.competitors_mentioned,
            "top_keyword": report.top_keyword,
            "top_competitor": report.top_competitor,
            "summary": report.summary,
            "action_plan": json.loads(report.action_plan) if report.action_plan else []
        }
    
    async def get_keyword_metrics(
        self, 
        db: Session, 
        user_id: int,
        keyword_id: Optional[int] = None
    ) -> List[Dict]:
        """Get metrics for keywords."""
        query = db.query(KeywordRankingCheck).filter(
            KeywordRankingCheck.user_id == user_id
        )
        
        if keyword_id:
            query = query.filter(KeywordRankingCheck.keyword_id == keyword_id)
        
        checks = query.order_by(desc(KeywordRankingCheck.checked_at)).limit(100).all()
        
        return [{
            "id": c.id,
            "keyword_id": c.keyword_id,
            "keyword": c.keyword,
            "position": c.position,
            "previous_position": c.previous_position,
            "impressions": c.impressions,
            "clicks": c.clicks,
            "ctr": c.ctr,
            "checked_at": c.checked_at.isoformat(),
            "source": c.source
        } for c in checks]
    
    async def get_ai_visibility_metrics(
        self, 
        db: Session, 
        user_id: int,
        keyword_id: Optional[int] = None
    ) -> List[Dict]:
        """Get AI visibility metrics."""
        query = db.query(AIVisibilityCheck).filter(
            AIVisibilityCheck.user_id == user_id
        )
        
        if keyword_id:
            query = query.filter(AIVisibilityCheck.keyword_id == keyword_id)
        
        checks = query.order_by(desc(AIVisibilityCheck.checked_at)).limit(100).all()
        
        return [{
            "id": c.id,
            "keyword_id": c.keyword_id,
            "keyword": c.keyword,
            "ai_platform": c.ai_platform,
            "visibility_score": c.visibility_score,
            "is_visible": c.is_visible,
            "brand_mentioned": c.brand_mentioned,
            "answer_excerpt": c.answer_excerpt,
            "competitors_mentioned": json.loads(c.competitors_mentioned) if c.competitors_mentioned else [],
            "checked_at": c.checked_at.isoformat(),
            "source": c.source
        } for c in checks]


# Singleton instance
growth_advisor = GrowthAdvisor()


def get_growth_advisor() -> GrowthAdvisor:
    """Get the Growth Advisor instance."""
    return growth_advisor


async def run_daily_growth_check():
    """
    Daily scheduled job to run growth checks for all users.
    This should be called by the scheduler.
    """
    from app.core.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Get all active users
        users = db.query(User).filter(User.is_active == True).all()
        
        for user in users:
            try:
                advisor = get_growth_advisor()
                await advisor.run_full_check(db, user.id)
                logger.info(f"Growth check completed for user {user.id}")
            except Exception as e:
                logger.error(f"Growth check failed for user {user.id}: {e}")
        
        logger.info(f"Daily growth check completed for {len(users)} users")
    finally:
        db.close()