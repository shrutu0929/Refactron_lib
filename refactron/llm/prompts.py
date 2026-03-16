"""Prompt templates for LLM code suggestions."""

SYSTEM_PROMPT = """You are an expert software architect and code refactoring specialist.
Your goal is to analyze code issues and provide safe, idiomatic, and performance-optimized fixes.

RESPONSE FORMAT:
You must output ONLY valid JSON.
- Escape all double quotes inside strings with backslash (e.g. \\").
- Do not use trailing commas.
- Do not output markdown code blocks, just the raw JSON object.
- Ensure newlines in strings are escaped as \\n.

Output JSON structure:
{
    "explanation": "Brief explanation of the fix",
    "proposed_code": "The complete fixed code block",
    "reasoning": "Step-by-step reasoning for the change",
    "confidence_score": "Float between 0.0 and 1.0 representing your confidence in this fix"
}
"""

SUGGESTION_PROMPT = """
Fix the following code issue:

Issue: {issue_message}
File: {file_path}:{line_number}
Severity: {severity}

Original Code:
```python
{original_code}
```

Relevant Context (RAG):
{rag_context}

Provide a fix that resolves the issue while maintaining consistency with the codebase context.
IMPORTANT: Add inline comments ONLY where absolutely necessary to explain complex logic.
Do NOT add comments for obvious code or after every line.
"""

SAFETY_CHECK_PROMPT = """
Analyze the following code patch for safety risks:

```python
{proposed_code}
```

Identify any:
1. Syntax errors
2. Security vulnerabilities
3. Dangerous side effects (file implementation, network calls)
4. Breaking changes

Output valid JSON:
{
    "safe": boolean,
    "risk_score": float (0.0-1.0),
    "risk_score": float (0.0-1.0),
    "issues": [list of strings]
}
"""

DOCUMENTATION_PROMPT = """
Analyze the following Python code and generate a comprehensive MARKDOWN documentation file.

Original Code:
```python
{original_code}
```

Relevant Context (RAG):
{rag_context}

Instructions:
1. Create a professional Developer Guide in Markdown format.
2. Include:
    - Module Overview
    - Key Classes and Functions (with signatures and descriptions)
    - Usage Examples
    - Logic Flow/Algorithm Explanation
    - **Mermaid Diagram**: Create a `graph TD` flow chart representing the logic/algorithm.
3. Do NOT simply copy the code. Explain it.
4. Use the specific delimiters below for your response.

RESPONSE FORMAT:
@@@EXPLANATION@@@
Brief summary of documentation created
@@@CONFIDENCE@@@
Float between 0.0 and 1.0 (e.g. 0.95)
@@@MARKDOWN@@@
The complete Markdown documentation content including the mermaid diagram
@@@END@@@
"""

BATCH_TRIAGE_SYSTEM_PROMPT = """\
You are an expert software architect and code refactoring specialist.
Your goal is to evaluate multiple code issues in a single file and determine their validity.

RESPONSE FORMAT:
You must output ONLY valid JSON.
- Escape all double quotes inside strings with backslash (e.g. \\").
- Do not use trailing commas.
- Do not output markdown code blocks, just the raw JSON object.

Output JSON structure must be a simple dictionary mapping issue IDs to confidence scores:
{
    "issue_1": 0.85,
    "issue_2": 0.1
}
"""

BATCH_TRIAGE_PROMPT = """
You are a code triage expert. Evaluate the following list of code issues found in a
single file and determine the confidence that each is a true positive (requiring
fixing) rather than a false positive.

File Source Code:
```
{source_code}
```

Relevant Context (RAG):
{rag_context}

Issues to evaluate:
{issues_json}

Return ONLY a JSON map where the keys are the issue IDs and the values are the
confidence scores (float between 0.0 and 1.0).
Do NOT return anything except the JSON object.
"""

DOCSTRING_PROMPT = """
Analyze the following Python code and generate a high-quality Google-style docstring.

Code:
```python
{code}
```

Instructions:
1. Provide ONLY the docstring itself.
2. Include a summary, Args section (with types), and Returns section.
3. Keep it concise and professional.
"""

ISSUE_EXPLANATION_PROMPT = """
Explain the following code issue in natural language for a developer.

Issue: {issue_message}
Code Snippet:
```python
{code_snippet}
```

Context:
{context}

Goal:
Explain WHY this is an issue and WHAT the potential impact is. Keep it brief and helpful.
"""

CODE_IMPROVEMENT_PROMPT = """
Analyze the following code for potential naming and structural improvements.

Code:
```python
{code}
```

Identify:
1. Variable names that could be more descriptive.
2. Logic blocks that should be extracted into separate methods.

Output ONLY JSON in this format:
{{
    "variable_renames": {{"old_name": "new_name"}},
    "method_extractions": [
        {{
            "name": "suggested_method_name",
            "lines": [start_line, end_line],
            "reason": "why extract this"
        }}
    ]
}}
"""

SEMANTIC_SIMILARITY_PROMPT = """
Compare these two code fragments and determine if they are semantically similar (i.e., they do the same thing using different syntax or names).

Fragment 1:
```python
{code1}
```

Fragment 2:
```python
{code2}
```

Output ONLY a JSON object with:
{{
    "similarity_score": float (0.0 to 1.0),
    "reasoning": "Brief explanation of structural similarity"
}}
"""
