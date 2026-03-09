import logging
from typing import List

import requests
from langchain_core.tools import tool

from app.config import settings
from app.graph.state import SerpResult
from config.config import cfg

logger = logging.getLogger(__name__)

# # ── Mock data templates ───────────────────────────────────────────────────────

# _TECH_MOCKS = [
#     (
#         "techcrunch.com",
#         "{query}: The Complete Developer Guide for {year}",
#         "A deep dive into {query} covering architecture, best practices, performance "
#         "benchmarks, and real-world implementation patterns used by top engineering teams.",
#     ),
#     (
#         "dev.to",
#         "How to Master {query} — Step-by-Step Tutorial",
#         "Learn {query} from scratch with hands-on examples. This tutorial walks through "
#         "setup, core concepts, common pitfalls, and production-ready patterns.",
#     ),
#     (
#         "medium.com/engineering",
#         "{query} Explained: What Every Engineer Should Know",
#         "Understanding {query} is essential for modern software development. We break down "
#         "the fundamentals, trade-offs, and when to choose this approach over alternatives.",
#     ),
#     (
#         "stackoverflow.blog",
#         "Why {query} Is Changing the Way We Build Software",
#         "The rise of {query} has reshaped software engineering workflows. Here's what the "
#         "data shows and how teams are adapting their processes and tooling.",
#     ),
#     (
#         "smashingmagazine.com",
#         "{query} Best Practices: A Practical Handbook",
#         "This handbook covers {query} best practices drawn from hundreds of real projects. "
#         "Includes code samples, anti-patterns to avoid, and a checklist for production use.",
#     ),
#     (
#         "css-tricks.com",
#         "Getting Started with {query} in {year}",
#         "New to {query}? This beginner-friendly guide covers installation, your first "
#         "project, key concepts, and community resources to keep learning.",
#     ),
#     (
#         "infoq.com",
#         "{query} at Scale: Lessons from the Field",
#         "Engineering teams share hard-won lessons scaling {query} to millions of requests. "
#         "Topics include observability, failure modes, and capacity planning strategies.",
#     ),
#     (
#         "hackernoon.com",
#         "The Pros and Cons of {query} You Need to Know",
#         "Before adopting {query}, understand the trade-offs. This balanced comparison "
#         "covers performance, maintainability, ecosystem maturity, and team learning curve.",
#     ),
#     (
#         "dzone.com",
#         "{query} vs the Alternatives: Which Should You Use?",
#         "Comparing {query} against competing solutions across key dimensions: performance, "
#         "developer experience, community support, and licence model.",
#     ),
#     (
#         "thenewstack.io",
#         "Future of {query}: Trends and Predictions for {year}",
#         "Industry analysts and practitioners share their {year} outlook for {query}, "
#         "including emerging patterns, tooling investments, and adoption forecasts.",
#     ),
# ]

# _MARKETING_MOCKS = [
#     (
#         "hubspot.com/blog",
#         "{query}: The Ultimate Marketing Guide for {year}",
#         "HubSpot's definitive guide to {query} covers strategy, proven tactics, KPIs to "
#         "track, and a step-by-step playbook to drive measurable business results.",
#     ),
#     (
#         "neilpatel.com",
#         "How to Use {query} to Grow Your Business Fast",
#         "Neil Patel breaks down how to leverage {query} for rapid growth. Includes data "
#         "from 1,000+ campaigns and a prioritised action plan you can start today.",
#     ),
#     (
#         "searchenginejournal.com",
#         "{query} Strategy: Everything You Need to Know",
#         "A comprehensive {query} strategy guide covering research, execution, measurement, "
#         "and iteration loops based on real campaign data and expert interviews.",
#     ),
#     (
#         "moz.com/blog",
#         "The Beginner's Guide to {query}",
#         "Moz's beginner guide to {query} makes complex concepts accessible. Learn the "
#         "fundamentals, set up your first campaign, and measure what matters.",
#     ),
#     (
#         "contentmarketinginstitute.com",
#         "{query} for Content Marketers: A Practical Playbook",
#         "Discover how content marketing teams are integrating {query} into their workflows "
#         "to increase reach, engagement, and conversion across every funnel stage.",
#     ),
#     (
#         "semrush.com/blog",
#         "{query} Tips That Actually Work in {year}",
#         "SEMrush analysed thousands of campaigns to find which {query} tactics deliver ROI. "
#         "Here are the evidence-based tips your team can implement this quarter.",
#     ),
#     (
#         "marketingland.com",
#         "Why {query} Should Be Your Top Priority This Year",
#         "Brands that invest in {query} are outperforming competitors across key metrics. "
#         "Here's the business case, benchmarks, and a roadmap to get started.",
#     ),
#     (
#         "ahrefs.com/blog",
#         "{query}: Data-Driven Insights from 10M+ Websites",
#         "Ahrefs analysed over 10 million websites to surface the {query} patterns that "
#         "correlate with top rankings, organic traffic, and conversion rates.",
#     ),
#     (
#         "sproutsocial.com/insights",
#         "How Top Brands Use {query} to Win Customers",
#         "Case studies from leading brands reveal how {query} drives customer acquisition "
#         "and retention. Includes benchmarks, creative examples, and key takeaways.",
#     ),
#     (
#         "forbes.com/marketing",
#         "{query} Trends Every Marketer Must Watch in {year}",
#         "Forbes spoke to CMOs and growth leaders about the {query} trends reshaping "
#         "marketing in {year}. Here's what the smartest teams are prioritising now.",
#     ),
# ]

