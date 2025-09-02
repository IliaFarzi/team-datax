# api/app/agent.py
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool

from fastapi import Request

import os
from dotenv import load_dotenv

from api.app.google_sheets import list_google_sheets, preview_google_sheet, load_google_sheet_to_dataframe, analyze_google_sheet, list_private_public_sheets, extract_headers_tool
from api.app.upload_router import analyze_uploaded_file, list_uploaded_files

def make_wrapped_tools(request):
    google_id = request.session.get("google_id")

    # Google Sheets tools
    def wrapped_list_google_sheets():
        return list_google_sheets(google_id=google_id)

    def wrapped_list_private_public_sheets():
        return list_private_public_sheets(google_id=google_id)

    def wrapped_preview_google_sheet(sheet_id: str):
        return preview_google_sheet(sheet_id=sheet_id, google_id=google_id)

    def wrapped_load_google_sheet_to_dataframe(sheet_id: str):
        return load_google_sheet_to_dataframe(sheet_id=sheet_id, google_id=google_id)

    def wrapped_analyze_google_sheet(sheet_id: str, operation: str, column: str, value: str = None):
        return analyze_google_sheet(sheet_id=sheet_id, google_id=google_id, operation=operation, column=column, value=value)

    def wrapped_extract_headers_tool(sheet_id: str):
        return extract_headers_tool(sheet_id=sheet_id, google_id=google_id)

    # Upload tools
    def wrapped_list_uploaded_files():
        return list_uploaded_files(google_id=google_id)

    def wrapped_analyze_uploaded_file(filename: str):
        return analyze_uploaded_file(filename=filename, google_id=google_id)

    tools = [
        StructuredTool.from_function(func=wrapped_list_google_sheets, name="ListGoogleSheets", description="List all Google Sheets available to the logged-in user."),
        StructuredTool.from_function(func=wrapped_list_private_public_sheets, name="ListPrivatePublicSheets", description="List private and public Google Sheets."),
        StructuredTool.from_function(func=wrapped_preview_google_sheet, name="PreviewGoogleSheet", description="Preview first 5 rows of a sheet."),
        StructuredTool.from_function(func=wrapped_load_google_sheet_to_dataframe, name="LoadGoogleSheet", description="Load a sheet into a DataFrame."),
        StructuredTool.from_function(func=wrapped_analyze_google_sheet, name="AnalyzeGoogleSheet", description="Perform analysis like sum, mean, filter."),
        StructuredTool.from_function(func=wrapped_extract_headers_tool, name="ExtractSheetHeaders", description="Extract headers from a Google Sheet."),
        StructuredTool.from_function(func=wrapped_list_uploaded_files, name="ListUploadedFiles", description="List all files uploaded by the logged-in user."),
        StructuredTool.from_function(func=wrapped_analyze_uploaded_file, name="AnalyzeUploadedFile", description="Analyze an uploaded CSV/Excel file."),
    ]
    return tools


# Load environment variables
load_dotenv(".env")

# Access API keys
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_base_url = os.getenv("OPENROUTER_API_BASE")

def get_agent(model_name: str, request):
    llm = ChatOpenAI(
        model=model_name,
        api_key=openrouter_api_key,
        base_url=openrouter_base_url,
        temperature=0.7,
        model_kwargs={
            "max_tokens": 4096,
            "top_p": 0.9,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.1,
        }
    )

    system_message = """
You are a strict data analysis assistant. 
You are ONLY allowed to answer questions about:
- The user's uploaded files (CSV/Excel).
- The user's Google Sheets.
- Data analysis tasks like sum, mean, filtering, previewing, and listing files/sheets.
❌ You MUST NOT answer general knowledge, chit-chat, personal advice, or unrelated questions (e.g., cars, movies, travel, coding).
If the user asks something outside of your scope, politely reply:
"I can only help with analyzing your data (Google Sheets or uploaded files)."
You have access to these tools:
- ListGoogleSheets
- PreviewGoogleSheet
- LoadGoogleSheet
- AnalyzeGoogleSheet
- ListPrivatePublicSheets
- ExtractSheetHeaders
- ListUploadedFiles
- AnalyzeUploadedFile
**Important:**
- Always format your responses in Markdown so the frontend can render them nicely.
- Use bullet points, tables, and code blocks where appropriate.
- Be clear and concise, and explain results as if teaching a non-technical user.
"""

    # attach system message
    llm = llm.with_config(system_message=system_message)

    tools = make_wrapped_tools(request)

    return create_react_agent(llm, tools=tools)