# Deployment Guide — Render.com (FREE)

Deploy the **Buy or Wait?** AI Financial Agent as a free Gradio chat app on Render.com.

> **Live Demo:** [https://buy-or-wait-financial-agent.onrender.com/](https://buy-or-wait-financial-agent.onrender.com/)

---

## Prerequisites

- A free account at [render.com](https://render.com)
- Your `GROQ_API_KEY` from [console.groq.com](https://console.groq.com)
- GitHub repo: `yogant18/buy-or-wait-financial-agent`

---

## Step 1 — Sign Up on Render

1. Go to [render.com](https://render.com)
2. Click **Sign Up with GitHub** — connect your GitHub account

---

## Step 2 — Create a New Web Service

1. Click **New → Web Service**
2. Select **"Build and deploy from a Git repository"**
3. Connect: **`yogant18/buy-or-wait-financial-agent`**

---

## Step 3 — Configure the Service

Render auto-detects the `Dockerfile`. Fill in:

| Field | Value |
|---|---|
| **Name** | `buy-or-wait-financial-agent` |
| **Branch** | `main` |
| **Language** | Docker (auto-detected) |
| **Instance Type** | **Free** |

---

## Step 4 — Add Environment Variable

Scroll to **Environment Variables** → Add:

| Key | Value |
|---|---|
| `GROQ_API_KEY` | your key from console.groq.com |

---

## Step 5 — Deploy

Click **Create Web Service** — build takes ~3-5 minutes.

---

## Your Live URL

```
https://buy-or-wait-financial-agent.onrender.com/
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| App sleeps after 15 min | Normal on free tier — wakes in ~30s on next visit |
| Build fails | Check Render logs tab for errors |
| `GROQ_API_KEY` not found | Re-add in Environment tab; name must match exactly |
| Dataset not found | Make sure `dataset/` folder is committed and pushed |

---

## Updating the Deployment

Any push to `main` triggers an auto-redeploy:

```bash
git add .
git commit -m "update: your change"
git push origin main
