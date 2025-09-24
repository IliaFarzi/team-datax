# api/app/main.py
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv
import os

from app.chat_router import chat_router
from app.auth_router import auth_router
from app.upload_router import upload_router
from app.download_router import file_router

load_dotenv(".env")

AUTH_SESSION_SECRET = os.getenv("AUTH_SESSION_SECRET")
VPS_URL=os.getenv('VPS_URL')
FRONTEND_URL = os.getenv("FRONTEND_URL")
CORS_CONNECTION = os.getenv('CORS_CONNECTION') 

app = FastAPI(title="DATAX", description="API for chat, file upload, Google Sheets integration, and data analysis")


# ✅ Session middleware 
app.add_middleware(
    SessionMiddleware,
    secret_key=AUTH_SESSION_SECRET,
    same_site="none",  
    https_only=False,
    domain="none"
)

# ✅ CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, VPS_URL, CORS_CONNECTION],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Register routers
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(file_router)
app.include_router(chat_router)

@app.get("/")
def root():
    return RedirectResponse("/docs")

@app.get("/favicon.ico")
def favicon():
    return {}
