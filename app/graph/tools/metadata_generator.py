import logging

from langchain_core.tools import tool

from app.graph.state import SeoMetadata
from app.graph.tools import get_llm
from config.config import cfg

logger = logging.getLogger(__name__)


@tool
def metadata_generator_tool(article_content: str, primary_keyword: str) -> str:
    """Generate SEO title tag, meta description, and keyword list from an article."""
    structured_llm = get_llm().with_structured_output(SeoMetadata, method="function_calling")

    hp_meta = cfg.hyperparams.metadata
    hp_qa = cfg.hyperparams.qa.thresholds

    # Truncate content sent to the LLM to avoid huge prompts
    preview = article_content[:hp_meta.article_preview_chars]

    prompt = cfg.prompts.tools.metadata.format(
        primary_keyword=primary_keyword,
        preview=preview,
        title_max=hp_qa.title_tag_max,
        desc_max=hp_qa.meta_description_max,
        secondary_min=hp_meta.secondary_keywords_min,
        secondary_max=hp_meta.secondary_keywords_max,
    )

    result: SeoMetadata = structured_llm.invoke(prompt)
    return result.model_dump_json()

