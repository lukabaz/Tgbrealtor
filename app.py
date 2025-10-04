import os  # Для env vars (PORT)
from api.webhook import app  # Import FastAPI app from webhook.py

# Vercel entrypoint (run uvicorn)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))