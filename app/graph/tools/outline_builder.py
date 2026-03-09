import json
import logging

from langchain_core.tools import tool

from app.graph.state import OutlineOutput
from app.graph.tools import get_llm
from config.config import cfg

logger = logging.getLogger(__name__)


@tool
def outline_builder_tool(themes_json: str, keywords_json: str, word_count: int) -> str:
    """Build a structured SEO article outline from themes and keywords."""
    print("="*60)
    print('Outline Builder Tool working')
    structured_llm = get_llm().with_structured_output(OutlineOutput, method="function_calling")

    hp = cfg.hyperparams.outline
    prompt = cfg.prompts.tools.outline_builder.format(
        themes_json=themes_json,
        keywords_json=keywords_json,
        word_count=word_count,
        h2_count_min=hp.h2_count_min,
        h2_count_max=hp.h2_count_max,
        h3_per_h2_min=hp.h3_per_h2_min,
        h3_per_h2_max=hp.h3_per_h2_max,
        h1_word_min=hp.h1_word_min,
        h1_word_max=hp.h1_word_max,
        h2_word_pct_min=hp.h2_word_pct_min,
        h2_word_pct_max=hp.h2_word_pct_max,
        h3_word_pct_min=hp.h3_word_pct_min,
        h3_word_pct_max=hp.h3_word_pct_max,
        # H3 count range for validation line
        section_count_min_h3=hp.h2_count_min * hp.h3_per_h2_min,
        section_count_max_h3=hp.h2_count_max * hp.h3_per_h2_max,
        section_count_min=hp.section_count_min,
        section_count_max=hp.section_count_max,
        word_target_tolerance_pct=hp.word_target_tolerance_pct,
    )

    result: OutlineOutput = structured_llm.invoke(prompt)
    print('OUTLINE BUILDER SUCCESSFUL !!')
    result_json = result.model_dump_json()
    print(json.dumps(json.loads(result_json), indent=2))
    print("Outline builder ends")
    print("="*60)
    return result_json

