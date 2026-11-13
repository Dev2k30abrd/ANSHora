"""
Business Context / Semantic Layer — feature 10.

Stores per-dataset:
  - metrics: named business metrics -> {column, aggregation, description}
    e.g. "revenue" -> {column: "Sales", aggregation: "sum"}
  - synonyms: alias -> canonical column/metric name
    e.g. "turnover" -> "revenue", "qty" -> "Quantity"
  - rules: free-text business rules the agent should honor
    e.g. "Fiscal year starts in April, not January"
  - notes: free-text dataset context

resolve_reference() lets any tool argument go through synonym
resolution before hitting pandas, so "show me turnover by region"
correctly maps to the Sales column even though the word never
appears in the dataset.
"""

from app.services.dataset_manager import dataset_store


def get_context(dataset_id: str) -> dict:
    return dataset_store.get_business_context(dataset_id)


def upsert_metric(dataset_id: str, name: str, column: str, aggregation: str = "sum", description: str = "") -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["metrics"][name.lower()] = {
        "column": column,
        "aggregation": aggregation,
        "description": description,
    }
    dataset_store.set_business_context(dataset_id, context)
    return context


def delete_metric(dataset_id: str, name: str) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["metrics"].pop(name.lower(), None)
    dataset_store.set_business_context(dataset_id, context)
    return context


def upsert_synonym(dataset_id: str, alias: str, canonical: str) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["synonyms"][alias.lower()] = canonical
    dataset_store.set_business_context(dataset_id, context)
    return context


def delete_synonym(dataset_id: str, alias: str) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["synonyms"].pop(alias.lower(), None)
    dataset_store.set_business_context(dataset_id, context)
    return context


def add_rule(dataset_id: str, rule_text: str) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["rules"].append(rule_text)
    dataset_store.set_business_context(dataset_id, context)
    return context


def delete_rule(dataset_id: str, index: int) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    if 0 <= index < len(context["rules"]):
        context["rules"].pop(index)
    dataset_store.set_business_context(dataset_id, context)
    return context


def set_notes(dataset_id: str, notes: str) -> dict:
    context = dataset_store.get_business_context(dataset_id)
    context["notes"] = notes
    dataset_store.set_business_context(dataset_id, context)
    return context


def resolve_reference(dataset_id: str, reference: str) -> str:
    """
    Resolve a business term to its canonical dataset column name.
    Falls back to returning the input unchanged if no mapping exists,
    so this is always safe to call speculatively.
    """

    if not reference:
        return reference

    context = dataset_store.get_business_context(dataset_id)
    key = reference.lower()

    if key in context["synonyms"]:
        canonical = context["synonyms"][key]
        # synonym might point to a metric name rather than a raw column
        metric = context["metrics"].get(canonical.lower())
        return metric["column"] if metric else canonical

    if key in context["metrics"]:
        return context["metrics"][key]["column"]

    return reference


def context_summary_for_prompt(dataset_id: str) -> str:
    """Compact text block to inject into the agent's planning/narration prompts."""

    context = dataset_store.get_business_context(dataset_id)

    if not any([context["metrics"], context["synonyms"], context["rules"], context["notes"]]):
        return "(no business context defined for this dataset)"

    lines = []

    if context["metrics"]:
        lines.append("Defined metrics:")
        for name, spec in context["metrics"].items():
            lines.append(f"  - {name} = {spec['aggregation']}({spec['column']}) — {spec.get('description', '')}")

    if context["synonyms"]:
        lines.append("Synonyms:")
        for alias, canonical in context["synonyms"].items():
            lines.append(f"  - '{alias}' means '{canonical}'")

    if context["rules"]:
        lines.append("Business rules:")
        for rule in context["rules"]:
            lines.append(f"  - {rule}")

    if context["notes"]:
        lines.append(f"Notes: {context['notes']}")

    return "\n".join(lines)
