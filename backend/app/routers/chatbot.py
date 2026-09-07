"""
app/routers/chatbot.py

Conversational assistant for FindIt Campus. Wraps the existing /reports,
/matches, and /custody endpoints behind natural-language chat, using
Gemini's tool-use to decide when to actually create a report, search for
matches, check a verification answer, confirm a claim, or (for admins)
check the admin dashboard / confirm a handover -- instead of duplicating
that logic here.

WHY conversation memory is server-side (not client-sent history):
Gemini's `contents` list -- which includes the real function_call and
function_response parts, not just text -- is kept server-side in
_CONVERSATIONS, keyed by a conversation_id the frontend echoes back on
every request. An earlier version rebuilt `contents` from plain text sent
by the client, so the model had no hard evidence a tool call had already
succeeded -- only its own prior text summary to go on. That let it
(a) hallucinate entire verification flows for tools it didn't even have,
and (b) re-call create_report on a later turn because it couldn't see the
earlier successful call. In-memory only (a plain dict) -- fine for a
college project; a real deployment would move this to Redis or a DB table.

Requires GEMINI_API_KEY in your .env (see core/config.py).
"""
import json
import uuid
import httpx
from google import genai
from google.genai import types
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from typing import List, Literal, Optional

from app.core.config import settings
from app.models.user import User
from app.routers.auth import get_current_user_optional

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

client = genai.Client(api_key=settings.gemini_api_key)
MODEL_NAME = "gemini-3.1-flash-lite"

MAX_TOOL_ITERATIONS = 6
INTERNAL_BASE_URL = "http://localhost:8000"

# conversation_id -> list[types.Content], the REAL Gemini history including
# function_call/function_response parts. See module docstring.
_CONVERSATIONS: dict[str, List[types.Content]] = {}

BASE_SYSTEM_PROMPT = """You are the FindIt Campus assistant -- a chatbot for VIT's
lost-and-found platform. You can help with:

1. REPORTING a lost or found item.
   Required fields for EVERY report: title, description, category, color,
   brand, location_name, item_datetime.
   Required fields for FOUND reports ONLY, additionally: hidden_question,
   hidden_answer, collection_point (where the owner collects the item
   once verified).

   You MUST explicitly ask for and receive an answer for EVERY required
   field above, one at a time, before calling create_report. Do not skip
   a field just because the person didn't mention it unprompted, and do
   not guess, assume, or fill in a plausible-sounding value for any field
   yourself -- every value must come from something the person actually
   told you. If a non-required detail is unknown ("I don't remember the
   brand"), that's fine to leave blank, but you still must have asked.
   Call create_report ONLY ONCE you have every required field, and ONLY
   ONCE per item -- if it already succeeded earlier in this conversation
   for this item, do not call it again; reuse the report_id you got back.

2. SEARCHING for matches. After a LOST report is created, call find_matches
   with its report_id. This returns a list of candidate matches, each with
   a match id and a found_report_id -- nothing else. To show the person
   what question they need to answer, you MUST call get_report on the
   found_report_id to fetch the real hidden_question text. NEVER invent or
   guess a hidden_question -- only ever use exactly what get_report returns.

   If the person asks something like "is there a match", "any updates on
   my report", or "what's the status of my item" WITHOUT giving you a
   report_id, you do not know the answer yet -- call list_my_reports
   first to see their actual reports, then find_matches on the relevant
   one. NEVER say "there are no reports" or "the platform is empty" or
   similar unless list_my_reports (or get_dashboard_summary, for an admin)
   actually returned that in THIS conversation. If you're not sure which
   of their reports they mean, ask them, using the real titles from
   list_my_reports.

3. VERIFYING a claim (the person believes one of the matches is their item):
   a) Call get_report(found_report_id) to get the real hidden_question, and
      ask the person that exact question.
   b) Call check_answer(match_id, hidden_answer) with their answer. This
      does NOT commit anything -- it just tells you correct: true/false.
      If false, let them try again or move to the next candidate match.
   c) If check_answer says correct: true, call verify_claim(match_id,
      hidden_answer) to actually finalize it. You do not need to ask for
      the person's name/email/registration number -- the system fills
      those in automatically from their logged-in account.
   d) Only AFTER verify_claim returns success should you tell the person
      where to collect their item -- use exactly the collection_point
      verify_claim's response gives you. NEVER state a collection location,
      a "correct answer" confirmation, or that a report/match/claim exists
      unless the corresponding tool call actually returned that result in
      THIS conversation. If a tool call fails or returns an error, say so
      plainly -- do not paper over it with an invented success message.

4. EXPLAINING how the platform works, if asked: matching combines text +
   photo similarity with location/time proximity into one score; close
   scores trigger a disambiguation question. High-risk items (IDs, phones,
   documents, cards) are auto-flagged and their public photo is pixelated
   until the true owner verifies. Every physical handover is logged in a
   custody ledger. Students can pre-register valuables with a QR tag.
   Only @vitstudent.ac.in and @vit.ac.in emails can sign up. A confirmation
   email is sent automatically when a report is created.

Ask clarifying questions one at a time. Keep responses short and
conversational -- this is a chat widget, not an essay.
"""

