import os
import json
import re
import carb
import carb.eventdispatcher
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Callable


class _LLMClient:
    """Optional HTTP client for OpenAI-compatible or Ollama endpoints.

    If any request fails, callers should handle fallback behavior.
    """

    def __init__(self):
        # Default to Ollama for local dev if not explicitly set
        self.provider = os.getenv("AI_PROVIDER", "ollama").lower()
        self.model = os.getenv("MODEL", "llama3.1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def is_configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.openai_api_key)
        if self.provider == "ollama":
            return True
        return False

    def chat(self, system: str, messages: list[dict]) -> str:
        try:
            if self.provider == "openai":
                url = f"{self.openai_base}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                }
                body = {"model": self.model, "messages": messages, "temperature": 0.2}
                req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
                return data["choices"][0]["message"]["content"]
            else:
                url = f"{self.ollama_base}/api/chat"
                headers = {"Content-Type": "application/json"}
                body = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0.2}}
                req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
                return data.get("message", {}).get("content", "")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"[AI] LLM request failed: {e}")
            return ""


class AIService:
    """
    Copied from the old monolithic extension.

    Important: This service emits `teleportToSpawnpoint` events when it decides to move.
    Those are handled by StageCore (Camera/Teleport).
    """

    def __init__(self, teleport_to_spawnpoint_cb: Optional[Callable[[str], bool]] = None):
        self._ed = carb.eventdispatcher.get_eventdispatcher()
        self._llm = _LLMClient()
        print(f"[AI] Service initialized (provider={self._llm.provider or 'none'}, model={self._llm.model})")
        if self._llm.provider == "ollama":
            print(f"[AI] Using Ollama at {self._llm.ollama_base}")
        elif self._llm.provider == "openai":
            print(f"[AI] Using OpenAI-compatible endpoint at {self._llm.openai_base}")
        self._poi_by_id: Dict[str, Dict[str, Any]] = self._load_poi_index()
        if not self._poi_by_id:
            print("[AI] ⚠️ Could not load POI index; descriptions will be minimal")
        self._session_memory: Dict[str, Dict[str, Any]] = {}
        self._teleport_cb: Optional[Callable[[str], bool]] = teleport_to_spawnpoint_cb

    def _emit(self, event_name: str, payload: dict):
        try:
            import omni.kit.app as _kit_app
            _kit_app.register_event_alias(carb.events.type_from_string(event_name), event_name)
        except Exception:
            pass
        try:
            if event_name != "ai.chat.response":
                print(f"[AI] Emitting local event: {event_name} -> {payload}")
            self._ed.dispatch_event(event_name, payload)
        except Exception as e:
            print(f"[AI] emit failed: {event_name}: {e}")

    def _load_poi_index(self) -> Dict[str, Dict[str, Any]]:
        def _try_load(path: str) -> Optional[Dict[str, Dict[str, Any]]]:
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    by_id: Dict[str, Dict[str, Any]] = {}
                    if isinstance(data, list):
                        for item in data:
                            poi_id = (item or {}).get("id")
                            if isinstance(poi_id, str):
                                key = str(poi_id).strip().lower()
                                by_id[key] = item
                    return by_id
            except Exception as e:
                print(f"[AI] POI index load attempt failed from {path}: {e}")
            return None

        candidates = []
        try:
            base_dir = os.path.dirname(__file__)
            candidates.append(os.path.normpath(os.path.join(base_dir, "../../../data/poi_index.json")))
            candidates.append(os.path.normpath(os.path.join(base_dir, "../../../../data/poi_index.json")))
            candidates.append(os.path.normpath(os.path.join(base_dir, "../../../../../data/poi_index.json")))
            candidates.append(os.path.normpath(os.path.join(base_dir, "../../../../../../data/poi_index.json")))
        except Exception:
            pass
        for p in candidates:
            res = _try_load(p)
            if res is not None:
                return res

        try:
            current = os.path.abspath(os.path.dirname(__file__))
            for _ in range(10):
                candidate = os.path.join(current, "source", "data", "poi_index.json")
                res = _try_load(candidate)
                if res is not None:
                    return res
                candidate2 = os.path.join(current, "data", "poi_index.json")
                res2 = _try_load(candidate2)
                if res2 is not None:
                    return res2
                parent = os.path.dirname(current)
                if parent == current:
                    break
                current = parent
        except Exception as e:
            print(f"[AI] POI index ascending search failed: {e}")

        print("[AI] ⚠️ Could not locate poi_index.json; falling back to minimal responses")
        return {}

    def _get_poi_description(self, poi_id: str, lang: str = "en") -> str:
        item = self._poi_by_id.get(poi_id) or self._poi_by_id.get(str(poi_id).strip().lower()) or {}
        names = (item.get("names") or {})
        descs = (item.get("descriptions") or {})
        name_str = names.get(lang) or names.get("en") or poi_id
        desc_str = descs.get(lang) or descs.get("en") or ""
        if desc_str:
            return f"{name_str}: {desc_str}"
        return name_str

    def _spawnpoint_for_poi(self, poi_id: str) -> str:
        return f"spawnpoint_{poi_id}"

    def _default_guide_text(self) -> str:
        return ("I'm a tour guide for Gothenburg. I can help you explore locations like Gothia Towers, "
                "Skandinavium, or the Art Museum. What would you like to see?")

    def process_chat_request(self, text: str, session_id: str):
        try:
            print(f"[AI] Service received chat: '{text}' (session: {session_id})")
            text = (text or "").strip()
            if not text:
                return

            try:
                self._emit("ai.chat.typing", {"sessionId": session_id})
            except Exception:
                pass

            raw = ""
            answer_text: Optional[str] = None
            parsed: Dict[str, Any] = {}

            memory = self._session_memory.get(session_id) or {}
            last_poi_id = str(memory.get("last_poi_id") or "").strip()

            if self._llm.is_configured():
                system = (
                    "You are a helpful tour guide assistant for Gothenburg. "
                    "If the user requests to go somewhere, respond with JSON like "
                    '{"poi_id":"<poi_id>","should_move":true}. If they ask about a place, '
                    'respond with {"poi_id":"<poi_id>","should_move":false}. If the query is unrelated '
                    'to places, respond with {"poi_id": null, "text": "<short guide-style default>"}. '
                    f"Context: last_poi_id={last_poi_id or 'none'}. If the user confirms moving without naming a place, "
                    'respond with {"poi_id":"last_poi_id","should_move":true} (only if last_poi_id is known).'
                )
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ]
                raw = self._llm.chat(system, messages) or ""
                if raw:
                    print(f"[AI] LLM raw response (truncated): {str(raw)[:200]}")
                try:
                    parsed = json.loads(raw) if raw.strip().startswith("{") else {}
                except Exception:
                    parsed = {}
                if not parsed:
                    answer_text = raw.strip() or None
                    if answer_text and ("poi_id" in answer_text or "poi-id" in answer_text):
                        try:
                            cleaned = answer_text
                            cleaned = cleaned.replace('\\"', '"')
                            cleaned = cleaned.replace("poi-id", "poi_id")
                            cleaned = cleaned.replace("should-move", "should_move")
                            if cleaned.strip().startswith("{") and cleaned.strip().endswith("}"):
                                parsed = json.loads(cleaned)
                        except Exception:
                            try:
                                pid_match = re.search(r'poi[_-]id"\s*:\s*"([^"]+)"', cleaned)
                                move_match = re.search(r'should[_-]move"\s*:\s*(true|false)', cleaned, re.IGNORECASE)
                                extracted: Dict[str, Any] = {}
                                if pid_match:
                                    pid_raw = pid_match.group(1).strip().lower()
                                    extracted["poi_id"] = pid_raw.replace("-", "_")
                                if move_match:
                                    extracted["should_move"] = move_match.group(1).lower() == "true"
                                if extracted:
                                    parsed = extracted
                            except Exception:
                                pass

            if not raw and not answer_text and not parsed:
                parsed = {"poi_id": None, "text": self._default_guide_text()}

            poi_id = parsed.get("poi_id") if isinstance(parsed, dict) else None
            should_move = parsed.get("should_move") if isinstance(parsed, dict) else None
            provided_text = parsed.get("text") if isinstance(parsed, dict) else None

            try:
                if isinstance(poi_id, str) and poi_id.strip().lower() == "last_poi_id":
                    mem = self._session_memory.get(session_id) if hasattr(self, "_session_memory") else None
                    stored = (mem or {}).get("last_poi_id") if isinstance(mem, dict) else None
                    poi_id = stored or None
            except Exception:
                pass

            if poi_id is None or poi_id is False or str(poi_id).lower() == "null":
                reply = provided_text or self._default_guide_text()
                payload = {"sessionId": session_id, "text": str(reply)}
                print(f"[AI] Final answer (default): {reply}")
                self._emit("ai.chat.response", payload)
                self._emit("ai.chat.done", {"sessionId": session_id})
                return

            poi_id_str = str(poi_id).strip().lower().replace("-", "_")
            description = self._get_poi_description(poi_id_str, lang="en")
            spawnpoint_name = self._spawnpoint_for_poi(poi_id_str)
            try:
                self._session_memory[session_id] = {"last_poi_id": poi_id_str}
            except Exception:
                pass

            if str(should_move).lower() == "true" or bool(should_move):
                # Teleport is performed by other extensions listening to this event
                try:
                    self._emit("teleportToSpawnpoint", {"spawnpointName": spawnpoint_name, "poiId": poi_id_str})
                except Exception as e:
                    print(f"[AI] Teleport emit failed: {e}")
                reply = description
                resp_payload = {
                    "sessionId": session_id,
                    "text": reply,
                    "poiId": poi_id_str,
                    "shouldMove": True,
                    "spawnpointName": spawnpoint_name,
                }
                print(f"[AI] Final answer (move now): {reply} -> {spawnpoint_name}")
                self._emit("ai.chat.response", resp_payload)
                self._emit("ai.chat.done", {"sessionId": session_id})
                return

            reply = description
            resp_payload = {
                "sessionId": session_id,
                "text": reply,
                "poiId": poi_id_str,
                "shouldMove": False,
                "spawnpointName": spawnpoint_name,
                "suggestedAction": "moveToLocation",
            }
            print(f"[AI] Final answer (no move): {reply} (suggest move -> {spawnpoint_name})")
            self._emit("ai.chat.response", resp_payload)
            self._emit("ai.chat.done", {"sessionId": session_id})
        except Exception as e:
            print(f"[AI] Service error: {e}")

