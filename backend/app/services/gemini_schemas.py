"""JSON schemas for Gemini structured output (response_json_schema)."""

from __future__ import annotations

# Gemini API supports a subset of JSON Schema — keep types flat and explicit.

KYC_ANSWER_RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "serial_no": {"type": "integer"},
                    "answer": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["title", "url"],
                        },
                    },
                },
                "required": ["serial_no", "answer", "sources"],
            },
        }
    },
    "required": ["items"],
}

KYC_VALIDATION_RESPONSE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "serial_no": {"type": "integer"},
                    "validation": {"type": "string", "enum": ["Yes", "No"]},
                    "validation_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "document": {"type": "string"},
                                "page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                                "excerpt": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                "url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            },
                            "required": ["document"],
                        },
                    },
                },
                "required": ["serial_no", "validation", "validation_sources"],
            },
        }
    },
    "required": ["items"],
}