ADMIN_SYSTEM_PROMPT_ADDITION = """

You are currently talking to an ADMIN. In addition to everything above, you can:
5. Give a dashboard summary (get_dashboard_summary) -- open lost reports,
   open found reports, unresolved high-risk items, items awaiting pickup.
6. List items awaiting pickup in detail (list_pending_pickups).
7. Confirm a handover (confirm_handover) once the admin explicitly says
   they've physically handed an item to its claimant. Never call this
   just because it was asked about -- only on an explicit confirmation.

Be concise -- a few short lines, not a long report. This is a chat widget.
"""

USER_TOOLS = [
    types.FunctionDeclaration(
        name="create_report",
        description=(
            "Create a lost or found item report. Only call this once you have "
            "explicitly asked for and received every required field listed in "
            "the system prompt -- for report_type='found', that includes "
            "hidden_question, hidden_answer, and collection_point. Call this "
            "at most once per item per conversation."
        ),
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
                "hidden_question": types.Schema(type=types.Type.STRING, description="FOUND reports only -- required"),
                "hidden_answer": types.Schema(type=types.Type.STRING, description="FOUND reports only -- required"),
                "collection_point": types.Schema(type=types.Type.STRING, description="FOUND reports only -- required"),
            },
            required=["report_type", "title", "description", "item_datetime"],
        ),
    ),
    types.FunctionDeclaration(
        name="find_matches",
        description="Search for potential matches against an existing report by its id. Returns match id + found_report_id per candidate -- call get_report to see the actual hidden_question.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"report_id": types.Schema(type=types.Type.STRING)},
            required=["report_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_report",
        description="Fetch a report's public details by id, including its real hidden_question (for FOUND reports) and collection_point. Never invent this info -- always fetch it.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"report_id": types.Schema(type=types.Type.STRING)},
            required=["report_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_my_reports",
        description=(
            "List the current logged-in user's own lost/found reports (id, title, "
            "report_type, status). ALWAYS call this before answering any question "
            "like 'is there a match', 'what's the status of my report', or 'did "
            "anyone find my X' -- you cannot know this without checking. Never "
            "say there are no reports or no matches without calling this (and, "
            "for a specific report, find_matches) first in this conversation."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="check_answer",
        description="Check whether an answer to a match's hidden_question is correct, WITHOUT finalizing the claim. Use this before verify_claim.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "match_id": types.Schema(type=types.Type.STRING),
                "hidden_answer": types.Schema(type=types.Type.STRING),
            },
            required=["match_id", "hidden_answer"],
        ),
    ),
    types.FunctionDeclaration(
        name="verify_claim",
        description="Finalize a claim once check_answer has confirmed the answer is correct. The claimant's identity is filled in automatically from their logged-in account -- you only need match_id and hidden_answer.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "match_id": types.Schema(type=types.Type.STRING),
                "hidden_answer": types.Schema(type=types.Type.STRING),
            },
            required=["match_id", "hidden_answer"],
        ),
    ),
]

ADMIN_TOOLS = [
    types.FunctionDeclaration(
        name="get_dashboard_summary",
        description="Admin only. Quick summary: open lost reports, open found reports, unresolved high-risk items, items awaiting pickup.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="list_pending_pickups",
        description="Admin only. List every match verified and awaiting physical handover, with who found it and who's collecting it.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="confirm_handover",
        description="Admin only. Confirm an item has been physically handed to its claimant. Only after the admin explicitly says the handover happened.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"match_id": types.Schema(type=types.Type.STRING)},
            required=["match_id"],
        ),
    ),
]


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str


