# Frontend API How-To

## Endpoints
- `POST /chat` for non-streaming responses
- `POST /chat/stream` for SSE streaming responses

## Required request fields
- `prompt` (string)
- `session_id` (string, required)
- `language` (`"sv"` or `"en"`)

## Non-streaming example (fetch)
```js
const payload = {
  prompt: "Vad heter du?",
  session_id: "your-session-id",
  language: "sv",
};

const res = await fetch("https://esbst.goteborg.se/citiverse/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

const data = await res.json();
// data.response_text, data.session_id, data.session_new
```

## Streaming example (SSE)
```js
const payload = {
  prompt: "Hello!",
  session_id: "your-session-id",
  language: "en",
};

const res = await fetch("https://esbst.goteborg.se/citiverse/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();

let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  // parse SSE chunks
  const parts = buffer.split("\n\n");
  buffer = parts.pop() || "";
  for (const part of parts) {
    // event: meta/data/final/done
    // data: ...
  }
}
```

## Response shape (non-streaming)
```json
{
  "response_text": "…",
  "results": [],
  "errors": [],
  "session_id": "your-session-id",
  "session_new": false
}
```

## Session handling
- Reuse `session_id` to keep context and language.
- To close a session:
```json
{ "action": "close_session", "session_id": "your-session-id" }
```

## Common errors
- 400: missing `session_id` or `language`
- 422: validation errors (invalid types or empty prompt)
