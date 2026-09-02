"""
app/routers/chatbot.py

Conversational assistant for FindIt Campus. Wraps the existing /reports and
/matches endpoints behind natural-language chat, using Gemini's tool-use to
decide when to actually create a report or search for matches, instead of
duplicating that logic here.

Requires GEMINI_API_KEY in your .env (see core/config.py).
"""
import json
import httpx
from google import genai
from google.genai import types
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Literal

from app.core.config import settings

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

client = genai.Client(api_key=settings.gemini_api_key)
MODEL_NAME = "gemini-3.6-flash"

INTERNAL_BASE_URL = "http://localhost:8000"

SYSTEM_PROMPT = """You are the FindIt Campus assistant, a helpful chatbot for a college
lost-and-found platform. You can help users with:

1. Reporting a lost or found item -- ask for: title, description, category,
   color, brand, where and when it was lost/found, and (for FOUND items only)
   a hidden verification question + answer that a claimant must answer correctly.
2. Searching for potential matches to an item they've lost.
3. Explaining how the platform works: asymmetric verification (claimant must
   answer a hidden question before contact info is revealed), the custody
   ledger (records every handover), high-risk item handling (IDs, phones,
   documents get priority + redaction), and QR tag pre-registration for valuables.

Ask clarifying questions one at a time rather than demanding everything at once.
Once you have enough info to create a report, use the create_report tool.
After a LOST report is created, use find_matches to check for existing FOUND items.
Keep responses short and conversational -- this is a chat widget, not an essay.
"""

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="create_report",
        description="Create a lost or found item report once you have the needed details from the user.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "report_type": types.Schema(type=types.Type.STRING, enum=["lost", "found"]),
                "title": types.Schema(type=types.Type.STRING),
                "description": types.Schema(type=types.Type.STRING),
                "category": types.Schema(type=types.Type.STRING),
                "color": types.Schema(type=types.Type.STRING),
                "brand": types.Schema(type=types.Type.STRING),
                "location_name": types.Schema(type=types.Type.STRING),
                "item_datetime": types.Schema(type=types.Type.STRING, description="ISO 8601 datetime"),
                "hidden_question": types.Schema(type=types.Type.STRING, description="FOUND reports only"),
                "hidden_answer": types.Schema(type=types.Type.STRING, description="FOUND reports only"),
            },
            required=["report_type", "title", "description", "item_datetime"],
        ),
    ),
    types.FunctionDeclaration(
        name="find_matches",
        description="Search for potential matches against an existing report by its id.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"report_id": types.Schema(type=types.Type.STRING)},
            required=["report_id"],
        ),
    ),
])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    history: List[ChatMessage]


async def _run_tool(name: str, tool_input: dict) -> dict:
    async with httpx.AsyncClient(base_url=INTERNAL_BASE_URL, timeout=30) as client_http:
        if name == "create_report":
            resp = await client_http.post("/reports/", json=tool_input)
        elif name == "find_matches":
            resp = await client_http.post(f"/matches/find/{tool_input['report_id']}")
        else:
            return {"error": f"unknown tool {name}"}
        try:
            return resp.json()
        except Exception:
            return {"error": resp.text}


def _to_gemini_role(role: str) -> str:
    return "model" if role == "assistant" else "user"


@router.post("/message", response_model=ChatResponse)
async def chat(req: ChatRequest):
    contents = [
        types.Content(role=_to_gemini_role(m.role), parts=[types.Part(text=m.content)])
        for m in req.history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=req.message)]))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[TOOLS],
    )

    while True:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )

        candidate_parts = response.candidates[0].content.parts
        function_calls = [p.function_call for p in candidate_parts if p.function_call]

        if not function_calls:
            reply_text = "".join(p.text for p in candidate_parts if p.text)
            contents.append(types.Content(role="model", parts=[types.Part(text=reply_text)]))
            history_out = [
                ChatMessage(role=("assistant" if c.role == "model" else "user"), content=part.text)
                for c in contents for part in c.parts if part.text
            ]
            return ChatResponse(reply=reply_text, history=history_out)

        contents.append(types.Content(role="model", parts=candidate_parts))

        function_response_parts = []
        for fc in function_calls:
            result = await _run_tool(fc.name, dict(fc.args))
            function_response_parts.append(
                types.Part(function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": json.loads(json.dumps(result, default=str))},
                ))
            )
        contents.append(types.Content(role="user", parts=function_response_parts))