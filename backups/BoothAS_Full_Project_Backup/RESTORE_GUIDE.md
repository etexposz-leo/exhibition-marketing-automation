# BoothAS Restore Guide

## How to Restore Locally

### Prerequisites
- Python 3.10+
- pip or uv package manager

### Steps

1. **Extract the backup:**
   ```bash
   unzip BoothAS_Full_Project_Backup.zip -d BoothAS
   cd BoothAS
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   .venv\Scripts\activate   # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Start the application:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Access the application:**
   Open http://localhost:8000 in your browser

---

## How to Restore on Render

### Option 1: Deploy from GitHub

1. **Connect GitHub to Render:**
   - Go to https://dashboard.render.com
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

2. **Configure the service:**
   - Branch: `main`
   - Root Directory: (leave empty)
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port 10000`

3. **Set environment variables:**
   - Add all variables from `.env.example`
   - Add your production API keys

4. **Deploy:**
   - Click "Create Web Service"
   - Render will automatically deploy from GitHub

### Option 2: Deploy via render.yaml

1. Push `render.yaml` to your repository
2. Render will detect and deploy automatically

---

## Required Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host/db

# Authentication
SECRET_KEY=your-secret-key-here

# AI Services
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=your-deepseek-key

# SMS (Development)
SMS_MOCK_MODE=true
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1234567890

# Social Media APIs
FACEBOOK_ACCESS_TOKEN=your-facebook-token
X_API_KEY=your-x-api-key
X_API_SECRET=your-x-api-secret
LINKEDIN_ACCESS_TOKEN=your-linkedin-token
INSTAGRAM_ACCESS_TOKEN=your-instagram-token
GOOGLE_BUSINESS_API_KEY=your-google-key
```

---

## How to Run Uvicorn

### Basic
```bash
uvicorn app.main:app
```

### With reload (development)
```bash
uvicorn app.main:app --reload
```

### With custom host/port
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### With workers (production)
```bash
uvicorn app.main:app --workers 4
```

---

## Troubleshooting

### Database Issues
```bash
# Reset database
rm marketing_automation.db
alembic upgrade head
```

### Dependency Issues
```bash
pip install --upgrade -r requirements.txt
```

### Port Already in Use
```bash
pkill -f uvicorn
# or
uvicorn app.main:app --port 8001
```
