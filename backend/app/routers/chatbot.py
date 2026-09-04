"""
app/routers/chatbot.py

Conversational assistant for FindIt Campus. Wraps the existing /reports,
/matches, and /custody endpoints behind natural-language chat, using
Gemini's tool-use to decide when to actually create a report, search for
matches, or (for admins) check the admin dashboard / confirm a handover --
instead of duplicating that logic here.

Requires GEMINI_API_KEY in your .env (see core/config.py).
"""
import json
import httpx
from google import genai
from google.genai import types
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
<<<<<<< Updated upstream
from typing import List, Literal
from fastapi import APIRouter, Header
=======
from typing import List, Literal, Optional
>>>>>>> Stashed changes

from app.core.config import settings
from app.models.user import User
from app.routers.auth import get_current_user_optional

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

client = genai.Client(api_key=settings.gemini_api_key)
MODEL_NAME = "gemini-3.1-flash-lite"

# Safety valve on the tool-calling loop below -- stops a misbehaving model
# from looping indefinitely on Gemini calls (each iteration is a real,
# billed API call).
MAX_TOOL_ITERATIONS = 5

INTERNAL_BASE_URL = "http://localhost:8000"

BASE_SYSTEM_PROMPT = """You are the FindIt Campus assistant, a helpful chatbot for a college
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

ADMIN_SYSTEM_PROMPT_ADDITION = """

You are currently talking to an ADMIN. In addition to everything above, you can:
4. Give a dashboard summary (get_dashboard_summary) -- open lost reports,
   open found reports, unresolved high-risk items, and items currently
   awaiting pickup. Use this whenever the admin asks how things look,
   what's pending, or anything dashboard-shaped.
5. List items awaiting pickup in detail (list_pending_pickups) -- who
   found what, who's coming to collect it, and their contact info.
6. Confirm a handover (confirm_handover) once the admin tells you they've
   physically handed an item to its claimant at the collection point. Only
   do this when the admin explicitly confirms the handover happened in
   person -- never call this just because it was asked about.

