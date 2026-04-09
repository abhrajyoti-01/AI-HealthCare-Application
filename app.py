from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from chatbot import HealthcareChatbot


load_dotenv()

app = Flask(__name__)


def _parse_model_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_flag(name: str, default: str = "0") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


chatbot = HealthcareChatbot(
    openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
    huggingface_api_key=os.getenv("HUGGINGFACE_API_KEY", "").strip(),
    openrouter_model=os.getenv("OPENROUTER_MODEL", "google/gemma-3-4b-it:free"),
    huggingface_model=os.getenv("HUGGINGFACE_MODEL", "google/flan-t5-large"),
    openrouter_fallback_models=_parse_model_list(
        os.getenv(
            "OPENROUTER_FALLBACK_MODELS",
            (
                "google/gemma-3n-e4b-it:free,google/gemma-3n-e2b-it:free,"
                "liquid/lfm-2.5-1.2b-instruct:free,liquid/lfm-2.5-1.2b-thinking:free,"
                "nvidia/nemotron-nano-9b-v2:free,arcee-ai/trinity-mini:free,"
                "arcee-ai/trinity-large-preview:free,nvidia/nemotron-3-super-120b-a12b:free,"
                "google/gemma-3-12b-it:free"
            ),
        )
    ),
    huggingface_fallback_models=_parse_model_list(
        os.getenv(
            "HUGGINGFACE_FALLBACK_MODELS",
            "mistralai/Mistral-7B-Instruct-v0.3,Qwen/Qwen2.5-7B-Instruct",
        )
    ),
)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/status")
def status() -> Any:
    return jsonify(chatbot.get_status())


@app.post("/api/chat")
def chat() -> Any:
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    history_raw = payload.get("history", [])

    history: List[Dict[str, str]] = []
    if isinstance(history_raw, list):
        for item in history_raw[-12:]:
            if isinstance(item, dict):
                role = str(item.get("role", "")).strip().lower()
                content = str(item.get("content", "")).strip()
                if role in {"user", "assistant"} and content:
                    history.append({"role": role, "content": content})

    if not message:
        return jsonify({"error": "Please enter a message."}), 400

    reply, metadata = chatbot.generate_response(message, history)

    return jsonify(
        {
            "reply": reply,
            "provider": metadata.get("provider", "fallback"),
            "model": metadata.get("model", "fallback"),
            "safety": metadata.get("safety", "normal"),
            "reason": metadata.get("reason", ""),
        }
    )


if __name__ == "__main__":
    debug_mode = _env_flag("FLASK_DEBUG", "0")
    use_reloader = _env_flag("FLASK_USE_RELOADER", "0")
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=debug_mode,
        use_reloader=use_reloader,
    )
