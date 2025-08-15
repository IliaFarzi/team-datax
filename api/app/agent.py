# api/app/agent.py
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool

import os
from dotenv import load_dotenv

from api.app.google_sheets import list_google_sheets, preview_google_sheet, load_google_sheet_to_dataframe, analyze_google_sheet, list_private_public_sheets, extract_headers_tool
from api.app.models import PreviewGoogleSheetArgs, LoadGoogleSheetArgs, AnalyzeGoogleSheetArgs, ListPrivatePublicSheetArgs, ListGoogleSheetArgs, AnalyzeUploadedFileArgs, ListUploadedFilesArgs
from api.app.upload_router import analyze_uploaded_file, list_uploaded_files

tools = [
    StructuredTool.from_function(
        func=list_google_sheets,
        name="ListGoogleSheets",
        description="List all Google Sheets available to the user. Requires google_id.",
        args_schema=ListGoogleSheetArgs, 
    ),
    StructuredTool.from_function(
        func=preview_google_sheet,
        name="PreviewGoogleSheet",
        description="Preview the first 5 rows of a Google Sheet. Requires sheet_id and google_id.",
        args_schema=PreviewGoogleSheetArgs
    ),
    StructuredTool.from_function(
        func=load_google_sheet_to_dataframe,
        name="LoadGoogleSheet",
        description="Load a complete Google Sheet into a DataFrame for analysis. Requires sheet_id and google_id.",
        args_schema=LoadGoogleSheetArgs
    ),
    StructuredTool.from_function(
        func=analyze_google_sheet,
        name="AnalyzeGoogleSheet",
        description="Analyze a Google Sheet with operations like sum, mean, or filter. Requires sheet_id, google_id, operation, column, and optionally value.",
        args_schema=AnalyzeGoogleSheetArgs
    ),
    StructuredTool.from_function(
        func=list_private_public_sheets,
        name="ListPrivatePublicSheets",
        description="List private and public Google Sheets for a user. Requires google_id.",
        args_schema=ListPrivatePublicSheetArgs 
    ),
    StructuredTool.from_function(
        func=extract_headers_tool,
        name="ExtractSheetHeaders",
        description="Extract headers from a Google Sheet, save to CSV, and upload to MinIO. Requires sheet_id and google_id.",
        args_schema=PreviewGoogleSheetArgs
    ),
    StructuredTool.from_function(
    func=analyze_uploaded_file,
    name="AnalyzeUploadedFile",
    description="Analyze an uploaded CSV or Excel file stored in MinIO. Requires filename.",
    args_schema=AnalyzeUploadedFileArgs
    ),
    StructuredTool.from_function(
    func=list_uploaded_files,
    name="ListUploadedFiles",
    description="List all files uploaded by a specific user (google_id) with metadata.",
    args_schema=ListUploadedFilesArgs
)
    ]

# Load environment variables
load_dotenv(".env")

# Access API keys
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_base_url = os.getenv("OPENROUTER_API_BASE")

def get_agent(model_name: str):
    llm = ChatOpenAI(
        model_name=model_name,
        openai_api_key=openrouter_api_key,
        openai_api_base=openrouter_base_url,
        temperature=0.7,
        max_tokens=4096,
        top_p=0.9,
        frequency_penalty=0.1,
        presence_penalty=0.1
    )
    system_message = """
    You are a data analysis assistant that helps users interact with their Google Sheets. Use the provided tools to:
    - List available Google Sheets (ListGoogleSheets).
    - Preview the first 5 rows of a specific sheet (PreviewGoogleSheet).
    - Load a sheet into a DataFrame for analysis (LoadGoogleSheet).
    - Perform analysis like sum, mean, or filtering on a sheet (AnalyzeGoogleSheet).
    - List private and public Google Sheets for a user. Requires google_id(ListPrivatePublicSheets).
    - List all files uploaded by a specific user (google_id) with metadata.(ListUploadedFiles)
    - Analyze an uploaded CSV or Excel file stored in MinIO. Requires filename.(AnalyzeUploadedFile)
    Provide clear and concise responses. If a user request requires a specific sheet, ask for the sheet_id if not provided.
    """
    llm = llm.with_config(system_message=system_message)
    return create_react_agent(llm, tools=tools)