When summarizing dashboard data, be concise -- a few short lines or a small
list, not a long report. This is a chat widget.
"""

USER_TOOLS = [
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
]

ADMIN_TOOLS = [
    types.FunctionDeclaration(
        name="get_dashboard_summary",
        description="Admin only. Get a quick summary of platform activity: open lost reports, open found reports, unresolved high-risk items, and items awaiting pickup.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="list_pending_pickups",
        description="Admin only. List every match that's verified and awaiting physical handover at the collection point, with who found it and who's collecting it.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="confirm_handover",
        description="Admin only. Confirm an item has been physically handed to its claimant. Only call after the admin explicitly says the handover happened.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"match_id": types.Schema(type=types.Type.STRING)},
            required=["match_id"],
        ),
    ),
]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    history: List[ChatMessage]


<<<<<<< Updated upstream
async def _run_tool(name: str, tool_input: dict, auth_header: str | None) -> dict:
    headers = {"Authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(base_url=INTERNAL_BASE_URL, timeout=30) as client_http:
        if name == "create_report":
            resp = await client_http.post("/reports/", json=tool_input, headers=headers)
        elif name == "find_matches":
            resp = await client_http.post(f"/matches/find/{tool_input['report_id']}", headers=headers)
=======
async def _get_dashboard_summary(client_http: httpx.AsyncClient) -> dict:
    """
    Builds a dashboard-style summary from data that already exists via
    /reports/ and /custody/admin/pending-pickups -- no new backend
    endpoints needed. Report status/high-risk fields come straight off
    the Report model (see backend/app/models/report.py).
    """
    lost_resp = await client_http.get("/reports/", params={"report_type": "lost"})
    found_resp = await client_http.get("/reports/", params={"report_type": "found"})
    pickups_resp = await client_http.get("/custody/admin/pending-pickups")

    lost = lost_resp.json() if lost_resp.status_code == 200 else []
    found = found_resp.json() if found_resp.status_code == 200 else []
    pickups = pickups_resp.json() if pickups_resp.status_code == 200 else []

    open_lost = [r for r in lost if r.get("status") == "OPEN"]
    open_found = [r for r in found if r.get("status") == "OPEN"]
    high_risk_unresolved = [
        r for r in (lost + found)
        if r.get("is_high_risk") in (True, "true") and r.get("status") != "RESOLVED"
    ]

    return {
        "open_lost_reports": len(open_lost),
        "open_found_reports": len(open_found),
        "unresolved_high_risk_items": len(high_risk_unresolved),
        "items_awaiting_pickup": len(pickups),
    }


async def _run_tool(name: str, tool_input: dict, auth_header: Optional[str]) -> dict:
    """
    Executes a tool call against the app's own internal REST API, forwarding
    whatever Authorization header the chat request itself carried -- so a
    report created via chat, or a pickup confirmed via chat, is attributed
    to the actual logged-in user/admin, exactly as if they'd used the form.
    """
    headers = {"Authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(base_url=INTERNAL_BASE_URL, timeout=30, headers=headers) as client_http:
        if name == "create_report":
            resp = await client_http.post("/reports/", json=tool_input)
            try:
                return resp.json()
            except Exception:
                return {"error": resp.text}
        elif name == "find_matches":
            resp = await client_http.post(f"/matches/find/{tool_input['report_id']}")
            try:
                return resp.json()
            except Exception:
                return {"error": resp.text}
        elif name == "get_dashboard_summary":
            return await _get_dashboard_summary(client_http)
        elif name == "list_pending_pickups":
            resp = await client_http.get("/custody/admin/pending-pickups")
            try:
                return resp.json()
            except Exception:
                return {"error": resp.text}
        elif name == "confirm_handover":
            resp = await client_http.post(f"/custody/admin/{tool_input['match_id']}/handover")
            try:
                return resp.json()
            except Exception:
                return {"error": resp.text}
>>>>>>> Stashed changes
        else:
            return {"error": f"unknown tool {name}"}


def _to_gemini_role(role: str) -> str:
    return "model" if role == "assistant" else "user"

@router.post("/message", response_model=ChatResponse)
<<<<<<< Updated upstream
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
=======
async def chat(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
    user: Optional[User] = Depends(get_current_user_optional),
):
    is_admin = bool(user and user.is_admin == "true")

    system_prompt = BASE_SYSTEM_PROMPT + (ADMIN_SYSTEM_PROMPT_ADDITION if is_admin else "")
    declarations = USER_TOOLS + (ADMIN_TOOLS if is_admin else [])

>>>>>>> Stashed changes
    contents = [
        types.Content(role=_to_gemini_role(m.role), parts=[types.Part(text=m.content)])
        for m in req.history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=req.message)]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=declarations)],
    )

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )
        except Exception:
            # Covers Gemini rate limits (429) and other transient API errors
            # -- fail with a friendly message instead of a raw 500 crash.
            return ChatResponse(
                reply="The assistant is a bit busy right now -- please try again in a moment.",
                history=req.history,
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
<<<<<<< Updated upstream
=======
            # Belt-and-braces: even if an admin tool somehow got called for
            # a non-admin (it shouldn't, since it's never offered to the
            # model), the underlying endpoint itself is still admin-gated
            # via require_admin and will 403 -- this isn't the only guard.
>>>>>>> Stashed changes
            result = await _run_tool(fc.name, dict(fc.args), authorization)
            function_response_parts.append(
                types.Part(function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": json.loads(json.dumps(result, default=str))},
                ))
            )
        contents.append(types.Content(role="user", parts=function_response_parts))

    # Loop safeguard hit -- Gemini kept calling tools past the configured max.
    return ChatResponse(
        reply="I'm having trouble finishing that request right now -- could you try rephrasing, or use the regular form instead?",
        history=req.history,
    )
    