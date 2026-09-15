# Deployment Guide — Hugging Face Spaces (Gradio SDK — FREE)

Deploy the **Buy or Wait?** AI Financial Agent as a free, always-on Gradio chat app on Hugging Face Spaces.

> **No Docker required.** Uses the Gradio SDK — completely free tier.

---

## Prerequisites

- A free account at [huggingface.co](https://huggingface.co)
- Git installed locally
- Your `GROQ_API_KEY` from [console.groq.com](https://console.groq.com)

---

## Step 1 — Create a New Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space)
2. Fill in:
   - **Space name**: `buy-or-wait`
   - **License**: MIT
   - **SDK**: **Gradio** ← select this (it's FREE)
   - **Visibility**: Public
3. Click **Create Space**

---

## Step 2 — Add Your Groq API Key as a Secret

1. In your Space, go to **Settings → Variables and Secrets**
2. Under **Repository Secrets**, click **New secret**
3. Name: `GROQ_API_KEY`
4. Value: your key (starts with `gsk_...`)
5. Click **Save**

> Your key is injected as an env variable at runtime — never stored in code or committed to git.

---

## Step 3 — Push This Repo to HF Spaces

HF Spaces is just a git remote. Add it and push:

```bash
# Add HF Spaces as a remote (replace YOUR_USERNAME)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/buy-or-wait

# Push
git push hf main
```

> First push may ask for your HF username + password (or access token from hf.co/settings/tokens).

---

## Step 4 — Wait for the Build (~2 min)

1. Go to: `https://huggingface.co/spaces/YOUR_USERNAME/buy-or-wait`
2. You'll see a **Building** badge — it turns **Running** in about 2 minutes
3. HF Spaces reads `requirements.txt` and `app.py` automatically

---

## Step 5 — Use the App

Once running, try these in the chat:

```
check request_26
check request_50
user_27 can I buy a laptop?
list
help
```

---

## File Structure HF Spaces Expects

```
repo root/
├── app.py              ← HF Spaces entry point (required at root)
├── requirements.txt    ← Python deps (gradio, pandas, easyocr, Pillow)
├── code/               ← Financial engine
├── dataset/            ← CSV data files
└── gradio_app/
    └── app.py          ← Full Gradio UI implementation
```

---

## Local Testing (No Docker Needed)

```bash
# Install deps
pip install -r requirements.txt

# Set your key
set GROQ_API_KEY=gsk_...      # Windows
export GROQ_API_KEY=gsk_...   # Mac/Linux

# Run
python app.py

# Open browser at:
# http://localhost:7860
```

---

## Updating the Deployment

Any push triggers an auto-rebuild:

```bash
git add .
git commit -m "update: improved UI"
git push hf main
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Space stuck on "Building" | Check the **Logs** tab in the Space UI |
| `GROQ_API_KEY` not found | Re-add in Settings → Secrets; name must match exactly |
| `ModuleNotFoundError: gradio` | Ensure `gradio>=4.0.0` is in `requirements.txt` |
| Dataset not found | Make sure `dataset/` folder is committed and pushed |
| EasyOCR slow first run | Normal — model downloads once on first request (~150MB) |

---

## Your Space URL

```
https://huggingface.co/spaces/YOUR_USERNAME/buy-or-wait
```

Shareable embed URL:
```
https://YOUR_USERNAME-buy-or-wait.hf.space
```
