import os
import sys
import traceback
from io import StringIO
from typing import List

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str


class ErrorAnalysis(BaseModel):
    error_lines: List[int]


def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code, {})
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


def analyze_error_with_ai(code: str, traceback_text: str) -> List[int]:
    token = os.environ["AIPIPE_TOKEN"]

    prompt = f"""
Analyze the Python code and traceback below.

Identify the exact line number or line numbers where the error occurred.

Return ONLY valid JSON in this format:
{{"error_lines":[3]}}

CODE:
{code}

TRACEBACK:
{traceback_text}
"""

    response = httpx.post(
        "https://aipipe.org/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-nano",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {
                "type": "json_object"
            },
            "temperature": 0
        },
        timeout=20
    )

    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    result = ErrorAnalysis.model_validate_json(content)

    return result.error_lines


@app.post("/code-interpreter")
def code_interpreter(request: CodeRequest):
    execution = execute_python_code(request.code)

    if execution["success"]:
        return {
            "error": [],
            "result": execution["output"]
        }

    return {
        "error": analyze_error_with_ai(
            request.code,
            execution["output"]
        ),
        "result": execution["output"]
    }