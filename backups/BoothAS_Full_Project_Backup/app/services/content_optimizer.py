"""
Platform-Specific Content Optimizer

Automatically adapts content for each social media platform's requirements.
"""

import re
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class OptimizationResult:
    """Result of content optimization for a platform."""
    original: str
    optimized: str
    platform: str
    changes: List[str]
    warnings: List[str]
    character_count: int
    character_limit: int


class ContentOptimizer:
    """
    Optimizes content for specific social media platforms.
    
    Each platform has different requirements:
    - X: 280 char limit, short/punchy style
    - LinkedIn: 3000 char, professional B2B style
    - Instagram: 2200 char, visual-focused with hashtags
    - Facebook: 63206 char, versatile marketing style
    - Google Business: 1500 char, local business promotion
    """
    
    # Platform configurations
    PLATFORM_LIMITS = {
        "x": 280,
        "linkedin": 3000,
        "instagram": 2200,
        "facebook": 63206,
        "google_business": 1500
    }
    
    # Style templates for each platform
    STYLE_TEMPLATES = {
        "x": {
            "max_length": 280,
            "prefix": "",
            "suffix": "",
            "hashtag_limit": 3,
            "emoji_limit": 2,
            "style": "short_punchy"
        },
        "linkedin": {
            "max_length": 3000,
            "prefix": "",
            "suffix": "",
            "hashtag_limit": 5,
            "emoji_limit": 5,
            "style": "professional_b2b"
        },
        "instagram": {
            "max_length": 2200,
            "prefix": "",
            "suffix": "",
            "hashtag_limit": 30,
            "emoji_limit": 10,
            "style": "visual_engaging"
        },
        "facebook": {
            "max_length": 63206,
            "prefix": "",
            "suffix": "",
            "hashtag_limit": 3,
            "emoji_limit": 8,
            "style": "general_marketing"
        },
        "google_business": {
            "max_length": 1500,
            "prefix": "",
            "suffix": "",
            "hashtag_limit": 0,
            "emoji_limit": 5,
            "style": "local_business"
        }
    }
    
    def __init__(self):
        self.industry_keywords = {
            "technology": ["innovation", "digital transformation", "cutting-edge", "tech solutions"],
            "healthcare": ["patient care", "wellness", "medical innovation", "health solutions"],
            "manufacturing": ["quality", "efficiency", "precision engineering", "production"],
            "retail": ["customer experience", "shopping", "products", "deals"],
            "finance": ["financial services", "investment", "growth", "solutions"],
            "automotive": ["mobility", "driving", "vehicles", "performance"],
            "education": ["learning", "education", "students", "knowledge"],
            "real_estate": ["property", "homes", "spaces", "living"],
            "food_beverage": ["food", "culinary", "taste", "quality ingredients"],
            "fashion": ["style", "fashion", "trends", "design"]
        }
    
    def optimize(self, content: str, platform: str, industry: str = "") -> OptimizationResult:
        """
        Optimize content for a specific platform.
        
        Args:
            content: Original content to optimize
            platform: Target platform (x, linkedin, instagram, facebook, google_business)
            industry: Customer industry for context-aware optimization
            
        Returns:
            OptimizationResult with optimized content and metadata
        """
        if platform not in self.PLATFORM_LIMITS:
            raise ValueError(f"Unknown platform: {platform}")
        
        changes = []
        warnings = []
        optimized = content
        limit = self.PLATFORM_LIMITS[platform]
        
        # Platform-specific optimizations
        if platform == "x":
            optimized, c, w = self._optimize_for_x(optimized, industry)
            changes.extend(c)
            warnings.extend(w)
        elif platform == "linkedin":
            optimized, c, w = self._optimize_for_linkedin(optimized, industry)
            changes.extend(c)
            warnings.extend(w)
        elif platform == "instagram":
            optimized, c, w = self._optimize_for_instagram(optimized, industry)
            changes.extend(c)
            warnings.extend(w)
        elif platform == "facebook":
            optimized, c, w = self._optimize_for_facebook(optimized, industry)
            changes.extend(c)
            warnings.extend(w)
        elif platform == "google_business":
            optimized, c, w = self._optimize_for_google_business(optimized, industry)
            changes.extend(c)
            warnings.extend(w)
        
        # Truncate if still over limit
        if len(optimized) > limit:
            warnings.append(f"Content truncated to fit {limit} character limit")
            optimized = optimized[:limit-3] + "..."
        
        return OptimizationResult(
            original=content,
            optimized=optimized,
            platform=platform,
            changes=changes,
            warnings=warnings,
            character_count=len(optimized),
            character_limit=limit
        )
    
    def _optimize_for_x(self, content: str, industry: str) -> tuple:
        """Optimize content for X (Twitter) - short and punchy."""
        changes = []
        warnings = []
        optimized = content.strip()
        
        # X style: short, punchy, call to action
        if len(optimized) > 280:
            # Condense to key message
            sentences = optimized.split('. ')
            condensed = sentences[0]
            if len(condensed) > 280:
                condensed = condensed[:277] + "..."
            optimized = condensed
            changes.append("Condensed for 280 character limit")
        
        # Add trending hashtag if not present
        if not any(c == '#' for c in optimized):
            industry_tag = self._get_industry_tag(industry)
            if industry_tag:
                optimized = f"{optimized}\n\n#{industry_tag}"
                changes.append("Added industry hashtag")
        
        # Ensure punchy ending
        if not optimized.endswith(('!', '?', '.', '...')):
            optimized = optimized.rstrip() + '!'
        
        return optimized, changes, warnings
    
    def _optimize_for_linkedin(self, content: str, industry: str) -> tuple:
        """Optimize content for LinkedIn - professional B2B style."""
        changes = []
        warnings = []
        optimized = content.strip()
        
        # LinkedIn style: professional, insightful, engaging
        # Add professional opener if missing
        openers = ["Excited to share", "Proud to announce", "Thrilled to present", "Delighted to share"]
        has_opener = any(opener.lower() in optimized.lower() for opener in openers)
        
        if not has_opener:
            optimized = f"✨ {openers[0]}:\n\n{optimized}"
            changes.append("Added professional opener")
        
        # Add relevant hashtags
        hashtags = self._generate_professional_hashtags(industry)
        if hashtags:
            optimized = f"{optimized}\n\n{hashtags}"
            changes.append("Added professional hashtags")
        
        # Add call to action
        if "visit" not in optimized.lower() and "see you" not in optimized.lower():
            optimized = f"{optimized}\n\n👉 Visit us at the exhibition to learn more!"
            changes.append("Added call to action")
        
        return optimized, changes, warnings
    
    def _optimize_for_instagram(self, content: str, industry: str) -> tuple:
        """Optimize content for Instagram - visual and engaging with hashtags."""
        changes = []
        warnings = []
        optimized = content.strip()
        
        # Instagram style: visual, engaging, hashtag-heavy
        # Make it more conversational
        if not any(emoji in optimized for emoji in ['✨', '🎉', '🚀', '💡', '📸']):
            optimized = f"✨ {optimized}"
            changes.append("Added visual opener")
        
        # Generate industry-specific hashtags
        hashtags = self._generate_instagram_hashtags(industry)
        optimized = f"{optimized}\n\n{hashtags}"
        changes.append("Added Instagram hashtags")
        
        # Add engagement prompt
        if "like" not in optimized.lower() and "comment" not in optimized.lower():
            optimized = f"{optimized}\n\n💬 Drop a comment below!"
            changes.append("Added engagement prompt")
        
        return optimized, changes, warnings
    
    def _optimize_for_facebook(self, content: str, industry: str) -> tuple:
        """Optimize content for Facebook - general marketing style."""
        changes = []
        warnings = []
        optimized = content.strip()
        
        # Facebook style: conversational, community-focused
        # Add friendly opener
        friendly_openers = ["Hey everyone!", "Great news!", "We're excited to share"]
        has_friendly = any(opener.lower() in optimized.lower() for opener in friendly_openers)
        
        if not has_friendly:
            optimized = f"🎉 {friendly_openers[1]}:\n\n{optimized}"
            changes.append("Added friendly opener")
        
        # Add moderate hashtags
        hashtags = self._generate_facebook_hashtags(industry)
        if hashtags:
            optimized = f"{optimized}\n\n{hashtags}"
            changes.append("Added Facebook hashtags")
        
        # Add community engagement
        if "share" not in optimized.lower():
            optimized = f"{optimized}\n\n🔄 Share with friends who might be interested!"
            changes.append("Added share prompt")
        
        return optimized, changes, warnings
    
    def _optimize_for_google_business(self, content: str, industry: str) -> tuple:
        """Optimize content for Google Business - local business promotion."""
        changes = []
        warnings = []
        optimized = content.strip()
        
        # Google Business style: local, SEO-friendly, clear offering
        # Make it concise and local-focused
        if len(optimized) > 1500:
            # Keep essential info
            sentences = optimized.split('. ')
            essential = '. '.join(sentences[:3])
            if len(essential) > 1500:
                essential = essential[:1497] + "..."
            optimized = essential
            changes.append("Condensed for Google Business limit")
        
        # Add local/SEO elements
        if not any(word in optimized.lower() for word in ['visit', 'see', 'discover', 'explore']):
            optimized = f"{optimized}\n\n📍 Visit our booth to learn more!"
            changes.append("Added visit prompt")
        
        # Add keywords
        industry_keywords = self.industry_keywords.get(industry.lower(), [])
        if industry_keywords:
            # Keep it natural, just ensure industry relevance
            pass
        
        return optimized, changes, warnings
    
    def _get_industry_tag(self, industry: str) -> str:
        """Get a hashtag for the industry."""
        tags = {
            "technology": "TechExpo",
            "healthcare": "HealthTech",
            "manufacturing": "Manufacturing",
            "retail": "RetailExpo",
            "finance": "FinTech",
            "automotive": "AutoShow",
            "education": "EdTech",
            "real estate": "PropTech",
            "food & beverage": "FoodExpo",
            "fashion": "FashionWeek"
        }
        return tags.get(industry.lower(), "")
    
    def _generate_professional_hashtags(self, industry: str) -> str:
        """Generate professional LinkedIn hashtags."""
        base_tags = ["#Business", "#Exhibition", "#Networking"]
        industry_map = {
            "technology": ["#Technology", "#Innovation", "#Digital"],
            "healthcare": ["#Healthcare", "#Medical", "#Wellness"],
            "manufacturing": ["#Manufacturing", "#Engineering", "#Industry"],
            "retail": ["#Retail", "#ConsumerGoods", "#Shopping"],
            "finance": ["#Finance", "#Banking", "#Investment"],
            "automotive": ["#Automotive", "#Mobility", "#Vehicles"],
            "education": ["#Education", "#Learning", "#Students"],
            "real estate": ["#RealEstate", "#Property", "#Development"],
            "food & beverage": ["#FoodIndustry", "#Beverage", "#Culinary"],
            "fashion": ["#Fashion", "#Design", "#Style"]
        }
        industry_tags = industry_map.get(industry.lower(), ["#Business"])
        return " ".join(base_tags[:2] + industry_tags[:3])
    
    def _generate_instagram_hashtags(self, industry: str) -> str:
        """Generate Instagram hashtags."""
        industry_tags = {
            "technology": ["#Tech", "#Technology", "#Innovation", "#Digital", "#Startup", "#Coding", 
                          "#TechExpo", "#Gadgets", "#Software", "#AI", "#FutureTech", "#TechTrends"],
            "healthcare": ["#Healthcare", "#Medical", "#Wellness", "#HealthTech", "#Doctor", "#Hospital",
                          "#Medicine", "#PatientCare", "#Health", "#MedicalExpo"],
            "manufacturing": ["#Manufacturing", "#Engineering", "#Industrial", "#Production", "#Machinery",
                            "#Factory", "#Metalworking", "#Industry40", "#SmartManufacturing"],
            "retail": ["#Retail", "#Shopping", "#Store", "#Consumer", "#Ecommerce", "#RetailTherapy",
                      "#ShoppingSpree", "#FashionRetail", "#RetailBusiness"],
            "finance": ["#Finance", "#Banking", "#Investment", "#Financial", "#Money", "#Wealth",
                       "#FinTech", "#StockMarket", "#Trading", "#FinanceExpo"],
            "automotive": ["#Automotive", "#Cars", "#Driving", "#Vehicle", "#AutoShow", "#CarLife",
                          "#AutomotiveIndustry", "#Motorsport", "#CarEnthusiast"],
            "education": ["#Education", "#Learning", "#School", "#Students", "#Teacher", "#Study",
                         "#Knowledge", "#EdTech", "#OnlineLearning", "#EducationMatters"],
            "real estate": ["#RealEstate", "#Property", "#Home", "#Housing", "#Realtor", "#LuxuryHomes",
                           "#Investment", "#CommercialProperty", "#PropertyManagement"],
            "food & beverage": ["#Food", "#Foodie", "#Restaurant", "#Cooking", "#Yummy", "#Delicious",
                               "#FoodPorn", "#Chef", "#Cuisine", "#Gourmet"],
            "fashion": ["#Fashion", "#Style", "#Clothing", "#Designer", "#OOTD", "#FashionWeek",
                       "#StreetStyle", "#LuxuryFashion", "#FashionBlogger"]
        }
        tags = industry_tags.get(industry.lower(), ["#Exhibition", "#Event", "#Expo"])
        return " ".join(tags[:10])
    
    def _generate_facebook_hashtags(self, industry: str) -> str:
        """Generate Facebook hashtags (fewer than Instagram)."""
        tags = {
            "technology": "#Tech #Innovation #Exhibition",
            "healthcare": "#Healthcare #Medical #Exhibition",
            "manufacturing": "#Manufacturing #Industry #Exhibition",
            "retail": "#Retail #Shopping #Exhibition",
            "finance": "#Finance #Business #Exhibition",
            "automotive": "#Automotive #Cars #Exhibition",
            "education": "#Education #Learning #Exhibition",
            "real estate": "#RealEstate #Property #Exhibition",
            "food & beverage": "#Food #Beverage #Exhibition",
            "fashion": "#Fashion #Style #Exhibition"
        }
        return tags.get(industry.lower(), "#Exhibition #Event #Business")
    
    def optimize_batch(self, content: str, platforms: List[str], industry: str = "") -> Dict[str, OptimizationResult]:
        """Optimize content for multiple platforms."""
        results = {}
        for platform in platforms:
            try:
                results[platform] = self.optimize(content, platform, industry)
            except ValueError as e:
                # Skip invalid platforms
                continue
        return results


# Global optimizer instance
content_optimizer = ContentOptimizer()