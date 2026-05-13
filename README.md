# HiveOS — Setup Guide

## Folder structure
```
hiveos/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example     ← copy to .env and fill in
│   └── routes/
│       ├── auth.py
│       ├── gpt.py
│       ├── data.py
│       └── hives.py
└── frontend/
    └── index.html
```

---

## Step 1 — Backend setup (on Raspberry Pi or any server)

```bash
cd hiveos/backend

# Copy and fill in your secrets
cp .env.example .env
nano .env

# Install dependencies
pip3 install -r requirements.txt --break-system-packages

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit http://localhost:8000 → should show {"status": "HiveOS API running"}
Visit http://localhost:8000/docs → automatic API documentation

---

## Step 2 — Test login

```bash
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"hiveos2024"}'
```

Should return: {"token":"eyJ...", "username":"admin"}

---

## Step 3 — Open the frontend

Just open frontend/index.html in a browser.
The frontend auto-connects to http://localhost:8000

---

## Step 4 — Deploy to internet (Railway - free)

1. Push the backend folder to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Add environment variables from your .env
4. Railway gives you a URL like: https://hiveos-backend.up.railway.app
5. In frontend/index.html change line:
      'https://YOUR-BACKEND-URL.up.railway.app'
   to your Railway URL
6. Deploy frontend to Vercel (drag & drop the frontend folder)

---

## Add a new user

```python
import bcrypt
print(bcrypt.hashpw(b"newpassword", bcrypt.gensalt()).decode())
```

Copy the output hash and add to USERS dict in main.py:
```python
USERS = {
    "admin":     bcrypt.hashpw(b"hiveos2024", bcrypt.gensalt()),
    "newuser":   b"$2b$12$paste-hash-here",
}
```

---

## Default credentials
- Username: admin
- Password:  hiveos2024
