import logging

from langchain_core.tools import tool

from app.graph.state import SeoMetadata
from app.graph.tools import get_llm

logger = logging.getLogger(__name__)


@tool
def metadata_generator_tool(article_content: str, primary_keyword: str) -> str:
    """Generate SEO title tag, meta description, and keyword list from an article."""
    structured_llm = get_llm().with_structured_output(SeoMetadata, method="function_calling")

    # Truncate content sent to the LLM to avoid huge prompts — first 3000 chars is enough
    preview = article_content[:3000]
    

    prompt = f"""You are an SEO metadata specialist. Generate optimised metadata for the article below.

Primary keyword: {primary_keyword}

Article preview:
{preview}

Requirements:
- title_tag: ≤60 characters, must include the primary keyword, compelling and click-worthy.
- meta_description: ≤160 characters, must include the primary keyword and a clear call-to-action.
- primary_keyword: the exact primary keyword string.
- secondary_keywords: list of 4–8 secondary keywords found naturally in the article.

Return a fully populated SeoMetadata."""

    result: SeoMetadata = structured_llm.invoke(prompt)
    return result.model_dump_json()

