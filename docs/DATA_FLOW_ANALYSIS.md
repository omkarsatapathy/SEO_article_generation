# Data Flow Analysis: Article Writer Missing Research Content

## THE PROBLEM
The LLM is writing content **without access to the research data** collected by the Research Agent.

---

## DATA FLOW BACKTRACK

### Stage 1: Research Agent Collects (✅ Rich Data Collected)
```
research_node() invokes ReAct Agent
  │
  ├─→ serp_fetch_tool(topic)
  │   └─→ Returns SERP results with:
  │       - rank (1-10)
  │       - url (source URL)
  │       - title (page titles)
  │       - snippet (actual content/context from pages) ⭐⭐⭐
  │
  ├─→ theme_extractor_tool(serp_results_json)
  │   └─→ Returns:
  │       - common_themes (extracted from content)
  │       - extracted_keywords (with frequency, is_primary)
  │       - competitor_structures (headings from top pages)
  │       - faq_questions (extracted from snippets)
  │
  └─→ faq_extractor_tool()
      └─→ Returns FAQ questions
```

### Stage 2: State Stores All This Data (✅ Full Data in State)
Located in `/app/graph/state.py` - `ArticleGenerationState`:
```python
class ArticleGenerationState(TypedDict):
    # ⭐ Research Stage — ALL collected here:
    serp_results: Optional[List[SerpResult]]           # ← Snippets from real sources!
    common_themes: Optional[List[str]]                 # ← Themes from research
    extracted_keywords: Optional[List[Keyword]]        # ← Keywords with frequency
    competitor_structures: Optional[List[CompetitorStructure]]  # ← What competitors write
    faq_questions: Optional[List[str]]                 # ← FAQs from research
```

### Stage 3: Writer Node Calls article_writer_tool (❌ MISSING DATA!)

**Current - What Gets Passed:**
```python
# In /app/graph/nodes/writer.py - writer_node()
draft_json = article_writer_tool.invoke(
    {
        "outline_json": outline_json,                    # ✅ Structure only
        "keywords_json": keywords_json,                  # ✅ Keywords only
        "themes_json": themes_json,                      # ✅ Theme names only
        "language": language,                            # ✅ Language
        "faq_questions_json": faq_json,                  # ✅ Q words, no context
        "target_word_count": target_wc,                  # ✅ Target
        "qa_feedback": qa_feedback,                      # ✅ QA issues
        
        # ❌ MISSING:
        # "serp_results_json": ???              ← NOT PASSED! (Has real snippets!)
        # "competitor_structures_json": ???     ← NOT PASSED! (Has what competitors wrote)
    }
)
```

### Stage 4: LLM Receives Incomplete Context (❌ NO RAW DATA)

**article_writer_tool function signature:**
```python
def article_writer_tool(
    outline_json: str,              # Just structure: "H1" → "H2" → "H3"
    keywords_json: str,             # Just keyword list: ["keyword1", "keyword2"]
    themes_json: str,               # Just array: ["theme1", "theme2"]
    language: str,
    faq_questions_json: str,        # FAQ questions without context
    target_word_count: int = 1500,
    qa_feedback: str = "",
) -> str:
```

**What happens in _generate_section():**
```python
def _generate_section(
    llm,
    block: Dict[str, Any],
    primary_kw: str,
    keywords_json: str,            # ← Keywords only
    themes_json: str,              # ← Theme names only (list)
    language: str,
    article_so_far: str,
    qa_feedback: str,
    remaining_budget: int | None = None,
) -> str:
    # LLM prompt built with:
    prompt = f"""Write the following section of an SEO article in {language}.
    
    ## {h2_heading}
    Word target: {total_target}
    Section keywords: {h2_keywords}        # ← Just names!
    
    Themes: {themes_json}                  # ← Just ["theme1", "theme2"]
    
    Previous content (for continuity):
    {article_so_far[-800:]}                # ← Only 800 chars of previous!
    """
    
    # ❌ NO SERP snippets about this section
    # ❌ NO competitor examples
    # ❌ NO real data sources
```

---

## WHAT'S MISSING