# _GENERAL_MOCKS = [
#     (
#         "forbes.com",
#         "Everything You Need to Know About {query} in {year}",
#         "Forbes breaks down {query} in plain language. This comprehensive overview covers "
#         "key concepts, recent developments, expert opinions, and what it means for you.",
#     ),
#     (
#         "wikipedia.org/wiki",
#         "{query} — Overview, History, and Key Concepts",
#         "An encyclopaedic overview of {query} covering its origins, core principles, "
#         "notable developments, and current applications across industries.",
#     ),
#     (
#         "investopedia.com",
#         "What Is {query}? Definition, Examples, and Benefits",
#         "Investopedia explains {query} with clear definitions, real-world examples, a "
#         "glossary of related terms, and a breakdown of key advantages and limitations.",
#     ),
#     (
#         "businessinsider.com",
#         "{query}: Why It Matters and How to Get Started",
#         "Business Insider's explainer on {query} covers why it has become important in "
#         "{year}, who is using it, and a practical guide for getting started quickly.",
#     ),
#     (
#         "theatlantic.com",
#         "The Rise of {query}: A Deep Dive",
#         "An in-depth look at how {query} emerged, the forces driving its growth, and the "
#         "broader implications for society, business, and individual decision-making.",
#     ),
#     (
#         "hbr.org",
#         "How Leaders Are Thinking About {query} Today",
#         "Harvard Business Review surveys executives on {query}: how they define it, where "
#         "they see opportunity, and the management challenges they're navigating.",
#     ),
#     (
#         "wired.com",
#         "{query} Is Here — And It's Changing Everything",
#         "Wired examines how {query} is transforming industries, the people leading the "
#         "charge, and the questions we should all be asking right now.",
#     ),
#     (
#         "nytimes.com",
#         "Understanding {query}: A Guide for Everyone",
#         "The New York Times explains {query} in accessible terms, with expert commentary, "
#         "visual explainers, and answers to the questions readers ask most.",
#     ),
#     (
#         "theguardian.com",
#         "{query}: Facts, Myths, and What the Experts Say",
#         "We separate fact from fiction on {query}, drawing on interviews with leading "
#         "experts, peer-reviewed research, and analysis of the latest available data.",
#     ),
#     (
#         "mckinsey.com/insights",
#         "The Business Case for {query}: McKinsey Analysis",
#         "McKinsey's analysis of {query} quantifies the opportunity, identifies the "
#         "critical success factors, and maps the implementation journey for organisations.",
#     ),
# ]

# _TECH_KEYWORDS = {
#     "api", "code", "software", "developer", "programming", "python", "javascript",
#     "framework", "database", "cloud", "devops", "ai", "ml", "llm", "model",
#     "architecture", "backend", "frontend", "docker", "kubernetes", "git",
# }
# _MARKETING_KEYWORDS = {
#     "seo", "marketing", "content", "keyword", "rank", "traffic", "organic",
#     "campaign", "social", "email", "funnel", "conversion", "brand", "ads",
#     "growth", "leads", "analytics", "backlink", "serp",
# }


# def _select_template_set(query: str) -> list:
#     q_lower = query.lower()
#     words = set(q_lower.split())
#     if words & _TECH_KEYWORDS:
#         return _TECH_MOCKS
#     if words & _MARKETING_KEYWORDS:
#         return _MARKETING_MOCKS
#     return _GENERAL_MOCKS


# def get_mock_serp_data(query: str) -> List[SerpResult]:
#     """Return 10 realistic mock SerpResult objects for the given query."""
#     templates = _select_template_set(query)
#     year = "2025"
#     results = []
#     for rank, (domain, title_tpl, snippet_tpl) in enumerate(templates, start=1):
#         title = title_tpl.format(query=query.title(), year=year)
#         snippet = snippet_tpl.format(query=query, year=year)
#         url = f"https://www.{domain}/{query.lower().replace(' ', '-')}-guide"
#         results.append(
#             SerpResult(rank=rank, url=url, title=title, snippet=snippet[:200])
#         )
#     return results


# ── LangChain tool ────────────────────────────────────────────────────────────

@tool
def serp_fetch_tool(query: str) -> List[SerpResult]:
    """Fetch the top 10 Google search results for *query* via SerpAPI.

    Falls back to realistic mock data on any network or parsing error.
    """
    try:
        response = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": 10, "api_key": settings.SERPAPI_KEY},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        organic = data.get("organic_results", [])
        result =  [
            SerpResult(
                rank=item.get("position", idx + 1),
                url=item["link"],
                title=item["title"],
                snippet=item.get("snippet", ""),
            )
            for idx, item in enumerate(organic[:cfg.hyperparams.serp.organic_results_limit])
        ]
        print('SERP CALL SUCCESSFUL !! output with len:', len(result))
        return result
    except Exception as exc:
        logger.warning(
            "serp_fetch_tool: SerpAPI call failed (%s: %s). Using mock data.",
            type(exc).__name__,
            exc,
        )
        # return get_mock_serp_data(query)
