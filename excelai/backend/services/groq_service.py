from __future__ import annotations

import os
from typing import Any

from backend.models.schemas import ColumnSchema
from backend.utils.helpers import build_fallback_table, normalize_whitespace, parse_ai_payload, safe_json_loads

SYSTEM_PROMPT = """
You are ExcelLence's data extraction engine. You convert raw content into perfectly structured tabular data for Excel export.

CRITICAL COMPLETENESS RULES:
- Return ONLY valid JSON. No markdown, no backticks, no commentary.
- You MUST return ALL rows from the source data. Never truncate, summarize, or stop early.
- If the user requests N rows, return exactly N rows. If source has M rows, return all M rows.
- Do NOT add "..." or any truncation markers. If data exceeds context, prioritize more rows with fewer columns.

OUTPUT FORMAT (strict):
{
    "columns": [{ "name": "Rank", "type": "number" }],
    "rows": [[1, "Apple"]],
    "confidence": 0.96,
    "table_title": "Top 10 Tech Companies by Revenue 2024",
    "warnings": []
}

FORMAT RULES:
- Numeric strings -> numbers (remove commas, symbols). Dates -> ISO 8601 where possible.
- Detect types: number, currency, date, percentage, text.
- Null for missing values; do not fabricate.
- Provide precise warnings for uncertain cells/columns.
"""

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_PROMPT_CHARS = 50000  # Increased to handle large datasets (40-50 columns/rows)


def _truncate_for_llm(content: str) -> str:
    """Truncate content while preserving table structure and headers."""
    lines = content.split("\n")
    normalized = normalize_whitespace(content)
    if len(normalized) <= MAX_PROMPT_CHARS:
        return normalized
    
    # For large tables: keep headers + as many rows as possible
    header_lines = []
    data_lines = []
    found_data = False
    
    for line in lines:
        if not found_data:
            # Treat first 2 lines as potential headers
            if len(header_lines) < 2:
                header_lines.append(line)
                continue
            found_data = True
        data_lines.append(line)
    
    # Build result starting with headers
    result = "\n".join(header_lines)
    for line in data_lines:
        test = result + "\n" + line
        if len(test) <= MAX_PROMPT_CHARS - 100:  # Leave 100 char buffer for LLM formatting
            result = test
        else:
            # Add row count info instead of truncating silently
            remaining = len(data_lines) - len(result.split("\n")[2:])
            result += f"\n... ({remaining} more rows)"
            break
    
    return result


def _compose_user_prompt(source_label: str, content: str, clarification: str | None = None) -> str:
    content = _truncate_for_llm(content)
    if source_label == "URL":
        return (
            f"Here is the content scraped from a URL. Identify the most relevant table based on user intent: '{clarification or 'extract the primary table'}'. "
            f"Extract it into the JSON format above.\n\nCONTENT:\n{content}"
        )
    if source_label == "IMAGE":
        return (
            "Here is text extracted via OCR from a screenshot/image or PDF. Parse it into a structured table. "
            "Flag any values that may be OCR misreads (e.g. 'S' vs '5', 'l' vs '1').\n\n"
            f"CONTENT:\n{content}"
        )
    return (
        "The user has provided a data request or raw text. If the content is already tabular, extract it exactly. "
        "If the content is a request for a table, generate the best possible structured table that satisfies it. "
        "Always return a usable table with at least one column and one row.\n\n"
        f"CONTENT:\n{content}"
    )


def _extract_groq_content(client: Any, messages: list[dict[str, str]], strict_json: bool = True) -> str:
    request_kwargs: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 8000,
    }
    if strict_json:
        request_kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**request_kwargs)
    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None)
    if not content and isinstance(choice, dict):
        content = choice.get("message", {}).get("content")
    return content or "{}"