| Data | Available in State? | Passed to Writer? | Sent to LLM? | Impact |
|------|:--:|:--:|:--:|---|
| **SERP snippets** (real source content) | ✅ `serp_results` | ❌ NO | ❌ NO | LLM has NO factual data about topic |
| **Competitor structures** (H1/H2/H3 from competitors) | ✅ `competitor_structures` | ❌ NO | ❌ NO | LLM doesn't know topic structure |
| **Competitor content** (actual competitor snippets) | ✅ In `serp_results[].snippet` | ❌ NO | ❌ NO | LLM can't see HOW competitors write |
| **FAQ with source snippets** | ✅ `faq_questions` + `serp_results` | ❌ Partial | ❌ Partial | FAQ written without context |
| **Keyword context** (where keywords appear in SERP) | ✅ In `serp_results` | ❌ NO | ❌ NO | LLM doesn't know keyword usage |

---

## EXAMPLE: CURRENT vs IDEAL

### Current Flow (Today - Problematic)
```
Research Agent: "Found top 10 results about 'AI model training'"
Stores: 
  - serp_results[0] = {
      "url": "https://example.com/ai-training",
      "snippet": "Model training involves feeding data through neural networks..."
    }

Writer Node says:
  "Here's your theme: 'neural networks', 'training methods'"
  
LLM receives: "Write about section 'Model Training Basics' (300 words) using theme 'neural networks'"
             (No actual snippet content!)

LLM generates: Generic content based on pattern matching, not research data
```

### Ideal Flow (Proposed)
```
Research Agent: "Found top 10 results about 'AI model training'"
Stores:
  - serp_results[0] = {
      "url": "https://example.com/ai-training",
      "snippet": "Model training involves feeding data through neural networks
                  with backpropagation. Industry standard uses mini-batches..."
    }
  - competitor_structures = [{
      "url": "...",
      "headings": ["H2: Types of Training", "H3: Supervised Learning", ...]
    }]

Writer Node says:
  "Theme: 'neural networks'
   Research snippet: 'Model training involves feeding data...'
   Competitor example structure: 'Types of Training' → 'Supervised Learning'
   Keywords found in context: 'backpropagation', 'mini-batches'"
  
LLM receives: Complete research context + structure examples

LLM generates: Data-backed content using actual research, proper structure, real terminology
```

---

## ROOT CAUSE

**File:** `/app/graph/nodes/writer.py` - `writer_node()` function

**Lines ~42-56:** Constructs JSON for article_writer_tool
```python
outline_json = json.dumps([s.model_dump() for s in (state.get("outline") or [])])
keywords_json = json.dumps([k.model_dump() for k in (state.get("extracted_keywords") or [])])
themes_json = json.dumps(state.get("common_themes") or [])      # ← Just theme names
faq_json = json.dumps(state.get("faq_questions") or [])

# ❌ MISSING:
# serp_results_json = json.dumps([s.model_dump() for s in (state.get("serp_results") or [])])
# competitor_structures_json = json.dumps([c.model_dump() for c in (state.get("competitor_structures") or [])])
```

**Then passes to article_writer_tool (Line 64-72):**
```python
draft_json = article_writer_tool.invoke(
    {
        "outline_json": outline_json,
        "keywords_json": keywords_json,
        "themes_json": themes_json,           # ← Only theme NAMES
        "language": language,
        "faq_questions_json": faq_json,
        "target_word_count": target_wc,
        "qa_feedback": qa_feedback,
        # ❌ NO serp_results_json
        # ❌ NO competitor_structures_json
    }
)
```

---

## RECOMMENDATION

### ✅ Solution Steps:
1. **Modify `article_writer_tool` signature** - Add parameters:
   - `serp_results_json`: Full SERP snippets + URLs
   - `competitor_structures_json`: Competitor outline examples
   
2. **Update writer_node()** - Pass research data:
   ```python
   serp_results_json = json.dumps([s.model_dump() for s in (state.get("serp_results") or [])])
   competitor_structures_json = json.dumps([c.model_dump() for c in (state.get("competitor_structures") or [])])
   ```

3. **Enhance _generate_section() prompts** - Include in LLM prompt:
   ```
   Research context:
   {relevant_serp_snippets_for_this_section}
   
   Competitor examples for this topic:
   {competitor_headings}
   ```

4. **Add section-specific filtering** - Filter SERP/competitor data by section keywords

---

## IMPACT
- **Now:** LLM writes generic content from patterns → Lower SEO relevance, weak topical authority
- **With Fix:** LLM writes data-backed content from research → Higher SEO value, better topical depth

## Current Blocker
The article writer is **blind to the research data** it should be using!
