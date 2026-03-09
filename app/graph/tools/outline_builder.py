import json
import logging

from langchain_core.tools import tool

from app.graph.state import OutlineOutput
from app.graph.tools import get_llm

logger = logging.getLogger(__name__)


@tool
def outline_builder_tool(themes_json: str, keywords_json: str, word_count: int) -> str:
    """Build a structured SEO article outline from themes and keywords."""
    print("="*60)
    print('Outline Builder Tool working')
    structured_llm = get_llm().with_structured_output(OutlineOutput, method="function_calling")

    prompt = f"""You are an expert SEO content strategist specializing in creating detailed, keyword-optimized article outlines.

## INPUT DATA:
Themes: {themes_json}
Keywords: {keywords_json}
Target word count: {word_count}

## CRITICAL REQUIREMENTS (You MUST follow these exactly):

1. STRUCTURE:
   - Create exactly 1 H1 heading (the main article title). It MUST contain or reference the primary keyword from the keywords list.
   - Create 4 to 6 H2 headings. Each H2 should correspond to one of the themes provided.
   - Add 2 to 3 H3 sub-headings under each H2 heading for detailed coverage.

2. WORD COUNT DISTRIBUTION:
   - H1 section: 50-100 words (introduction)
   - H2 sections combined: 70-80% of total word count
   - H3 sections: 20-30% of total word count
   - Calculate proportionally: If total is {word_count}, divide by number of sections appropriately.
   - Each section MUST have a word_target that is a positive integer.

3. KEYWORD ASSIGNMENT:
   - Assign the most relevant keywords to each section's keywords list.
   - The H1 section should include the primary keyword.
   - Each H2/H3 section should have 1-3 relevant keywords.
   - Keywords MUST be from the provided keywords list.

4. OUTPUT FORMAT:
   - title (string): The H1 heading text - MUST be a string
   - sections (list): An ordered list of section objects
   - Each section object MUST include:
     - title: Section heading text (string)
     - level: Heading level (1, 2, or 3) - integer
     - keywords: List of relevant keywords (list of strings)
     - word_target: Target word count for this section (positive integer)

5. VALIDATION:
   - All word_target values MUST be positive integers (no decimals).
   - All keywords MUST be strings from the provided list.
   - Total sections should be 1 H1 + 4-6 H2s + 8-18 H3s (total: 13-25 sections).
   - Sum of all word_targets should be close to {word_count} (within 10% variation allowed).

## OUTPUT:
Generate the outline structure now. Ensure every field is properly formatted and all requirements are met."""

    result: OutlineOutput = structured_llm.invoke(prompt)
    print('OUTLINE BUILDER SUCCESSFUL !!')
    result_json = result.model_dump_json()
    print(json.dumps(json.loads(result_json), indent=2))
    print("Outline builder ends")
    print("="*60)
    return result_json

