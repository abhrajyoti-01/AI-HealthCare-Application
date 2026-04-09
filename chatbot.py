from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re

import requests


EMERGENCY_KEYWORDS = {
    "chest pain",
    "trouble breathing",
    "difficulty breathing",
    "severe bleeding",
    "passed out",
    "unconscious",
    "stroke",
    "seizure",
    "suicidal",
    "overdose",
}

HEALTHCARE_DISCLAIMER = "Disclaimer: This application provides health information for guidance purposes only and is not a substitute for professional medical advice, diagnosis, or treatment."

SYSTEM_PROMPT = (
    "You are a clinical-grade AI Healthcare Assistant. You provide structured, professional symptom triage and wellness guidance. "
    "You must ALWAYS respond using the following format:\n\n"
    "Clinical Impression: A brief, cautious overview of what the symptoms may indicate.\n"
    "Possibilities: A broad, non-diagnostic list of potential causes (never state a single definitive diagnosis).\n"
    "Red Flags: Any symptoms in the user's description (or commonly associated) that would require immediate emergency care. If none, state 'None identified based on current information.'\n"
    "Recommended Action: Clear, actionable next steps (e.g., rest, monitor, schedule a doctor visit, or seek emergency care).\n\n"
    "SAFETY RULES:\n"
    "1. NEVER provide a definitive diagnosis. Use language like 'may be associated with' or 'could suggest'.\n"
    "2. NEVER prescribe specific medications. Only suggest general over-the-counter options when appropriate.\n"
    "3. If symptoms suggest a life-threatening condition, strongly and immediately advise calling emergency services.\n"
    "4. Keep the full response under 200 words. Be concise, professional, and empathetic.\n"
    "5. Consider the full conversation history to build a continuous clinical picture, like a real consultation.\n"
    f"6. The absolute final sentence of EVERY response MUST BE exactly: '{HEALTHCARE_DISCLAIMER}'"
)


