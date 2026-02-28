"""
Report generation service: uses Claude to produce structured property reports.
"""
import os
import json
from typing import Optional, List, Dict
import anthropic

from ..config import config
from .document_service import DocumentService

_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
_doc_service = DocumentService()

REPORT_PROMPTS = {
    "feasibility": """Generate a detailed property development feasibility report with the following sections:

1. **Executive Summary** - Key conclusions and recommendation
2. **Project Overview** - Site description, proposed development, key assumptions
3. **Development Cost Analysis** - Land cost, construction, professional fees, finance costs, contingency
4. **Revenue Analysis** - Gross realisation, absorption assumptions, pricing strategy
5. **Development Margin & Returns** - Development margin, return on cost, equity returns
6. **Financial Sensitivity Analysis** - Impact of ±10%/±20% on costs and revenue
7. **Key Risks & Mitigants** - Top 5 risks with mitigation strategies
8. **Recommendation** - Go/No-Go with conditions

Use specific numbers and figures where available from the project documents. Where data is not available, state assumptions clearly. Format as professional report suitable for board or investor presentation.""",

    "strategic_brief": """Generate a strategic project brief with the following sections:

1. **Project Vision & Objectives** - What success looks like
2. **Site & Context Analysis** - Location, zoning, constraints, opportunities
3. **SWOT Analysis** - Strengths, Weaknesses, Opportunities, Threats
4. **Strategic Options** - 2-3 development scenarios with pros/cons
5. **Planning Pathway** - Consent strategy, key risks, timeline
6. **Community & Stakeholder Considerations** - Community benefits, engagement strategy
7. **Financial Summary** - High-level economics of preferred option
8. **Next Steps & Decision Points** - Immediate actions required

Be strategic and concise. Focus on the big picture decisions and what needs to be resolved.""",

    "market_analysis": """Generate a property market analysis report with the following sections:

1. **Market Overview** - Current market conditions and trends
2. **Comparable Sales Analysis** - Recent comparable transactions
3. **Rental Market Analysis** - Vacancy rates, yields, demand drivers
4. **Supply Analysis** - Competing projects, pipeline supply
5. **Demand Analysis** - Target market, demographic trends, employment drivers
6. **Pricing & Absorption** - Recommended pricing, expected sales rates
7. **Market Risks** - Key risks to market assumptions
8. **Conclusions** - Market opportunity assessment

Search for current market data to supplement project documents. Use specific data points and percentages.""",

    "financial_model": """Generate a comprehensive property development financial model with the following sections:

1. **Project Assumptions** - All key inputs and assumptions
2. **Land & Acquisition Costs** - Purchase price, stamp duty, legals
3. **Development Costs** - Construction, professional fees, authorities, marketing, contingency
4. **Finance Costs** - Construction finance, interest calculations, establishment fees
5. **Revenue Schedule** - Unit/lot pricing, sales program, settlement timing
6. **Cash Flow Summary** - Monthly/quarterly project cash flow
7. **Returns Analysis** - Development margin, ROC, equity IRR, NPV
8. **Sensitivity Analysis** - Two-way sensitivity tables for key variables
9. **Funding Structure** - Equity/debt split, LVR, presales requirement

Present all figures in a clear tabular format. Show workings for key calculations.""",

    "community_benefit": """Generate a community benefit assessment with the following sections:

1. **Project Background** - Development overview and community context
2. **Direct Community Benefits** - Housing supply, affordable housing, local employment
3. **Infrastructure & Public Realm** - Public spaces, infrastructure contributions, amenities
4. **Economic Benefits** - Construction jobs, ongoing employment, rate revenue
5. **Social Outcomes** - Community cohesion, diversity, services access
6. **Environmental Sustainability** - Green features, environmental outcomes
7. **Stakeholder Perspectives** - Key stakeholders and their interests
8. **Community Benefit Statement** - Summary for planning submissions

Focus on genuine, measurable benefits. Be realistic rather than promotional.""",
}


async def generate_report(
    project_id: str,
    project_name: str,
    project_description: str,
    report_type: str,
    custom_instructions: Optional[str] = None,
) -> str:
    """Generate a report as Markdown string."""
    prompt_template = REPORT_PROMPTS.get(report_type)
    if not prompt_template:
        raise ValueError(f"Unknown report type: {report_type}. Valid types: {list(REPORT_PROMPTS.keys())}")

    # Retrieve relevant document chunks
    doc_chunks = await _doc_service.search(project_id, report_type + " " + project_name, n_results=10)

    doc_context = ""
    if doc_chunks:
        doc_context = "\n\n## Available Project Documents\n"
        for chunk in doc_chunks:
            meta = chunk.get("metadata", {})
            doc_context += f"\n[{meta.get('source', 'document')}]\n{chunk['text']}\n"

    system = f"""You are a senior property development advisor producing a professional report for '{project_name}'.
{project_description}

Generate reports in clean Markdown format suitable for conversion to PDF.
Use tables where appropriate for financial data. Be specific with numbers."""

    user_message = prompt_template
    if custom_instructions:
        user_message += f"\n\nAdditional instructions: {custom_instructions}"
    if doc_context:
        user_message = doc_context + "\n\n" + user_message

    response = await _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    report_content = response.content[0].text

    # Save report to disk
    reports_dir = os.path.join(config.projects_dir, project_id, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{report_type}_{timestamp}.md"
    filepath = os.path.join(reports_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {project_name} - {report_type.replace('_', ' ').title()}\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%d %B %Y %H:%M')}*\n\n")
        f.write(report_content)

    return report_content, filename


def list_reports(project_id: str) -> List[Dict]:
    """List generated reports for a project."""
    reports_dir = os.path.join(config.projects_dir, project_id, "reports")
    if not os.path.exists(reports_dir):
        return []
    reports = []
    for fname in sorted(os.listdir(reports_dir), reverse=True):
        if fname.endswith(".md"):
            fpath = os.path.join(reports_dir, fname)
            stat = os.stat(fpath)
            reports.append({
                "filename": fname,
                "size": stat.st_size,
                "created_at": stat.st_mtime,
            })
    return reports
