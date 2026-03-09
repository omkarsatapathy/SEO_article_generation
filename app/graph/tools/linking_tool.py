import logging

from langchain_core.tools import tool

from app.graph.state import LinkingSuggestions
from app.graph.tools import get_llm

logger = logging.getLogger(__name__)


@tool
def linking_tool(outline_json: str, themes_json: str) -> str:
    """Suggest internal and external links based on the article outline and themes."""
    structured_llm = get_llm().with_structured_output(LinkingSuggestions, method="function_calling")

    prompt = f"""You are an SEO link-building specialist. Suggest relevant links for an article.

Outline (JSON): {outline_json}
Themes (JSON): {themes_json}

Requirements:
- Internal links (3–5): suggest anchor_text and a suggested_target_topic for a related page on the same site.
- External links (2–4): suggest authoritative, real-world source_url values (e.g. Wikipedia, gov sites, major publications) and a context string describing where in the article the link should appear.

Return a fully populated LinkingSuggestions."""

    result: LinkingSuggestions = structured_llm.invoke(prompt)
    return result.model_dump_json()

