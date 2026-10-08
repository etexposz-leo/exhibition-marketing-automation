from app.services.templates import (
    LINKEDIN_TEMPLATES,
    FACEBOOK_TEMPLATES,
    GOOGLE_BUSINESS_TEMPLATES,
    IMAGE_PROMPT_TEMPLATES
)
import random
from app.services import sales_copy

def sales_draft(industry, exhibition, platform):
    brief=sales_copy.analyze(sales_copy.Brief(target_audience=industry+" exhibitors",industry=industry,trade_show=exhibition))
    return sales_copy.generate_local(brief,platform)


def generate_linkedin_post(industry: str, exhibition: str) -> str:
    """Generate a LinkedIn post for exhibition booth design."""
    return sales_draft(industry, exhibition, "linkedin")


def generate_facebook_post(industry: str, exhibition: str) -> str:
    """Generate a Facebook post for exhibition booth design."""
    return sales_draft(industry, exhibition, "facebook")


def generate_google_business_post(industry: str, exhibition: str) -> str:
    """Generate a Google Business Profile post for exhibition booth design."""
    return sales_draft(industry, exhibition, "google_business")


def generate_image_prompts(industry: str, exhibition: str) -> list[str]:
    """Generate image prompts for exhibition booth design marketing materials."""
    prompts = []
    for template in random.sample(IMAGE_PROMPT_TEMPLATES, min(4, len(IMAGE_PROMPT_TEMPLATES))):
        prompts.append(template.format(industry=industry, exhibition=exhibition))
    return prompts


def generate_all_content(industry: str, exhibition: str) -> dict:
    """Generate all marketing content at once."""
    return {
        "linkedin_post": generate_linkedin_post(industry, exhibition),
        "facebook_post": generate_facebook_post(industry, exhibition),
        "google_business_post": generate_google_business_post(industry, exhibition),
        "image_prompts": generate_image_prompts(industry, exhibition)
    }
