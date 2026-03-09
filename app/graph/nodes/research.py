import json
import logging
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.graph.state import ArticleGenerationState, SerpResult, ThemeAnalysis
from app.graph.tools import get_llm
from app.graph.tools.serp_fetch import serp_fetch_tool
from app.graph.tools.theme_extractor import theme_extractor_tool
from config.config import cfg

logger = logging.getLogger(__name__)


def _get_max_iterations() -> int:
    return cfg.hyperparams.agent.research_max_iterations


def _normalize_tool(t, name: str):
    """Ensure tools are functions with a __name__, wrapping mocks when needed."""
    if inspect.isfunction(t) or inspect.ismethod(t) or inspect.isclass(t) or inspect.ismodule(t):
        if not getattr(t, "__name__", None):
            try:
                t.__name__ = name
            except Exception:
                pass
        if not getattr(t, "__doc__", None):
            try:
                t.__doc__ = "Wrapped tool"
            except Exception:
                pass
        return t

    if hasattr(t, "invoke"):
        if not getattr(t, "__name__", None):
            try:
                t.__name__ = getattr(t, "name", None) or name
            except Exception:
                pass
        if not getattr(t, "__doc__", None):
            try:
                t.__doc__ = getattr(t, "description", None) or "Wrapped tool"
            except Exception:
                pass
        return t

    def wrapper(*args, **kwargs):
        if hasattr(t, "invoke"):
            return t.invoke(*args, **kwargs)
        if callable(t):
            return t(*args, **kwargs)
        return t

    wrapper.__name__ = name
    wrapper.__qualname__ = name
    wrapper.__doc__ = getattr(t, "__doc__", "Wrapped mock tool") or "Wrapped mock tool"
    return wrapper


@tool
def faq_extractor_tool(serp_results_json: str) -> List[str]:
    """Lightweight heuristic FAQ extractor for SERP results."""
    try:
        raw = json.loads(serp_results_json)
        limit = cfg.hyperparams.theme_extractor.serp_results_limit
        questions: List[str] = []
        for item in raw[:limit]:
            title = item.get("title") or "this topic"
            questions.append(f"What should readers know about {title}?")
        if not questions:
            questions = ["What is the core definition of the topic?", "How does it work in practice?"]
        return questions
    except Exception:
        return ["What is the topic?", "Why does it matter?", "How can readers apply it?"]


def _build_research_agent():
    return create_react_agent(
        model=get_llm(),
        tools=[
            _normalize_tool(serp_fetch_tool, "serp_fetch_tool"),
            _normalize_tool(theme_extractor_tool, "theme_extractor_tool"),
            _normalize_tool(faq_extractor_tool, "faq_extractor_tool"),
        ],
        prompt=cfg.prompts.agents.research,
    )


