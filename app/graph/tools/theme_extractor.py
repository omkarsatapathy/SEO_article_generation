import json
import logging
from typing import List

from langchain_core.tools import tool

from app.graph.state import SerpResult, ThemeAnalysis, Keyword
from app.graph.tools import get_llm
from config.config import cfg

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


@tool
def theme_extractor_tool(serp_results_json: str) -> str:
    """Analyze SERP results and extract themes, keywords, competitor structures, and FAQs."""
    print("="*60)
    print('Theme Extractor Tool working')
    try:
        raw = json.loads(serp_results_json)

        # The ReAct agent sometimes passes strings instead of dicts — normalise.
        serp_results: List[SerpResult] = []
        for i, r in enumerate(raw if isinstance(raw, list) else []):
            if isinstance(r, dict):
                serp_results.append(SerpResult(**r))
            elif isinstance(r, str):
                # Best-effort: treat the string as a title/snippet
                serp_results.append(SerpResult(rank=i + 1, url="", title=r, snippet=r))

        structured_llm = get_llm().with_structured_output(ThemeAnalysis, method="function_calling")

        results_text = "\n".join(
            f"{r.rank}. [{r.title}]({r.url})\n   {r.snippet}"
            for r in serp_results
        )

        th = cfg.hyperparams.theme_extractor
        prompt = cfg.prompts.tools.theme_extractor.format(
            results_count=len(serp_results),
            results_text=results_text,
            themes_count=th.themes_count,
            keywords_min=th.keywords_min,
            keywords_max=th.keywords_max,
            faqs_min=th.faqs_min,
            faqs_max=th.faqs_max,
        )

        result: ThemeAnalysis = structured_llm.invoke(prompt)
        result_json = result.model_dump_json()
        result_dict = json.loads(result_json)
        print('THEME EXTRACTOR SUCCESSFUL !!')
        print(json.dumps(result_dict, indent=2))
        print("="*60)
        print("Theme extractor ends")
        return result_json

    except Exception as exc:
        logger.warning("theme_extractor_tool failed: %s — returning minimal fallback.", exc)
        fallback = ThemeAnalysis(
            themes=["General topic"],
            keywords=[
                Keyword(word="topic", frequency=1, is_primary=True)
            ],
            competitor_structures=[],
            faqs=[],
        )
        return fallback.model_dump_json()