def generate_table(
    source_label: str,
    content: str,
    clarification: str | None = None,
    instruction: str | None = None,
) -> dict[str, Any]:
    fallback = build_fallback_table(content, hint=clarification or "Extracted Data")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        fallback["warnings"] = fallback.get("warnings", []) + ["GROQ_API_KEY is not configured. Fallback extraction was used."]
        return fallback

    try:
        from groq import Groq
    except Exception:
        fallback["warnings"] = fallback.get("warnings", []) + ["Groq SDK is unavailable. Fallback extraction was used."]
        return fallback

    try:
        client = Groq(api_key=api_key)
        user_prompt = _compose_user_prompt(source_label, content, clarification)
        if instruction:
            user_prompt += f"\n\nAdditional instruction: {instruction}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # First attempt: strict JSON mode with full prompt
        raw = _extract_groq_content(client, messages, strict_json=True)
        try:
            payload = safe_json_loads(raw)
            # Validate that we got actual data (not empty)
            if payload.get("columns") and payload.get("rows"):
                return parse_ai_payload(payload, content, hint=clarification or fallback.get("table_title") or "Extracted Data")
        except Exception as e1:
            pass  # Continue to retry

        # Second attempt: relaxed JSON mode with explicit strict instruction
        retry_prompt = (
            user_prompt
            + "\n\n[STRICT] You MUST return valid JSON. Return ONLY JSON, nothing else. "
            + "Ensure 'columns' array is not empty and 'rows' array has at least 1 element."
        )
        raw = _extract_groq_content(
            client,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": retry_prompt},
            ],
            strict_json=False,
        )
        try:
            payload = safe_json_loads(raw)
            if payload.get("columns") and payload.get("rows"):
                return parse_ai_payload(payload, content, hint=clarification or fallback.get("table_title") or "Extracted Data")
        except Exception as e2:
            pass  # Continue to retry

        # Third attempt: simplified system prompt with chunked data (first 3000 chars)
        chunk_size = 3000
        content_chunk = content[:chunk_size]
        if len(content) > chunk_size:
            content_chunk += f"\n... [Total input: {len(content)} characters, showing first {chunk_size}]"
        
        simple_system = (
            "Return ONLY valid JSON. Extract all columns and rows from data. "
            "CRITICAL: columns array MUST have at least 1 item. rows array MUST have at least 1 item. "
            'Format: {"columns": [{"name": "Col1", "type": "text"}], "rows": [["value1"]], "confidence": 0.8, "warnings": []}'
        )
        raw = _extract_groq_content(
            client,
            [
                {"role": "system", "content": simple_system},
                {"role": "user", "content": f"Extract this table data:\n{content_chunk}"},
            ],
            strict_json=False,
        )
        try:
            payload = safe_json_loads(raw)
            if payload.get("columns") and payload.get("rows"):
                return parse_ai_payload(payload, content, hint=clarification or fallback.get("table_title") or "Extracted Data")
        except Exception as e3:
            pass

        # Fourth attempt: ask LLM to first identify structure, then extract
        identify_structure_prompt = (
            "First, identify the structure of this data (how many columns, what are they named). "
            "Then extract all rows into JSON format. "
            f"Data:\n{content[:2000]}"
        )
        raw = _extract_groq_content(
            client,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": identify_structure_prompt},
            ],
            strict_json=False,
        )
        try:
            payload = safe_json_loads(raw)
            if payload.get("columns") and payload.get("rows"):
                return parse_ai_payload(payload, content, hint=clarification or fallback.get("table_title") or "Extracted Data")
        except Exception as e4:
            pass

        # All LLM attempts failed - add details to fallback warning
        fallback["warnings"] = fallback.get("warnings", []) + ["LLM extraction attempts failed. Using fallback parser."]
        return fallback
        
    except Exception as exc:
        fallback["warnings"] = fallback.get("warnings", []) + [f"LLM extraction failed. Fallback parsing was used. ({exc.__class__.__name__})"]
        return fallback


def apply_calculated_columns(rows: list[list[Any]], columns: list[dict[str, Any]], calculations: list[dict[str, str]]) -> tuple[list[list[Any]], list[dict[str, Any]]]:
    """
    Apply BODMAS-style calculated columns to the rows.
    calculations = [ {"name": "Result", "formula": "col_0 + col_2 - col_4"} ]
    Returns updated (rows, columns) where each calculated column is appended.
    """
    import ast, operator

    # Safe operators mapping
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _safe_eval(node, namespace):
        if isinstance(node, ast.Expression):
            return _safe_eval(node.body, namespace)
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            left = _safe_eval(node.left, namespace)
            right = _safe_eval(node.right, namespace)
            op = operators.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported operator")
            return op(left, right)
        if isinstance(node, ast.UnaryOp):
            op = operators.get(type(node.op))
            operand = _safe_eval(node.operand, namespace)
            if op is None:
                raise ValueError("Unsupported unary operator")
            return op(operand)
        if isinstance(node, ast.Name):
            return namespace.get(node.id, 0)
        if isinstance(node, ast.Call):
            # disallow function calls
            raise ValueError("Function calls not allowed")
        if isinstance(node, ast.Subscript):
            # allow simple indexing like col_0[0] (not needed here) - disallow
            raise ValueError("Subscript not allowed")
        raise ValueError("Unsupported expression")

    col_count = len(columns)
    for calc in calculations:
        name = calc.get("name") or calc.get("label") or "Calculated"
        formula = calc.get("formula", "")
        # append new column schema
        columns.append({"name": name, "type": "number", "calculated": True})

        # Pre-parse formula replacing column references like col_0, col_1
        try:
            expr_ast = ast.parse(formula, mode="eval")
        except Exception:
            # If formula invalid, append None for each row
            for row in rows:
                row.append(None)
            continue

        for row in rows:
            # Build namespace mapping col_0 .. col_N to numeric values
            namespace = {}
            for idx in range(col_count):
                var = f"col_{idx}"
                try:
                    val = row[idx]
                    namespace[var] = float(val) if val is not None and str(val) != "" else 0.0
                except Exception:
                    namespace[var] = 0.0

            try:
                value = _safe_eval(expr_ast, namespace)
                # Round floats to 4 decimals
                if isinstance(value, float):
                    value = round(value, 4)
                row.append(value)
            except Exception:
                row.append(None)

    return rows, columns


async def extract_large_dataset(content: str, schema: dict, chunk_size: int = 30) -> dict[str, Any]:
    """Split large content into chunks and merge LLM extraction results.
    This function will call generate_table for each chunk and concatenate rows.
    """
    # naive split by lines
    lines = content.splitlines()
    chunks = ["\n".join(lines[i:i+chunk_size]) for i in range(0, len(lines), chunk_size)]
    all_rows = []
    columns = None
    confidences = []
    warnings = []

    for i, chunk in enumerate(chunks):
        result = generate_table("CHUNK", chunk)
        if not columns and result.get("columns"):
            columns = result["columns"]
        rows = result.get("rows", [])
        all_rows.extend(rows)
        if result.get("confidence") is not None:
            confidences.append(result.get("confidence"))
        warnings.extend(result.get("warnings", []))

    return {
        "columns": columns or schema.get("columns", []),
        "rows": all_rows,
        "confidence": (sum(confidences)/len(confidences)) if confidences else None,
        "warnings": warnings,
        "total_rows": len(all_rows),
    }
