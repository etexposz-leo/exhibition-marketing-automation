import os
from typing import Optional
from openai import AsyncOpenAI
import httpx


class AIService:
    """Service for AI content generation using OpenAI or DeepSeek API."""
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.openai_client: Optional[AsyncOpenAI] = None
        self.deepseek_client: Optional[AsyncOpenAI] = None
        
    async def _get_openai_client(self) -> AsyncOpenAI:
        if self.openai_client is None:
            self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        return self.openai_client
    
    async def _get_deepseek_client(self) -> AsyncOpenAI:
        if self.deepseek_client is None:
            self.deepseek_client = AsyncOpenAI(
                api_key=self.deepseek_api_key,
                base_url="https://api.deepseek.com"
            )
        return self.deepseek_client
    
    async def generate_content(
        self,
        prompt: str,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        temperature: float = 0.8,
        max_tokens: int = 1000
    ) -> str:
        """
        Generate content using the specified AI provider.
        
        Args:
            prompt: The prompt for content generation
            provider: "openai" or "deepseek"
            model: Model to use
            temperature: Creativity level (0-2)
            max_tokens: Maximum tokens in response
            
        Returns:
            Generated content string
        """
        if provider == "deepseek" and self.deepseek_api_key:
            client = await self._get_deepseek_client()
            model = "deepseek-chat"
        elif self.openai_api_key:
            client = await self._get_openai_client()
        else:
            raise ValueError("No API key available. Set OPENAI_API_KEY or DEEPSEEK_API_KEY")
        
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert marketing copywriter specializing in exhibition booth design companies."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    async def generate_linkedin_post(
        self,
        industry: str,
        exhibition: str,
        provider: str = "openai"
    ) -> str:
        """Generate a LinkedIn post for exhibition booth design."""
        prompt = f"""Create an engaging LinkedIn post for an exhibition booth design company attending {exhibition} in the {industry} industry.

Requirements:
- Professional but engaging tone
- Include relevant hashtags (3-5)
- Highlight booth design services and expertise
- Include a call-to-action
- Maximum 300 words
- Include emojis sparingly for visual appeal

Write the LinkedIn post:"""
        
        return await self.generate_content(prompt, provider)
    
    async def generate_facebook_post(
        self,
        industry: str,
        exhibition: str,
        provider: str = "openai"
    ) -> str:
        """Generate a Facebook post for exhibition booth design."""
        prompt = f"""Create an engaging Facebook post for an exhibition booth design company attending {exhibition} in the {industry} industry.

Requirements:
- Friendly and conversational tone
- Include relevant hashtags (2-4)
- Highlight booth design services and what makes them unique
- Include a call-to-action encouraging messages
- Maximum 150 words
- Include emojis for engagement

Write the Facebook post:"""
        
        return await self.generate_content(prompt, provider)
    
    async def generate_google_business_post(
        self,
        industry: str,
        exhibition: str,
        provider: str = "openai"
    ) -> str:
        """Generate a Google Business Profile post."""
        prompt = f"""Create a concise Google Business Profile post for an exhibition booth design company attending {exhibition} in the {industry} industry.

Requirements:
- Brief and informative (under 100 words)
- Professional tone
- Include relevant keywords for local SEO
- Include a call-to-action
- Include 1-2 relevant hashtags
- Focus on driving customer action

Write the Google Business Profile post:"""
        
        return await self.generate_content(prompt, provider, max_tokens=500)
    
    async def generate_image_prompts(
        self,
        industry: str,
        exhibition: str,
        provider: str = "openai",
        count: int = 4
    ) -> list[str]:
        """Generate AI image generation prompts for exhibition booth designs."""
        prompt = f"""Generate {count} detailed image prompts for AI image generators (like Midjourney, DALL-E, Stable Diffusion) to create exhibition booth concept images for a booth design company attending {exhibition} in the {industry} industry.

Each prompt should:
- Be detailed and specific (50-100 words each)
- Describe booth design, lighting, materials, layout
- Include style references (photorealistic, modern, etc.)
- Include camera/shot angle suggestions
- Be separated by a line with "---"

Generate exactly {count} prompts, numbered 1-{count}:"""
        
        content = await self.generate_content(prompt, provider, max_tokens=2000)
        
        # Parse prompts from response
        prompts = []
        parts = content.split("---")
        for part in parts:
            part = part.strip()
            # Remove numbered prefixes
            if part:
                import re
                part = re.sub(r'^\d+[\.\)]\s*', '', part)
                prompts.append(part)
        
        return prompts[:count]
    
    def is_available(self) -> bool:
        """Check if any AI provider is configured."""
        return bool(self.openai_api_key or self.deepseek_api_key)
    
    def get_provider_name(self) -> str:
        """Get the name of the available AI provider."""
        if self.deepseek_api_key:
            return "deepseek"
        elif self.openai_api_key:
            return "openai"
        return "none"


# Singleton instance
ai_service = AIService()
