# api/app/agent.py
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver 

from fastapi import Request

import os
from dotenv import load_dotenv
import logging 

logger = logging.getLogger(__name__)

from api.app.sheet_tools import (
    list_google_sheets,
    preview_google_sheet,
    load_google_sheet_to_dataframe,
    analyze_google_sheet
)
from api.app.upload_router import analyze_uploaded_file, list_uploaded_files


def make_wrapped_tools(request: Request):

    user_id = str(request.session.get("user_id"))
    
    # Show all data in one place
    def wrapped_show_all_data():
        logger.info("Using ShowAllData tool 🔧")
        uploads = list_uploaded_files(user_id=user_id)
        sheets = list_google_sheets(user_id=user_id)

        if not uploads and not sheets:
            return "هیچ فایلی یا شیتی پیدا نشد."

        # 📌 Markdown the output so it can be displayed directly to the user
        md = "### 📂 داده‌های شما\n"
        if uploads:
            md += "\n**فایل‌های آپلود شده:**\n"
            for f in uploads:
                md += f"- {f}\n"
        if sheets:
            md += "\n**گوگل شیت‌ها:**\n"
            for s in sheets:
                md += f"- {s}\n"

        return md

    # Google Sheets tools
    def wrapped_list_google_sheets():
        logger.info("Using ListGoogleSheets tool 🔧")
        return list_google_sheets(user_id=user_id)

    def wrapped_preview_google_sheet(sheet_id: str):
        logger.info("Using PreviewGoogleSheet tool 🔧")
        return preview_google_sheet(sheet_id=sheet_id, user_id=user_id)

    def wrapped_load_google_sheet_to_dataframe(sheet_id: str):
        logger.info("Using LoadGoogleSheet tool 🔧")
        return load_google_sheet_to_dataframe(sheet_id=sheet_id, user_id=user_id)

    def wrapped_analyze_google_sheet(sheet_id: str, operation: str, column: str, value: str = None):
        logger.info("Using AnalyzeGoogleSheet tool 🔧")
        return analyze_google_sheet(
            sheet_id=sheet_id,
            user_id=user_id,
            operation=operation,
            column=column,
            value=value
        )

    # Upload tools
    def wrapped_list_uploaded_files():
        logger.info("Using ListUploadedFiles tool 🔧")
        return list_uploaded_files(user_id=user_id)

    def wrapped_analyze_uploaded_file(filename: str):
        logger.info("Using AnalyzeUploadedFile tool 🔧")
        return analyze_uploaded_file(filename=filename, user_id=user_id)

    tools = [
        StructuredTool.from_function(func=wrapped_list_google_sheets, name="ListGoogleSheets", description="List all Google Sheets available to the logged-in user."),
        StructuredTool.from_function(func=wrapped_preview_google_sheet, name="PreviewGoogleSheet", description="Preview first 5 rows of a sheet."),
        StructuredTool.from_function(func=wrapped_load_google_sheet_to_dataframe, name="LoadGoogleSheet", description="Load a sheet into a DataFrame."),
        StructuredTool.from_function(func=wrapped_analyze_google_sheet, name="AnalyzeGoogleSheet", description="Perform analysis like sum, mean, filter."),
        StructuredTool.from_function(func=wrapped_list_uploaded_files, name="ListUploadedFiles", description="List all files uploaded by the logged-in user."),
        StructuredTool.from_function(func=wrapped_analyze_uploaded_file, name="AnalyzeUploadedFile", description="Analyze an uploaded CSV/Excel file."),
        StructuredTool.from_function(func=wrapped_show_all_data,name="ShowAllData",description="Show all data (uploads and sheets) together.")]
    return tools


# Load environment variables
load_dotenv(".env")

# Access API keys
LLM_OPENROUTER_API_KEY = os.getenv("LLM_OPENROUTER_API_KEY")
LLM_OPENROUTER_API_BASE = os.getenv("LLM_OPENROUTER_API_BASE")

def pre_model_hook(state):
    """Before calling LLM → keep only the last 5 messages"""
    messages = state.get("messages", [])
    if len(messages) > 10:
        messages = messages[-5:]
    return {"messages": messages}

def get_agent(model_name: str, request: Request):
    llm = ChatOpenAI(
        model=model_name,
        api_key=LLM_OPENROUTER_API_KEY,
        base_url=LLM_OPENROUTER_API_BASE,
        max_tokens= 4096,
        temperature=0.7,
        top_p= 0.9,
        frequency_penalty= 0.1,
        presence_penalty= 0.1)

    system_message = """
    You are a strict data analysis assistant named DATAX.
    Your name is always DATAX. If user asks for your name, you MUST answer "My name is DATAX."
    At the beginning of every new session, after the welcome message, explicitly introduce yourself by name.
    You are ONLY allowed to answer questions about:
    - The user's uploaded files (CSV/Excel).
    - The user's Google Sheets.
    - Data analysis tasks like sum, mean, filtering, previewing, and listing files/sheets.
    ❌ You MUST NOT answer general knowledge, chit-chat, personal advice, or unrelated questions.
    If the user asks something outside of your scope, politely reply:
    "I can only help with analyzing your data (Google Sheets or uploaded files)."

    You have access to these tools:
    - ListGoogleSheets
    - PreviewGoogleSheet
    - LoadGoogleSheet
    - AnalyzeGoogleSheet
    - ListUploadedFiles
    - AnalyzeUploadedFile
    - ShowAllData

    **Important:**
    - Always format your responses in Markdown so the frontend can render them nicely.
    - Use bullet points, tables, and code blocks where appropriate.
    - Be clear and concise, and explain results as if teaching a non-technical user.
    - Never delete, post, or modify user info in any database or service.
    - Never disclose user information to anyone.
    - When the user asks to "analyze everything", first list all files and sheets, then ask the user to select **one at a time**. Do not try to analyze all at once.
    - If asked about access to databases or systems, respond: 'I securely access your data through specialized tools. Please upload files or connect Google Sheets to proceed.'
    """

    llm = llm.with_config(system_message=system_message)

    tools = make_wrapped_tools(request)
    # 🟢 Pipe agent → parser to always return clean output
    agent = create_react_agent(llm, tools=tools,
                            pre_model_hook=pre_model_hook, # History management
                            checkpointer=MemorySaver(),  # Save simple state
                            version="v2",
                            name="DATAX-Agent")
    
    return agent 