def _extract_agent_payload(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    messages = agent_result.get("messages") or []
    if not messages:
        raise ValueError("Research agent returned no messages")

    final_message = messages[-1]
    content = getattr(final_message, "content", final_message)
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = " ".join(
            fragment.get("text", "") if isinstance(fragment, dict) else str(fragment)
            for fragment in content
        )
    if isinstance(final_message, AIMessage) and not isinstance(content, str):
        content = str(final_message)
    if not isinstance(content, str):
        content = str(content)

    return json.loads(content)


def _coerce_serp_results(raw: Any) -> List[SerpResult]:
    serp_results: List[SerpResult] = []
    for item in raw or []:
        if isinstance(item, SerpResult):
            serp_results.append(item)
        elif isinstance(item, dict):
            serp_results.append(SerpResult(**item))
    return serp_results


def _coerce_theme_analysis(payload: Dict[str, Any]) -> ThemeAnalysis:
    analysis_dict = {
        "themes": payload.get("common_themes") or payload.get("themes") or [],
        "keywords": payload.get("extracted_keywords") or payload.get("keywords") or [],
        "competitor_structures": payload.get("competitor_structures") or [],
        "faqs": payload.get("faq_questions") or payload.get("faqs") or [],
    }
    return ThemeAnalysis.model_validate(analysis_dict)


def research_node(state: ArticleGenerationState) -> dict:
    """Fetch SERP data and extract themes/keywords from top results via a ReAct agent."""
    print(json.dumps(dict(state), indent=2, default=str))
    logger.info("───────────────────────────────────────────────────")
    logger.info("🔍 RESEARCH NODE — Starting")
    logger.info("   Topic: %s", state.get("topic"))

    try:
        agent = _build_research_agent()
        
        topic = state.get("topic") or ""
        print(f"\n[STEP 1] Extracted topic from state:")
        print(f"  Topic: '{topic}'")
        print(f"  State keys: {list(state.keys())}")
        _dbg = cfg.hyperparams.debug
        print(f"  Full state summary: \n status={state.get('status')}, user_message={state.get('user_message', {}).get('content', '')[:_dbg.preview_short]}...")
        
        # Step 2: Build research agent
        print(f"\n[STEP 2] Building research agent...")
        agent = _build_research_agent()
        print(f"  ✓ Agent built successfully with LLM and 3 tools: serp_fetch_tool, theme_extractor_tool, faq_extractor_tool")

        # Step 3: Prepare user message for agent
        user_message = (
            f"Research topic: {topic}. "
            "Call serp_fetch_tool with query set to the topic. Convert the results to JSON and pass as "
            "serp_results_json into theme_extractor_tool. Use faq_extractor_tool if you need extra questions. "
            "Return only JSON with keys: serp_results, common_themes, extracted_keywords, competitor_structures, faq_questions."
        )
        print(f"\n[STEP 3] User message prepared:")
        print(f"  Message: {user_message[:_dbg.preview_long]}...")

        try:
            # Step 4: Invoke agent
            print(f"\n[STEP 4] Invoking research agent (max iterations: {_get_max_iterations()})...")
            print(f"  → Sending message to agent...")
            agent_result = agent.invoke(
                {"messages": [("user", user_message)]},
                config={"recursion_limit": _get_max_iterations()},
            )
            print(f"  ✓ Agent invocation completed")
            print(f"  Agent result keys: {list(agent_result.keys()) if isinstance(agent_result, dict) else 'Not a dict'}")

            # Step 5: Extract payload from agent result
            print(f"\n[STEP 5] Extracting payload from agent result...")
            payload = _extract_agent_payload(agent_result)
            print(f"  ✓ Payload extracted successfully")
            print(f"  Payload keys: {list(payload.keys())}")
            print(f"  Payload summary:")
            print(f"    - serp_results: {len(payload.get('serp_results', []))} items")
            print(f"    - common_themes: {len(payload.get('common_themes', []))} items")
            print(f"    - extracted_keywords: {len(payload.get('extracted_keywords', []))} items")
            print(f"    - competitor_structures: {len(payload.get('competitor_structures', []))} items")
            print(f"    - faq_questions: {len(payload.get('faq_questions', []))} items")

            # Step 6: Coerce SERP results
            print(f"\n[STEP 6] Coercing SERP results...")
            serp_results = _coerce_serp_results(payload.get("serp_results"))
            print(f"  ✓ SERP results coerced: {len(serp_results)} results")
            if serp_results:
                print(f"  Sample SERP result 1:")
                first_result = serp_results[0]
                print(f"    - Title: {getattr(first_result, 'title', 'N/A')[:_dbg.preview_short]}...")
                print(f"    - URL: {getattr(first_result, 'url', 'N/A')[:_dbg.preview_short]}...")
                print(f"    - Position: {getattr(first_result, 'position', 'N/A')}")

            # Step 7: Coerce theme analysis
            print(f"\n[STEP 7] Coercing theme analysis...")
            analysis = _coerce_theme_analysis(payload)
            print(f"  ✓ Theme analysis coerced successfully")
            print(f"  Analysis content:")
            print(f"    - Themes: {analysis.themes}")
            print(f"    - Keywords: {len(analysis.keywords)} keywords")
            if analysis.keywords:
                _kw_limit = cfg.hyperparams.theme_extractor.debug_sample_keywords
                print(f"      Sample keywords: {[k.word for k in analysis.keywords[:_kw_limit]]}")
            print(f"    - Competitor structures: {analysis.competitor_structures}")
            print(f"    - FAQs: {len(analysis.faqs)} questions")
            if analysis.faqs:
                _faq_limit = cfg.hyperparams.theme_extractor.debug_sample_faqs
                print(f"      Sample FAQs: {analysis.faqs[:_faq_limit]}")

        except Exception as agent_exc:
            print(f"\n[STEP 4-7 ERROR] Research agent failed, attempting fallback...")
            print(f"  Exception: {agent_exc}")
            logger.warning("   ⚠️  Research agent failed (%s). Falling back to direct tools.", agent_exc)
            
            # Fallback Step 4a: Direct SERP fetch
            print(f"\n[FALLBACK STEP 4a] Invoking SERP fetch directly...")
            print(f"  Query: '{topic}'")
            serp_raw = serp_fetch_tool.invoke({"query": topic})
            print(f"  ✓ SERP results received")
            print(f"  Raw SERP type: {type(serp_raw)}")
            if isinstance(serp_raw, str):
                print(f"  Converting string to JSON...")
                serp_payload = json.loads(serp_raw)
            else:
                print(f"  Converting list/objects to JSON-serializable format...")
                serp_payload = [r.model_dump() if hasattr(r, "model_dump") else r for r in (serp_raw or [])]
            print(f"  ✓ SERP payload ready: {len(serp_payload)} results")
            
            # Fallback Step 4b: Theme extraction
            print(f"\n[FALLBACK STEP 4b] Extracting themes from SERP results...")
            print(f"  Input SERP JSON size: {len(json.dumps(serp_payload))} chars")
            theme_json = theme_extractor_tool.invoke({"serp_results_json": json.dumps(serp_payload)})
            print(f"  ✓ Theme extraction completed")
            print(f"  Theme JSON type: {type(theme_json)}")
            
            # Fallback Step 4c: Parse theme analysis
            print(f"\n[FALLBACK STEP 4c] Parsing theme analysis JSON...")
            theme_analysis = ThemeAnalysis.model_validate_json(theme_json)
            print(f"  ✓ Theme analysis parsed successfully")
            print(f"  Themes: {theme_analysis.themes}")
            print(f"  Keywords: {len(theme_analysis.keywords)} keywords")
            print(f"  Competitor structures: {theme_analysis.competitor_structures}")
            print(f"  FAQs: {len(theme_analysis.faqs)} questions")
            
            # Fallback Step 4d: Coerce results
            print(f"\n[FALLBACK STEP 4d] Coercing fallback results...")
            serp_results = _coerce_serp_results(serp_payload)
            print(f"  ✓ SERP results coerced: {len(serp_results)} results")
            
            analysis = _coerce_theme_analysis(
                {
                    "common_themes": theme_analysis.themes,
                    "extracted_keywords": theme_analysis.keywords,
                    "competitor_structures": theme_analysis.competitor_structures,
                    "faq_questions": theme_analysis.faqs,
                }
            )
            print(f"  ✓ Theme analysis coerced successfully")

        # Step 8: Prepare final output
        print(f"\n[STEP 8] Preparing final output...")
        output = {
            "serp_results": serp_results,
            "common_themes": analysis.themes,
            "extracted_keywords": analysis.keywords,
            "competitor_structures": analysis.competitor_structures,
            "faq_questions": analysis.faqs,
            "status": "outlining",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"  ✓ Output prepared")
        print(f"    - SERP results: {len(serp_results)}")
        print(f"    - Themes: {len(analysis.themes)}")
        print(f"    - Keywords: {len(analysis.keywords)}")
        print(f"    - Competitor structures: {len(analysis.competitor_structures)}")
        print(f"    - FAQs: {len(analysis.faqs)}")
        print(f"    - Status: {output['status']}")
        print(f"    - Updated at: {output['updated_at']}")

        # Step 9: Success logging
        logger.info("   ✅ Got %d SERP results", len(serp_results))
        logger.info("   ✅ Themes extracted: %s", analysis.themes)
        logger.info(
            "   ✅ Keywords: %d found (primary: %s)",
            len(analysis.keywords),
            next((k.word for k in analysis.keywords if k.is_primary), "N/A"),
        )
        logger.info("   ✅ FAQs: %d questions", len(analysis.faqs))
        logger.info("🔍 RESEARCH NODE — Complete → status: outlining")
        logger.info("───────────────────────────────────────────────────")
        print(f"\n[RESEARCH NODE COMPLETE] Status: outlining", 'returning output: \n ')
        print(json.dumps({
            "serp_results": serp_results,
            "common_themes": analysis.themes,
            "extracted_keywords": analysis.keywords,
            "competitor_structures": analysis.competitor_structures,
            "faq_questions": analysis.faqs,
            "status": "outlining",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2, default=str))
        return {
            "serp_results": serp_results,
            "common_themes": analysis.themes,
            "extracted_keywords": analysis.keywords,
            "competitor_structures": analysis.competitor_structures,
            "faq_questions": analysis.faqs,
            "status": "outlining",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        print(f"\n[ERROR] ❌ RESEARCH NODE FAILED")
        print(f"  Exception type: {type(exc).__name__}")
        print(f"  Exception message: {exc}")
        import traceback
        print(f"  Traceback:\n{traceback.format_exc()}")
        
        logger.error("   ❌ RESEARCH NODE FAILED: %s", exc)
        retry_counts = dict(state.get("retry_counts") or {})
        retry_counts["research"] = retry_counts.get("research", 0) + 1
        print(f"  Retry count: {retry_counts['research']} / 3")
        logger.info("   🔄 Retry count: %d / 3", retry_counts["research"])
        
        error_output = {
            "errors": [f"research_node error: {exc}"],
            "retry_counts": retry_counts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        print("="*80)
        return error_output
