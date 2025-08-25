# api/app/main.py
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv
import os

from api.app.chat_router import chat_router
from api.app.auth_router import auth_router
from api.app.upload_router import upload_router

from api.app.google_sheets import  google_sheets_preview_router

load_dotenv(".env")

SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
VPS_HOST=os.getenv('VPS_HOST')
FRONTEND_URL = os.getenv("FRONTEND_URL")  

app = FastAPI(title="Smart Support Chatbot", description="API for chat, file upload, Google Sheets integration, and data analysis")


# ✅ Session middleware 
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="none",  
    https_only=False,
    domain="none"
)

# ✅ CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, VPS_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Register routers
app.include_router(auth_router)
app.include_router(google_sheets_preview_router)
app.include_router(upload_router)
app.include_router(chat_router)

@app.get("/")
def root():
    return RedirectResponse("/docs")

@app.get("/favicon.ico")
def favicon():
    return {}
