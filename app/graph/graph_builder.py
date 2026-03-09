from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.db.checkpointer import get_checkpointer
from app.graph.nodes.orchestrator import orchestrator_node
from app.graph.nodes.output_builder import output_builder_node
from app.graph.nodes.outline import outline_node
from app.graph.nodes.qa import qa_node
from app.graph.nodes.research import research_node
from app.graph.nodes.writer import writer_node
from app.graph.state import ArticleGenerationState
from config.config import cfg


# ── Inline error-handler node ─────────────────────────────────────────────────

def error_handler_node(state: ArticleGenerationState) -> dict:
    """Terminal failure node — marks the job as failed and surfaces accumulated errors."""
    return {
        "status": "failed",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Conditional routing functions ─────────────────────────────────────────────

def route_after_research(state: ArticleGenerationState) -> str:
    retry_counts = state.get("retry_counts") or {}
    if retry_counts.get("research", 0) >= settings.MAX_RETRIES:
        return "error_handler"
    if state.get("serp_results"):
        return "outline"
    return "research"


def route_after_outline(state: ArticleGenerationState) -> str:
    retry_counts = state.get("retry_counts") or {}
    if retry_counts.get("outline", 0) >= settings.MAX_RETRIES:
        return "error_handler"
    if state.get("outline"):
        return "writer"
    return "outline"


def route_after_writer(state: ArticleGenerationState) -> str:
    retry_counts = state.get("retry_counts") or {}
    if retry_counts.get("writer", 0) >= settings.MAX_RETRIES:
        return "error_handler"
    if state.get("article_draft"):
        return "qa"
    return "writer"


def route_after_qa(state: ArticleGenerationState) -> str:
    if state.get("status") == "done":
        return "output"
    if (state.get("revision_count") or 0) >= cfg.hyperparams.pipeline.max_revisions:
        return "output"  # publish best effort
    return "writer"


# ── Graph assembly ────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    """Build and compile the SEO article generation StateGraph."""
    builder = StateGraph(ArticleGenerationState)

    # Nodes
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("research", research_node)
    builder.add_node("outline", outline_node)
    builder.add_node("writer", writer_node)
    builder.add_node("qa", qa_node)
    builder.add_node("output", output_builder_node)
    builder.add_node("error_handler", error_handler_node)

    # Fixed edges
    builder.add_edge(START, "orchestrator")
    builder.add_edge("orchestrator", "research")
    builder.add_edge("output", END)
    builder.add_edge("error_handler", END)

    # Conditional edges
    builder.add_conditional_edges("research", route_after_research)
    builder.add_conditional_edges("outline", route_after_outline)
    builder.add_conditional_edges("writer", route_after_writer)
    builder.add_conditional_edges("qa", route_after_qa)

    return builder.compile(checkpointer=checkpointer)


def get_default_graph():
    """Convenience function: build the graph with the production PostgreSQL checkpointer."""
    checkpointer = get_checkpointer(settings.DATABASE_URL)
    return build_graph(checkpointer=checkpointer)