async def _get_dashboard_summary(client_http: httpx.AsyncClient) -> dict:
    """
    Builds a dashboard-style summary from data that already exists via
    /reports/ and /custody/admin/pending-pickups -- no new backend
    endpoints needed. Statuses on the backend are lowercase ("open",
    "resolved", etc. -- see models/report.py's ReportStatus enum), so the
    comparisons below match that, not "OPEN"/"RESOLVED".
    """
    lost_resp = await client_http.get("/reports/", params={"report_type": "lost"})
    found_resp = await client_http.get("/reports/", params={"report_type": "found"})
    pickups_resp = await client_http.get("/custody/admin/pending-pickups")

    lost = lost_resp.json() if lost_resp.status_code == 200 else []
    found = found_resp.json() if found_resp.status_code == 200 else []
    pickups = pickups_resp.json() if pickups_resp.status_code == 200 else []

    open_lost = [r for r in lost if r.get("status") == "open"]
    open_found = [r for r in found if r.get("status") == "open"]
    high_risk_unresolved = [
        r for r in (lost + found)
        if r.get("is_high_risk") in (True, "true") and r.get("status") != "resolved"
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
    the real Authorization header so every action is attributed to the
    actual logged-in user -- and, for verify_claim, filling in the
    claimant's identity from that same authenticated user rather than
    trusting the model to supply (or invent) it.
    """
    headers = {"Authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(base_url=INTERNAL_BASE_URL, timeout=30, headers=headers) as h:
        try:
            if name == "create_report":
                resp = await h.post("/reports/", json=tool_input)
            elif name == "find_matches":
                resp = await h.post(f"/matches/find/{tool_input['report_id']}")
            elif name == "get_report":
                resp = await h.get(f"/reports/{tool_input['report_id']}")
            elif name == "list_my_reports":
                me_resp = await h.get("/auth/me")
                if me_resp.status_code != 200:
                    return {"error": "Not logged in -- can't list reports without an authenticated account."}
                my_id = me_resp.json().get("id")
                all_resp = await h.get("/reports/")
                if all_resp.status_code != 200:
                    return {"error": "Could not fetch reports."}
                mine = [
                    {"id": r["id"], "title": r["title"], "report_type": r["report_type"], "status": r["status"]}
                    for r in all_resp.json()
                    if r.get("reporter_id") == my_id
                ]
                return {"reports": mine}
            elif name == "check_answer":
                resp = await h.post(
                    f"/matches/{tool_input['match_id']}/check-answer",
                    json={"hidden_answer": tool_input["hidden_answer"]},
                )
            elif name == "verify_claim":
                me_resp = await h.get("/auth/me")
                if me_resp.status_code != 200:
                    return {"error": "Not logged in -- can't verify a claim without an authenticated account."}
                me = me_resp.json()
                resp = await h.post(
                    f"/matches/{tool_input['match_id']}/verify",
                    json={
                        "claimant_name": me.get("name") or "",
                        "claimant_registration_number": me.get("registration_number") or "",
                        "claimant_email": me.get("email") or "",
                        "hidden_answer": tool_input["hidden_answer"],
                    },
                )
            elif name == "get_dashboard_summary":
                return await _get_dashboard_summary(h)
            elif name == "list_pending_pickups":
                resp = await h.get("/custody/admin/pending-pickups")
            elif name == "confirm_handover":
                resp = await h.post(f"/custody/admin/{tool_input['match_id']}/handover")
            else:
                return {"error": f"unknown tool {name}"}
        except Exception as e:
            # Broad on purpose: a tool failing for ANY reason (missing key,
            # bad response body, a downstream 500, a network blip) should
            # degrade to a message the model can relay honestly -- it must
            # never crash the whole /chatbot/message request into a raw
            # 500 (which is what "Sorry, I couldn't reach the assistant"
            # on the frontend actually means).
            return {"error": f"{type(e).__name__}: {e}"}

        try:
            body = resp.json()
        except Exception:
            body = {"error": resp.text}
        if resp.status_code >= 400:
            return {"error": body if isinstance(body, dict) else str(body), "status_code": resp.status_code}
        return body


@router.post("/message", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
    user: Optional[User] = Depends(get_current_user_optional),
):
    is_admin = bool(user and user.is_admin == "true")

    conversation_id = req.conversation_id or str(uuid.uuid4())
    contents = _CONVERSATIONS.get(conversation_id, [])

    system_prompt = BASE_SYSTEM_PROMPT + (ADMIN_SYSTEM_PROMPT_ADDITION if is_admin else "")
    declarations = USER_TOOLS + (ADMIN_TOOLS if is_admin else [])

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
            return ChatResponse(
                reply="The assistant is a bit busy right now -- please try again in a moment.",
                conversation_id=conversation_id,
            )

        candidate_parts = response.candidates[0].content.parts
        function_calls = [p.function_call for p in candidate_parts if p.function_call]

        if not function_calls:
            reply_text = "".join(p.text for p in candidate_parts if p.text)
            contents.append(types.Content(role="model", parts=[types.Part(text=reply_text)]))
            _CONVERSATIONS[conversation_id] = contents
            return ChatResponse(reply=reply_text, conversation_id=conversation_id)

        contents.append(types.Content(role="model", parts=candidate_parts))

        function_response_parts = []
        for fc in function_calls:
            try:
                result = await _run_tool(fc.name, dict(fc.args), authorization)
                result_json = json.loads(json.dumps(result, default=str))
            except Exception as e:
                result_json = {"error": f"{type(e).__name__}: {e}"}
            function_response_parts.append(
                types.Part(function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": result_json},
                ))
            )
        contents.append(types.Content(role="user", parts=function_response_parts))

    _CONVERSATIONS[conversation_id] = contents
    return ChatResponse(
        reply="I'm having trouble finishing that request right now -- could you try rephrasing, or use the regular form instead?",
        conversation_id=conversation_id,
    )
