import logging

from langchain_core.tools import tool

from app.graph.state import LinkingSuggestions
from app.graph.tools import get_llm
from config.config import cfg

logger = logging.getLogger(__name__)


@tool
def linking_tool(outline_json: str, themes_json: str) -> str:
    """Suggest internal and external links based on the article outline and themes."""
    structured_llm = get_llm().with_structured_output(LinkingSuggestions, method="function_calling")

    lk = cfg.hyperparams.linking
    prompt = cfg.prompts.tools.linking.format(
        outline_json=outline_json,
        themes_json=themes_json,
        internal_min=lk.internal_links_min,
        internal_max=lk.internal_links_max,
        external_min=lk.external_links_min,
        external_max=lk.external_links_max,
    )

    result: LinkingSuggestions = structured_llm.invoke(prompt)
    return result.model_dump_json()

