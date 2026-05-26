# AI Training — Ollama Setup & Guide

One guide for setting up the Younite AI (Ollama) on a fresh computer and day-to-day use.

---

## Setup on a New Computer

### 1. Install Ollama

1. Download the **Windows** installer from [ollama.ai](https://ollama.ai) and run it.
2. Open a **new** Command Prompt or PowerShell and run:
   ```batch
   ollama --version
   ```
   You should see something like `ollama version is 0.x.x`.

**If `ollama` is not found:** Ollama is installed but not in PATH.

- **Quick test (this session):**
  ```batch
  "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" --version
  ```
- **Add to PATH (permanent):** In PowerShell (as Administrator):
  ```powershell
  $ollamaPath = "$env:USERPROFILE\AppData\Local\Programs\Ollama"
  $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($currentPath -notlike "*$ollamaPath*") {
      [Environment]::SetEnvironmentVariable("Path", "$currentPath;$ollamaPath", "User")
  }
  ```
  Then close and reopen your terminal. Or add `%USERPROFILE%\AppData\Local\Programs\Ollama` via: Win → "Environment Variables" → User "Path" → Edit → New.

### 2. Pull the base model

```batch
ollama pull llama3.1
```

Wait for the download (~4.7GB). You can use another base (e.g. `llama3.2`, `mistral`) and pass it when training in step 4.

### 3. Create the custom Younite model

From the **project root** (where `startstream.bat` and `starttraining.bat` are):

1. Generate the Modelfile:
   ```batch
   starttraining.bat
   ```
   Or with a specific base: `starttraining.bat ollama llama3.2`

2. Create the Ollama model (required after each training run):
   ```batch
   ollama create llama3.1-younite -f kit-app-template-main\tools\ai_training\output\Modelfile
   ```
   Use `llama3.2-younite` (or your base name + `-younite`) if you used a different base.

3. Test in the terminal:
   ```batch
   ollama run llama3.1-younite
   ```
   Try: *"Show me Gothia Towers"* — you should get JSON like `{"poi_id":"...", "should_move": true}`. Type `/bye` to exit.

### 4. Run the app with your model

**This session only:**
```batch
set MODEL=llama3.1-younite
startstream.bat
```

**Permanent (Windows):** Win + Pause → Advanced system settings → Environment Variables → User variables → New → Name: `MODEL`, Value: `llama3.1-younite`. Restart terminal, then `startstream.bat`.

In the app, try the AI chat: *"Show me Gothia Towers"*, *"Tell me about Skandinavium"*. In the console you should see `[AI] Service initialized (provider=ollama, model=llama3.1-younite)`.

---

## Basic Guidance

### How it works

- **Training:** `examples.jsonl` maps user phrases to `poi_id` and `should_move`. The script builds a Modelfile; you run `ollama create ...` to create the model.
- **Runtime:** The app uses `poi_index.json` for positions and descriptions. The AI only returns `poi_id`; the orchestrator decides navigation vs. description from `should_move`.

### Important paths and files

- **Examples (training):** `tools/ai_training/data/examples.jsonl` — one JSON object per line (`input`, `response` with `poi_id` / `should_move` / `text`, optional `lang`).
- **Catalog (reference):** `tools/ai_training/data/catalog.json` — POI IDs, names, tags (for reference; positions/descriptions are in `poi_index.json` at runtime).
- **Output:** `tools/ai_training/output/Modelfile` — used by `ollama create`.

### Environment variables

| Variable         | Purpose                    | Default              |
|------------------|----------------------------|----------------------|
| `MODEL`          | Model name                 | `llama3.1`           |
| `AI_PROVIDER`    | Provider                   | `ollama`             |
| `OLLAMA_BASE_URL`| Ollama API base            | `http://localhost:11434` |

### Updating the model

1. Edit `tools/ai_training/data/examples.jsonl` (add or fix lines).
2. From project root: `starttraining.bat`
3. Recreate the model:
   ```batch
   ollama rm llama3.1-younite
   ollama create llama3.1-younite -f kit-app-template-main\tools\ai_training\output\Modelfile
   ```
4. Run the app with `set MODEL=llama3.1-younite` (or your model name).

### Running training only (no Ollama create)

From project root:
```batch
starttraining.bat
```
Or from `kit-app-template-main`: `python tools\ai_training\train.py`. To only convert, no create: `python tools\ai_training\train.py --convert-only`.

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| `ollama` not found | New terminal after install; or use full path above; or add Ollama to PATH (see step 1). |
| Connection refused | Ollama must be running (service or `ollama serve`). Check http://localhost:11434 or `ollama list`. |
| Model not found in app | `ollama list` — confirm `llama3.1-younite` exists. Set `MODEL=llama3.1-younite` before `startstream.bat`. |
| Wrong or no AI responses | Check console for `[AI]` errors; confirm `MODEL` and provider; retrain and run `ollama create` again. |
| Invalid JSON in examples | Fix the reported line in `tools/ai_training/data/examples.jsonl`, save, run `starttraining.bat` again. |

---

## Quick reference

```batch
REM Fresh machine: install Ollama, then in a NEW terminal:
ollama pull llama3.1

REM From project root:
starttraining.bat
ollama create llama3.1-younite -f kit-app-template-main\tools\ai_training\output\Modelfile

REM Test model
ollama run llama3.1-younite

REM Run app with your model
set MODEL=llama3.1-younite
startstream.bat
```
