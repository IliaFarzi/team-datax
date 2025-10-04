# api/app/main.py
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv
import os

from app.chat_router import chat_router
from app.auth_router import auth_router
from app.file_router import file_router
from app.billing_router import billing_router

load_dotenv(".env")

AUTH_SESSION_SECRET = os.getenv("AUTH_SESSION_SECRET")
FRONTEND_LOCAL_URL=os.getenv('FRONTEND_LOCAL_URL')
FRONTEND_URL = os.getenv("FRONTEND_URL")
CORS_CONNECTION = os.getenv('CORS_CONNECTION') 

app = FastAPI(title="DATAX", description="API for chat, file upload, Google Sheets integration, and data analysis")

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="DATAX API",
        version="1.0.0",
        description="Your API description",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    openapi_schema["security"] = [{"OAuth2PasswordBearer": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi



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
    allow_origins=[FRONTEND_URL, FRONTEND_LOCAL_URL, CORS_CONNECTION],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Register routers
app.include_router(auth_router)
app.include_router(file_router)
app.include_router(chat_router)
app.include_router(billing_router)

@app.get("/")
def root():
    return RedirectResponse("/docs")

@app.get("/favicon.ico")
def favicon():
    return {}
