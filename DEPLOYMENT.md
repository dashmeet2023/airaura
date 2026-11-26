# AirAura Deployment Guide

Production deployment architecture:
- **Database:** MongoDB Atlas (Free `M0` tier)
- **Backend (`backend/`):** Render Web Service (Free Python tier via [render.yaml](render.yaml))
- **Frontend (`frontend/`):** Vercel (Static React SPA via [frontend/vercel.json](frontend/vercel.json))
- **Hardware Node (`firmware/airaura_node/`):** ESP32 posting over HTTPS to Render

---

## (a) Set Up MongoDB Atlas (Free M0 Cluster)

1. Sign in to [MongoDB Atlas](https://cloud.mongodb.com/) and create or select a project.
2. Click **Create** (or **Build a Database**):
   - Choose **M0 Free**.
   - Select your preferred cloud provider/region (for lowest latency from Render Oregon/Singapore, e.g. AWS `us-west-2` or `ap-south-1`, matching your Render region when possible).
   - Name the cluster (e.g. `airaura-cluster`) and click **Create Deployment**.
3. **Create a Database User** when prompted (or go to **Security -> Database Access -> Add New Database User**):
   - Authentication Method: **Password**.
   - Enter a username (e.g. `airaura_app`) and generate a strong password (prefer alphanumeric characters, or URL-encode special characters like `@`, `:`, `/`, `?`, `#`, `%` if used).
   - Built-in Role: **Read and write to any database** (or `readWrite@airaura`). Click **Add User**.
4. **Configure Network Access**:
   - Go to **Security -> Network Access -> Add IP Address**.
   - Click **Allow Access from Anywhere** (enters `0.0.0.0/0` — required because Render free-tier services use dynamic outbound IPs).
   - Click **Confirm**.
5. **Copy and complete the Connection String**:
   - Go to **Database -> Connect -> Drivers** (Python / Motor).
   - Copy the `mongodb+srv://...` URI, replace `<db_password>` with your database user password, and add `/airaura` right before `?`:
     ```text
     mongodb+srv://airaura_app:<YOUR_PASSWORD>@airaura-cluster.<id>.mongodb.net/airaura?retryWrites=true&w=majority
     ```

---

## (b) Push Code to a Private GitHub Repository

Ensure no local secrets (`backend/.env`, `firmware/airaura_node/config.h`) or virtual environments are tracked before pushing.

```bash
# 1. Verify no secrets are tracked or staged
git status
git ls-files | grep -E "\.env$|config\.h$" || echo "Clean: no secrets tracked"

# 2. Add your private GitHub repository as origin and push
git remote add origin https://github.com/<your-username>/<your-private-repo>.git
git branch -M main
git push -u origin main
```

> **Never commit** `backend/.env`, `frontend/.env`, or `firmware/airaura_node/config.h`. Keep only `.env.example` and `config.example.h` in Git.

---

## (c) Deploy the Backend on Render (Blueprint)

First, generate strong secrets locally in Python (run twice for two distinct values):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

1. Sign in to [Render](https://dashboard.render.com/) and connect your GitHub account (grant access to your private AirAura repo).
2. Click **New + -> Blueprint**.
3. Select your private AirAura repository and click **Connect**. Render detects `render.yaml` (`airaura-api`, `runtime: python`, `rootDir: backend`, `plan: free`, `healthCheckPath: /api/health`).
4. Fill in every prompted environment variable (`sync: false` fields):
   - `MONGO_URL`: Your full Atlas SRV connection string ending in `/airaura?retryWrites=true&w=majority`
   - `JWT_SECRET`: First 64-char hex string generated above
   - `NODE_API_KEY`: Second 64-char hex string generated above (save this for the ESP32 `config.h`)
   - `CORS_ORIGINS`: Temporarily put `http://localhost:3000` (you will update this to your Vercel URL in step `(e)`)
   - `ADMIN_PASSWORD`: A strong password for the seeded PPCB admin (`admin@ppcb.gov.in`; must **not** be `admin@123` because `ENV=production` skips weak/missing admin seeding)
   - `STUDENT_DEMO_PASSWORD`: A strong demo password for `student@thapar.edu` (or leave blank if you prefer students to register their own accounts instead of having a demo login)
   - *(Pre-filled by `render.yaml`: `DB_NAME=airaura`, `ENV=production`, `ADMIN_EMAIL=admin@ppcb.gov.in`, `STUDENT_DEMO_EMAIL=student@thapar.edu`)*
5. Click **Apply** / **Create Services** and wait for the build and startup logs to finish (`Uvicorn running on http://0.0.0.0:...`).
6. Copy your Render service URL (e.g. `https://airaura-api.onrender.com`) and verify the health endpoint:
   ```bash
   curl https://airaura-api.onrender.com/api/health
   ```
   Expected response:
   ```json
   {"status":"ok","db":"ok","model_loaded":true}
   ```

---

## (d) Deploy the Frontend on Vercel

1. Sign in to [Vercel](https://vercel.com/) and click **Add New... -> Project**.
2. Import your private GitHub repository.
3. Under **Configure Project**:
   - **Framework Preset:** `Create React App` (auto-detected)
   - **Root Directory:** Click **Edit** and select `frontend`
4. Expand **Environment Variables** and add:
   - **Name:** `REACT_APP_BACKEND_URL`
   - **Value:** Your Render URL with **no** trailing slash and **no** `/api`, e.g. `https://airaura-api.onrender.com`
5. Click **Deploy**. (`frontend/.npmrc` sets `legacy-peer-deps=true`, and `frontend/vercel.json` builds with `CI=false npm run build` and rewrites all routes to `/index.html`.)
6. Copy your deployed Vercel URL (e.g. `https://airaura.vercel.app`).

---

## (e) Lock Down `CORS_ORIGINS` on Render and Redeploy

1. In Render, open the **`airaura-api`** service -> **Environment**.
2. Edit `CORS_ORIGINS` and set it to your Vercel URL (exact origin, **no trailing slash**):
   ```text
   https://airaura.vercel.app
   ```
   *(If you use multiple origins such as a custom domain, separate them cleanly with commas: `https://airaura.vercel.app,https://air.example.com`.)*
3. Click **Save Changes** (or **Save, rebuild, and deploy**). Wait until Render finishes redeploying and `/api/health` returns `200`.

---

## (f) Test Login for Both Roles

1. Open your Vercel URL (`https://airaura.vercel.app`).
2. **PPCB Official login:** Go to `/login`, select the **PPCB** tab, sign in with `admin@ppcb.gov.in` and your production `ADMIN_PASSWORD`. Verify `/pcb`, `/pcb/stations`, and `/pcb/advisories` load.
3. **Student login / registration:** Open `/login` in another browser/incognito window:
   - If you set `STUDENT_DEMO_PASSWORD`, sign in under the **Student** tab with `student@thapar.edu`.
   - Or go to `/register` to create a student account (registration always assigns `role: "student"`).
   - Verify `/student` displays live campus data without any pre-seeded demo advisories (since `ENV=production` skips sample advisory seeding).

---

## (g) Update ESP32 Firmware Config and Reflash

1. On your workstation, edit the gitignored `firmware/airaura_node/config.h`:
   - Wi-Fi credentials are **not** set in code — firmware `v0.3.0` uses the **`AirAura-Setup`** WiFiManager captive portal.
   - Set:
     ```cpp
     #define SERVER_URL    "https://airaura-api.onrender.com"
     #define NODE_ID       "airaura-01"
     #define NODE_KEY      "<PASTE_YOUR_RENDER_NODE_API_KEY_HERE>"
     ```
   - Make sure `NODE_KEY` matches Render's `NODE_API_KEY` environment variable verbatim.
2. Open [firmware/airaura_node/airaura_node.ino](firmware/airaura_node/airaura_node.ino) (`v0.3.0`) in Arduino IDE, select the ESP32 board and COM port, and click **Upload**.
3. Power the node, connect from a phone to the **`AirAura-Setup`** hotspot (password `airaura123`), and save your Wi-Fi network in the captive portal. *(Hold the ESP32 `BOOT` button for 5 seconds at any time to clear saved Wi-Fi and reopen `AirAura-Setup`.)*
4. Open Serial Monitor (`115200` baud) and confirm HTTP `200` responses from `/api/ingest`.
5. Check live node status:
   ```bash
   curl https://airaura-api.onrender.com/api/nodes/airaura-01/status
   ```
   Confirm `"online": true` and `"latest.fw": "0.3.0"`.

---

## (h) Render Free Tier Sleep Behavior

Render's free web service spins down after **15 minutes without inbound HTTP traffic**:
- **Cold starts:** The first request after sleep takes **30–60 seconds** while Render boots the container and reloads the ML model.
- **ESP32 resilience:** Because the firmware uses `15 s` connect / `30 s` read timeouts on HTTPS (`setConnectTimeout(15000)`, `setTimeout(30000)`) and posts every 60 seconds, a wakeup request may occasionally time out once while Render is booting. Failed posts are automatically saved in LittleFS (`/buffer.jsonl`, up to 500 lines) and flushed automatically once Render finishes waking up.
- Once the ESP32 posts every 60 seconds cleanly, inbound `/api/ingest` traffic naturally keeps the Render free instance awake while your hardware node is powered (staying aware of Render's monthly free instance-hour allowance).

---

## (i) Rotating Passwords and Keys

- **`JWT_SECRET`**: Update `JWT_SECRET` in Render -> **Environment** and save/redeploy. All existing user tokens immediately invalidate and users must sign in again.
- **`ADMIN_PASSWORD` / `STUDENT_DEMO_PASSWORD`**: Update the variable in Render -> **Environment** and save/redeploy. On startup, `server.py` compares the env password against the stored bcrypt hash and updates `password_hash` automatically for existing seeded accounts.
- **`NODE_API_KEY`**:
  1. Update `NODE_API_KEY` in Render -> **Environment** and save/redeploy (`ingest.py`'s `seed_default_node` updates `nodes.key_hash` for `airaura-01` automatically on startup).
  2. Update `NODE_KEY` in `firmware/airaura_node/config.h` to the same new secret and reflash the ESP32.
- **MongoDB Atlas DB Password**: Update the user password in Atlas **Database Access**, update `MONGO_URL` in Render **Environment**, and redeploy.