class HealthcareChatbot:
    def __init__(
        self,
        openrouter_api_key: str = "",
        huggingface_api_key: str = "",
        openrouter_model: str = "google/gemma-3-4b-it:free",
        huggingface_model: str = "google/flan-t5-large",
        openrouter_fallback_models: List[str] | None = None,
        huggingface_fallback_models: List[str] | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.openrouter_api_key = openrouter_api_key
        self.huggingface_api_key = huggingface_api_key
        self.openrouter_models = self._unique_models(
            [openrouter_model, *(openrouter_fallback_models or [])]
        )
        self.huggingface_models = self._unique_models(
            [huggingface_model, *(huggingface_fallback_models or [])]
        )
        self.openrouter_model = (
            self.openrouter_models[0] if self.openrouter_models else openrouter_model
        )
        self.huggingface_model = (
            self.huggingface_models[0] if self.huggingface_models else huggingface_model
        )
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _unique_models(models: List[str]) -> List[str]:
        seen = set()
        cleaned: List[str] = []
        for model in models:
            item = model.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            cleaned.append(item)
        return cleaned

    def get_status(self) -> Dict[str, Any]:
        active_provider = "fallback"
        if self.openrouter_api_key:
            active_provider = "openrouter"
        elif self.huggingface_api_key:
            active_provider = "huggingface"

        return {
            "openrouterConfigured": bool(self.openrouter_api_key),
            "huggingfaceConfigured": bool(self.huggingface_api_key),
            "activeProvider": active_provider,
            "openrouterModel": self.openrouter_model,
            "openrouterFallbackModels": self.openrouter_models[1:],
            "huggingfaceModel": self.huggingface_model,
            "huggingfaceFallbackModels": self.huggingface_models[1:],
        }

    def _is_emergency(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in EMERGENCY_KEYWORDS)

    def _build_prompt(
        self, user_message: str, history: List[Dict[str, str]] | None
    ) -> str:
        history = history or []
        recent_history = history[-6:]
        conversation_lines: List[str] = []

        for turn in recent_history:
            role = "User" if turn.get("role") == "user" else "Assistant"
            content = re.sub(r"\s+", " ", turn.get("content", "")).strip()
            conversation_lines.append(f"{role}: {content}")

        conversation_lines.append(f"User: {user_message.strip()}")
        conversation_text = "\n".join(conversation_lines)

        instruction = SYSTEM_PROMPT

        return f"{instruction}\n\nConversation:\n{conversation_text}\nAssistant:"

    def _build_openrouter_messages(
        self,
        user_message: str,
        history: List[Dict[str, str]] | None,
        include_system: bool = True,
    ) -> List[Dict[str, str]]:
        system_prompt = SYSTEM_PROMPT

        messages: List[Dict[str, str]] = []
        if include_system:
            messages.append({"role": "system", "content": system_prompt})

        for turn in (history or [])[-8:]:
            role = "user" if turn.get("role") == "user" else "assistant"
            content = re.sub(r"\s+", " ", turn.get("content", "")).strip()
            if content:
                messages.append({"role": role, "content": content})

        if include_system:
            messages.append({"role": "user", "content": user_message})
        else:
            messages.append(
                {
                    "role": "user",
                    "content": f"Instruction:\n{system_prompt}\n\nUser message:\n{user_message}",
                }
            )

        return messages

    def _ensure_disclaimer(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return HEALTHCARE_DISCLAIMER

        # Remove one or more trailing disclaimer copies, then append exactly one.
        trailing_disclaimer_pattern = re.compile(
            rf"(?:{re.escape(HEALTHCARE_DISCLAIMER)}\s*)+$",
            re.IGNORECASE,
        )
        base_text = trailing_disclaimer_pattern.sub("", normalized).strip()

        if not base_text:
            return HEALTHCARE_DISCLAIMER

        if base_text.endswith((".", "!", "?")):
            return f"{base_text} {HEALTHCARE_DISCLAIMER}"
        return f"{base_text}. {HEALTHCARE_DISCLAIMER}"

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    message = error.get("message") or error.get("code")
                    if message:
                        return str(message)
                if isinstance(error, str) and error:
                    return error
                message = payload.get("message")
                if isinstance(message, str) and message:
                    return message
        except ValueError:
            pass

        text = response.text.strip()
        if text:
            return text[:220]
        return f"HTTP {response.status_code}"

    @staticmethod
    def _extract_chat_completion_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""

        choices = data.get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            return ""

        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return ""

        return str(message.get("content", "")).strip()

    @staticmethod
    def _extract_hf_inference_text(data: Any) -> str:
        if isinstance(data, list) and data:
            item = data[0]
            if isinstance(item, dict):
                return str(item.get("generated_text", "")).strip()

        if isinstance(data, dict):
            generated = str(data.get("generated_text", "")).strip()
            if generated:
                return generated

        return ""

    def _query_openrouter(
        self, user_message: str, history: List[Dict[str, str]] | None
    ) -> Tuple[str, str, str]:
        if not self.openrouter_api_key:
            return "", "", "OpenRouter key missing"

        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "Healthcare AI Assistant",
        }

        last_error = ""

        for model_name in self.openrouter_models:
            base_payload = {
                "model": model_name,
                "temperature": 0.6,
                "max_tokens": 260,
            }

            try:
                payload = {
                    **base_payload,
                    "messages": self._build_openrouter_messages(
                        user_message, history, include_system=True
                    ),
                }

                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )

                if response.status_code >= 400:
                    # Some providers (for example Gemma via Google AI Studio) reject system/developer instructions.
                    if (
                        response.status_code == 400
                        and "developer instruction is not enabled"
                        in response.text.lower()
                    ):
                        payload = {
                            **base_payload,
                            "messages": self._build_openrouter_messages(
                                user_message,
                                history,
                                include_system=False,
                            ),
                        }
                        response = requests.post(
                            endpoint,
                            headers=headers,
                            json=payload,
                            timeout=self.timeout_seconds,
                        )

                    error_message = self._extract_error_message(response)
                    if response.status_code >= 400:
                        last_error = f"OpenRouter {response.status_code} ({model_name}): {error_message}"
                        if response.status_code in {401, 403}:
                            break
                        continue

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    last_error = f"OpenRouter empty choices ({model_name})"
                    continue

                message = choices[0].get("message", {})
                content = str(message.get("content", "")).strip()
                if content:
                    return content, model_name, ""

                last_error = f"OpenRouter empty content ({model_name})"
            except requests.RequestException as exc:
                last_error = (
                    f"OpenRouter request error ({model_name}): {exc.__class__.__name__}"
                )
                continue

        return "", "", last_error or "OpenRouter request failed"

    def _query_huggingface(
        self, user_message: str, history: List[Dict[str, str]] | None
    ) -> Tuple[str, str, str]:
        if not self.huggingface_api_key:
            return "", "", "Hugging Face key missing"

        chat_endpoint = "https://router.huggingface.co/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.huggingface_api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""

        for model_name in self.huggingface_models:
            chat_payload = {
                "model": model_name,
                "messages": self._build_openrouter_messages(user_message, history),
                "temperature": 0.5,
                "max_tokens": 260,
            }

            chat_error = ""

            try:
                response = requests.post(
                    chat_endpoint,
                    headers=headers,
                    json=chat_payload,
                    timeout=self.timeout_seconds,
                )

                if response.status_code < 400:
                    data = response.json()
                    content = self._extract_chat_completion_text(data)
                    if content:
                        return content, model_name, ""
                    chat_error = f"Hugging Face chat empty content ({model_name})"
                else:
                    error_message = self._extract_error_message(response)
                    chat_error = f"Hugging Face chat {response.status_code} ({model_name}): {error_message}"
            except requests.RequestException as exc:
                chat_error = f"Hugging Face chat request error ({model_name}): {exc.__class__.__name__}"

            inference_endpoint = (
                f"https://router.huggingface.co/hf-inference/models/{model_name}"
            )
            inference_payload = {
                "inputs": self._build_prompt(user_message, history),
                "parameters": {
                    "max_new_tokens": 220,
                    "temperature": 0.5,
                    "top_p": 0.92,
                    "return_full_text": False,
                },
                "options": {
                    "wait_for_model": True,
                },
            }

            try:
                inference_response = requests.post(
                    inference_endpoint,
                    headers=headers,
                    json=inference_payload,
                    timeout=self.timeout_seconds,
                )

                if inference_response.status_code < 400:
                    data = inference_response.json()
                    content = self._extract_hf_inference_text(data)
                    if content:
                        return content, model_name, ""

                    inference_error = (
                        f"Hugging Face hf-inference empty content ({model_name})"
                    )
                else:
                    error_message = self._extract_error_message(inference_response)
                    inference_error = (
                        f"Hugging Face hf-inference {inference_response.status_code} "
                        f"({model_name}): {error_message}"
                    )
            except requests.RequestException as exc:
                inference_error = (
                    f"Hugging Face hf-inference request error ({model_name}): "
                    f"{exc.__class__.__name__}"
                )

            if chat_error and inference_error:
                last_error = f"{chat_error}; {inference_error}"
            else:
                last_error = chat_error or inference_error

            lower_error = last_error.lower()
            if "403" in lower_error and "insufficient permissions" in lower_error:
                break

        return "", "", last_error or "Hugging Face request failed"

    def _fallback_response(self, user_message: str) -> str:
        lowered = user_message.lower()

        if any(token in lowered for token in ["fever", "temperature"]):
            return (
                "For mild fever, rest, hydrate well, and monitor temperature. "
                "Seek medical care if fever is high, lasts more than 2-3 days, or appears with severe symptoms. "
                "This is educational information only, not medical advice."
            )

        if any(token in lowered for token in ["cough", "cold", "sore throat"]):
            return (
                "For common cold-like symptoms, hydrate, rest, and avoid smoke exposure. "
                "See a doctor if breathing worsens, symptoms persist, or you have high-risk conditions. "
                "This is educational information only, not medical advice."
            )

        return (
            "I can share general health education and triage guidance. "
            "Please describe your symptoms, duration, and any major risk factors in simple language. "
            "This is educational information only, not medical advice."
        )

    def generate_response(
        self, user_message: str, history: List[Dict[str, str]] | None = None
    ) -> Tuple[str, Dict[str, str]]:
        cleaned = re.sub(r"\s+", " ", user_message).strip()
        if not cleaned:
            return (
                "Please share your symptoms or healthcare question in one short sentence.",
                {
                    "provider": "fallback",
                    "model": "fallback",
                    "safety": "normal",
                    "reason": "Empty input",
                },
            )

        if self._is_emergency(cleaned):
            return (
                "Your message may include emergency warning signs. "
                "Please call emergency services immediately or go to the nearest emergency department now. "
                "This is educational information only, not medical advice.",
                {
                    "provider": "safety",
                    "model": "safety",
                    "safety": "emergency",
                    "reason": "Emergency keyword detected",
                },
            )

        provider_used = "fallback"
        model_used = "fallback"
        response_text = ""
        reason = ""

        if self.openrouter_api_key:
            response_text, selected_model, openrouter_error = self._query_openrouter(
                cleaned, history
            )
            if response_text:
                provider_used = "openrouter"
                model_used = selected_model
            elif openrouter_error:
                reason = openrouter_error

        else:
            reason = "OpenRouter key missing"

        if not response_text and self.huggingface_api_key:
            response_text, selected_model, huggingface_error = self._query_huggingface(
                cleaned, history
            )
            if response_text:
                provider_used = "huggingface"
                model_used = selected_model
                reason = ""
            elif huggingface_error:
                if reason:
                    reason = f"{reason}; {huggingface_error}"
                else:
                    reason = huggingface_error

        elif not response_text and not self.huggingface_api_key:
            if reason:
                reason = f"{reason}; Hugging Face key missing"
            else:
                reason = "Hugging Face key missing"

        if not response_text:
            response_text = self._fallback_response(cleaned)
            provider_used = "fallback"
            model_used = "fallback"

        response_text = self._ensure_disclaimer(response_text)
        return response_text, {
            "provider": provider_used,
            "model": model_used,
            "safety": "normal",
            "reason": reason[:500],
        }
