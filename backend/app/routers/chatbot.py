"""
app/routers/chatbot.py

Conversational assistant for FindIt Campus. Wraps the existing /reports,
/matches, and /custody endpoints behind natural-language chat, using
Gemini's tool-use to decide when to actually create a report, search for
matches, check a verification answer, confirm a claim, resolve a
disambiguation, view the custody ledger, run the staleness sweep, delete a
report, or (for admins) check the admin dashboard / confirm a handover --
instead of duplicating that logic here.

WHY conversation memory is server-side (not client-sent history):
Gemini's `contents` list -- which includes the real function_call and
function_response parts, not just text -- is kept server-side in
_CONVERSATIONS, keyed by a conversation_id the frontend echoes back on
every request. Rebuilding `contents` from plain text sent by the client
means the model has no hard evidence a tool call already succeeded --
only its own prior text summary to go on. That lets it hallucinate entire
flows for tools it doesn't have, or re-call create_report on a later turn
because it can't see the earlier successful call. In-memory only (a plain
dict) -- fine for a college project; a real deployment would move this to
Redis or a DB table.

IMPORTANT: this ONLY works if the frontend actually sends back the same
conversation_id on every message in a chat session (see ChatWidget.jsx /
client.js's sendChatMessage). If the frontend ever sends conversation_id:
null on every call, every message starts a brand-new empty conversation --
the model will re-ask questions it was already just given the answer to,
because as far as it can tell, this is the first message it's ever seen.

WHY generate_content runs in a thread:
client.models.generate_content() is a synchronous, blocking network call.
Calling it directly inside this async def would stall the whole event
loop for the entire round-trip to Gemini -- every OTHER request (another
student's chat message, login, report creation) would freeze until Gemini
replied. asyncio.to_thread pushes it to a worker thread so the server
stays responsive to everyone else while one call is in flight.

Requires GEMINI_API_KEY in your .env (see core/config.py).
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
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
# NOTE: gemini-3.1-flash-lite has repeatedly, in live testing, skipped
# calling real tools (check_answer/verify_claim) on consequential turns
# and just narrated a fabricated success instead -- even with every tool
# it needed actually available and explicit instructions not to do this.
# gemini-3.6-flash is the recommended model here; only drop to a lite
# tier if you've specifically retested this exact failure mode against it.
MODEL_NAME = "gemini-3.1-flash-lite"

MAX_TOOL_ITERATIONS = 6
INTERNAL_BASE_URL = "http://localhost:8000"

# conversation_id -> list[types.Content], the REAL Gemini history including
# function_call/function_response parts. See module docstring.
_CONVERSATIONS: dict[str, List[types.Content]] = {}

# Shown to anyone who messages the chat while logged out (no token, or an
# expired/invalid one). Gemini is never called for these -- the reply is
# fixed, so a logged-out visitor can't use the assistant (or burn API quota)
# in any way until they log in.
LOGIN_REQUIRED_REPLY = (
    "Hi! I'm the FindIt Campus assistant -- I can help you report a lost or "
    "found item, check for matches, and claim your item. Please log in to "
    "get started."
)

BASE_SYSTEM_PROMPT_TEMPLATE = """Today's date is {today}. Use this as ground
truth for any date reasoning (e.g. "is this date in the future", "how long
ago was this") -- never guess or assume what today's date is.

You are the FindIt Campus assistant -- a chatbot for VIT's lost-and-found
platform. You can help with:

1. REPORTING a lost or found item.
   First find out whether it is LOST or FOUND (skip this if they already
   said). Then, BEFORE asking for any value, show the person the COMPLETE
   field list for that report type in ONE message, so they know exactly what
   you will need -- marking which fields are mandatory and which are
   optional. Use exactly these lists:

   LOST report:
     Mandatory: title, description, category, location_name (where they lost
     it -- "Not known" is fine if they truly don't know), item_datetime
     (when they lost it).
     Optional: color, brand.

   FOUND report:
     Mandatory: title, description (this is PUBLIC -- anyone browsing can
     read it, so it must not contain the verification answer), category,
     location_name (where it was found), hidden_question, hidden_answer,
     collection_point.
     Optional: color, brand.

   category must be exactly one of: Wallet, Phone, Laptop, ID Card, Keys,
   Bag, Bottle, Earbuds, Books, Other -- list these when you ask for it, and
   if their item doesn't fit, use Other.

   In that same first message also tell them that photos and map
   coordinates can't be added in chat -- they can only be attached through
   the report form (the "Report lost" / "Report found" button), so if they
   want to add photos they should use that instead.

   Then ask for the MANDATORY fields one at a time, in the order listed
   above. Never skip a mandatory field, never combine it with a guess, and
   never fill in a plausible-sounding value yourself -- every value must
   come from something the person actually told you in THIS conversation.
   After the mandatory fields, ask once for each optional field (color,
   brand); if they say skip / don't know, leave it blank and move on.

   Rules for specific fields:
   - LOST item_datetime must not be in the future and cannot be more than
     14 days ago; the backend rejects anything outside that window with a
     422 (relay that message plainly and ask for a more recent date -- or
     tell them to contact the lost & found desk directly for an older
     loss). FOUND reports never need this field; the backend timestamps it
     automatically at submission time.
   - collection_point (FOUND only) must be exactly one of PRP, SJT, or TT --
     ask the person which one; do not accept any other location as the
     collection_point even if that's where the item was actually found --
     the physical finding location goes in location_name, collection_point
     is always one of those three admin desks.
   - NEVER invent hidden_question or hidden_answer, and never infer them
     from other fields (e.g. never make up "what color is it" as the
     question when color was already given publicly). If you cannot point
     to the exact message where the person gave you these two values, STOP
     and ask before going further.
   - For a FOUND report, as soon as you have the description plus the
     hidden_question and hidden_answer, call check_verification to make
     sure the answer doesn't leak from the public description. If it comes
     back leaked: true, tell the person and ask for a better question or
     answer before proceeding.

   When every mandatory field (and the optional ones you asked about) is in
   hand, show a short summary listing EVERY value -- for a FOUND report,
   show the hidden question and answer too -- and ask "Shall I submit
   this?". Call create_report ONLY after they clearly say yes. If they want
   to change something, update it and show the summary again. The backend
   also refuses create_report and lists the missing fields if a mandatory
   one is absent -- if that happens, ask the person for exactly those
   fields; do not retry with guessed values.

   Call create_report ONLY ONCE per item -- if it already succeeded earlier
   in this conversation for this item, do not call it again; reuse the
   report_id you got back. If create_report fails with a timeout or any
   unclear error, do NOT call it again straight away -- the report may
   still have been saved; the system checks for that itself. If a result
   says already_created: true, the report already exists: tell the person
   it's already filed (do not create another). If unsure whether something is allowed beyond
   what's stated here, call create_report and see what happens -- if the
   backend rejects it, relay its exact error message plainly rather than
   guessing why.

   After you successfully create a report, mention these real time-based
   platform behaviors so the person knows what to expect (briefly, one
   sentence, only whichever applies):
   - A LOST report that stays OPEN for 14+ days is marked "stale" and
     shown lower in listings -- NOT deleted, hidden, or blocked, just
     deprioritized so fresher reports get visibility first.
   - A FOUND high-risk item (ID card, phone, laptop, academic documents)
     that stays unclaimed for 7+ days gets ESCALATED for staff follow-up.

   IMPORTANT -- do not re-ask a question the person already answered
   earlier in this same conversation. If they already told you it's a
   LOST item, or already gave you the brand, never ask "are you reporting
   a lost or found item?" or "what's the brand?" again -- move on to
   whatever field you're still missing.

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
   list_my_reports. If they reference a match by a short/truncated id you
   showed earlier, match it against the full ids you already have from an
   earlier find_matches call in this conversation -- use get_match if you
   need full details on a specific one.

3. VERIFYING a claim (the person believes one of the matches is their item).
   This is a REAL, CONSEQUENTIAL action -- you MUST use the actual tools
   below for every step. NEVER narrate, imply, or state that an answer was
   checked, that a claim was verified, that contact info was "unlocked",
   or that any part of this succeeded UNLESS the corresponding tool call
   actually returned that result in THIS conversation. There is no
   "contact info unlock" feature -- do not describe one.
   a) Call get_report(found_report_id) to get the real hidden_question, and
      ask the person that exact question.
   b) Call check_answer(match_id, hidden_answer) with their answer -- ALWAYS,
      for every single answer attempt, no exceptions. This does NOT commit
      anything -- it just tells you correct: true/false. If false, let them
      try again or move to the next candidate match.
   c) If check_answer says correct: true, call verify_claim(match_id,
      hidden_answer) to actually finalize it. You do not need to ask for
      the person's name/email/registration number -- the system fills
      those in automatically from their logged-in account.
   d) Only AFTER verify_claim returns success should you tell the person
      where to collect their item -- use exactly the collection_point
      verify_claim's response gives you. The owner collects it from
      ADMIN at that location -- there is no direct contact with the
      finder. If a tool call fails or returns an error (e.g. 403 because
      the logged-in account isn't the one who filed the lost report), say
      so plainly -- do not paper over it with an invented success message.

4. RESOLVING a disambiguation. Sometimes find_matches returns several
   candidates whose scores are too close to auto-rank -- the person has to
   pick which one is really theirs. If they tell you which match is
   correct, call resolve_disambiguation with that match_id. This confirms
   their pick and rejects the other competing candidates -- make sure the
   person is confident before calling it.

5. DELETING a report. If the person asks to delete, remove, or cancel a
   report:
   a) Make sure you know exactly which report they mean -- if you don't
      already have its report_id from earlier in this conversation, call
      list_my_reports first and match it by title.
   b) Explicitly confirm with them before deleting -- e.g. "Just to
      confirm, delete your report 'Black wallet'? This can't be undone."
      NEVER call delete_report without this confirmation step, even if
      they sound sure -- deletion is irreversible and there is no undo.
   c) Only after they confirm, call delete_report with that report_id.
      The backend will refuse (and you should relay this plainly) if the
      report isn't theirs to delete.

6. VIEWING the custody ledger. If the person asks about past handovers,
   who returned an item, or wants a history of completed claims platform-
   wide, call list_custody_records.

7. VIEWING the person's own claims. If they ask "what have I claimed",
   "when can I pick up my item", or "what's the status of my claim", call
   list_my_claims -- this shows both pending (verified, awaiting physical
   handover) and completed claims for the logged-in person specifically,
   which is different from list_my_reports (their own lost/found reports).

8. ESCALATING stale high-risk items. If explicitly asked to run the
   staleness check (unclaimed high-risk items open 7+ days), call
   escalate_stale_items. This affects other users' reports platform-wide,
   so only call it on an explicit request to run it -- never on your own
   initiative or as a side effect of something else.

9. EXPLAINING how the platform works, if asked: matching combines text +
   photo similarity with location/time proximity into one score; close
   scores trigger a disambiguation question. High-risk items (IDs, phones,
   documents, cards) are auto-flagged and their public photo is pixelated
   until the true owner verifies. Every physical handover is logged in a
   custody ledger. Only @vitstudent.ac.in and @vit.ac.in emails can sign up.
   A confirmation email is sent automatically when a report is created.

Ask clarifying questions one at a time. Keep responses short and
conversational -- this is a chat widget, not an essay. The chat shows plain
text only, so do not use markdown (no ** bold, no # headings); use line
breaks and simple "- " dashes for lists.
"""

ADMIN_SYSTEM_PROMPT_ADDITION = """

You are currently talking to an ADMIN. In addition to everything above, you can:
10. Give a dashboard summary (get_dashboard_summary) -- open lost reports,
    open found reports, unresolved high-risk items, items awaiting pickup.
11. List items awaiting pickup in detail (list_pending_pickups).
12. Confirm a handover (confirm_handover) once the admin explicitly says
    they've physically handed an item to its claimant. Never call this
    just because it was asked about -- only on an explicit confirmation.
13. List the actual reports platform-wide (list_reports). Use it whenever the
    admin asks to see, list, or look up reports -- e.g. "show all found
    reports", "which lost reports are still open", "any high-risk items
    escalated?". Pass report_type ("lost"/"found") and/or status
    ("open"/"matched"/"resolved"/"escalated") when they narrow it down.
    get_dashboard_summary only gives COUNTS of open items -- it is NOT the
    full list, and you must never tell the admin that you can't list
    reports. Present the results as a short, readable list (title, category,
    where, status), and mention the total count.

Note: check_answer/verify_claim will correctly fail (403) if used on a
report that isn't the logged-in admin's own -- only the actual reporter
can verify their own claim. If that happens, relay it plainly rather than
trying to work around it.

Be concise -- a few short lines, not a long report. This is a chat widget.
"""

# Mirrors CATEGORIES in frontend/src/pages/ReportForm.jsx -- keep the two in
# sync. Chat-created reports must use the same fixed list as the form so
# category matching (exact) and high-risk detection (ID Card / Phone /
# Laptop) behave identically no matter how a report was filed.
REPORT_CATEGORIES = [
    "Wallet", "Phone", "Laptop", "ID Card", "Keys",
    "Bag", "Bottle", "Earbuds", "Books", "Other",
]
_CATEGORY_BY_LOWER = {c.lower(): c for c in REPORT_CATEGORIES}

# Mirrors the Building enum (models/building.py).
COLLECTION_POINTS = ("PRP", "SJT", "TT")

# Mandatory fields, matching the * fields on the report form.
_REQUIRED_BASE = ["title", "description", "category", "location_name"]
_REQUIRED_LOST = ["item_datetime"]
_REQUIRED_FOUND = ["hidden_question", "hidden_answer", "collection_point"]

USER_TOOLS = [
    types.FunctionDeclaration(
        name="check_verification",
        description=(
            "Check whether a FOUND report's hidden_question/hidden_answer "
            "would leak from its public description (e.g. the description "
            "already mentions the color and the question asks for the "
            "color). Returns { leaked: bool, reason }. Call this BEFORE "
            "create_report for every FOUND report -- if leaked is true, ask "
            "the person for a better hidden question or answer instead of "
            "proceeding."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "description": types.Schema(type=types.Type.STRING),
                "hidden_question": types.Schema(type=types.Type.STRING),
                "hidden_answer": types.Schema(type=types.Type.STRING),
            },
            required=["description", "hidden_question", "hidden_answer"],
        ),
    ),
    types.FunctionDeclaration(
        name="create_report",
        description=(
            "Create a lost or found item report. Only call this after the "
            "person has seen the full field list, you have explicitly asked "
            "for and received EVERY mandatory field, shown them a summary "
            "and they said yes. Mandatory for LOST: title, description, "
            "category, location_name, item_datetime (not in the future, not "
            "more than 14 days ago). Mandatory for FOUND: title, "
            "description, category, location_name, hidden_question, "
            "hidden_answer, collection_point (exactly 'PRP', 'SJT', or "
            "'TT'), and you must already have called check_verification "
            "and confirmed leaked was false. color and brand are optional. "
            "The server rejects the call and lists what is missing if a "
            "mandatory field is absent. Call this at most once per item "
            "per conversation."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "report_type": types.Schema(type=types.Type.STRING, enum=["lost", "found"]),
                "title": types.Schema(type=types.Type.STRING),
                "description": types.Schema(type=types.Type.STRING),
                "category": types.Schema(
                    type=types.Type.STRING,
                    enum=REPORT_CATEGORIES,
                    description="Mandatory. Must be one of the listed categories -- use 'Other' if nothing fits.",
                ),
                "color": types.Schema(type=types.Type.STRING, description="Optional."),
                "brand": types.Schema(type=types.Type.STRING, description="Optional."),
                "location_name": types.Schema(
                    type=types.Type.STRING,
                    description="Mandatory. Where it was lost (LOST) or found (FOUND).",
                ),
                "item_datetime": types.Schema(
                    type=types.Type.STRING,
                    description=(
                        "Required for LOST reports only -- when the person lost "
                        "the item. Not needed for FOUND reports (the backend "
                        "sets it to the current time automatically). Must not "
                        "be in the future, and must be within the last 14 days "
                        "-- the backend rejects anything older with a 422."
                    ),
                ),
                "hidden_question": types.Schema(type=types.Type.STRING, description="FOUND reports only -- required"),
                "hidden_answer": types.Schema(type=types.Type.STRING, description="FOUND reports only -- required"),
                "collection_point": types.Schema(
                    type=types.Type.STRING,
                    enum=["PRP", "SJT", "TT"],
                    description="FOUND reports only -- required. Must be exactly PRP, SJT, or TT.",
                ),
            },
            required=["report_type", "title", "description"],
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
        name="get_match",
        description=(
            "Fetch full details for a single match by its id -- scores, "
            "status, and (if you're a party to a CONFIRMED match) contact "
            "info. If the person references a match by a short/truncated id "
            "you showed earlier, resolve it against the full ids you already "
            "have from an earlier find_matches call in this conversation "
            "rather than asking them to retype it in full."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"match_id": types.Schema(type=types.Type.STRING)},
            required=["match_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_my_reports",
        description=(
            "List the current logged-in user's own lost/found reports (id, title, "
            "report_type, status). ALWAYS call this before answering any question "
            "like 'is there a match', 'what's the status of my report', or 'did "
            "anyone find my X' -- you cannot know this without checking. Also use "
            "this to look up a report_id before deleting a report if you don't "
            "already have it. Never say there are no reports or no matches without "
            "calling this (and, for a specific report, find_matches) first in this "
            "conversation."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="list_my_claims",
        description=(
            "List the current logged-in user's own claims -- both pending "
            "(verified but not yet physically handed over) and completed. "
            "Use this for questions like 'what have I claimed', 'when can I "
            "pick up my item', or 'what's the status of my claim'. This is "
            "different from list_my_reports (their own lost/found reports) -- "
            "this is about items THEY are collecting, not items they reported."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="check_answer",
        description="Check whether an answer to a match's hidden_question is correct, WITHOUT finalizing the claim. Use this before verify_claim, for EVERY answer attempt.",
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
    types.FunctionDeclaration(
        name="resolve_disambiguation",
        description=(
            "Confirm which match is the person's real item when find_matches "
            "returned several close-scoring candidates needing disambiguation. "
            "This promotes the chosen match and rejects the other competing "
            "candidates -- only call it once the person has clearly told you "
            "which specific match is correct."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"match_id": types.Schema(type=types.Type.STRING)},
            required=["match_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_custody_records",
        description="List the full custody ledger -- every completed handover, who returned what to whom and when. Use this if the person asks about handover history or past claims.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="escalate_stale_items",
        description=(
            "Run the staleness sweep: flags high-risk FOUND items that have "
            "been open 7+ days as ESCALATED. Affects the whole platform, not "
            "just this person's items -- only call this if explicitly asked "
            "to run/trigger the escalation or staleness check."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="delete_report",
        description=(
            "Permanently delete a lost/found report by its id. This is "
            "IRREVERSIBLE. Only the person who created the report can delete "
            "it -- the backend enforces this, so it will fail if the report "
            "isn't theirs. NEVER call this without the person explicitly "
            "confirming they want to delete THIS specific report -- if they "
            "just say 'delete my report' without confirming which one or "
            "confirming they're sure, ask first."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"report_id": types.Schema(type=types.Type.STRING)},
            required=["report_id"],
        ),
    ),
]

ADMIN_TOOLS = [
    types.FunctionDeclaration(
        name="list_reports",
        description=(
            "Admin only. List the actual lost/found reports across the whole "
            "platform (not just the admin's own). Optionally filter by "
            "report_type ('lost' or 'found') and/or status ('open', "
            "'matched', 'resolved', 'escalated'). Use this when the admin "
            "asks to see/list/look up reports. Returns total count plus, per "
            "report: id, title, report_type, status, category, color, brand, "
            "location_name, collection_point, is_high_risk, days_open, "
            "created_at, reporter_name."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "report_type": types.Schema(type=types.Type.STRING, enum=["lost", "found"]),
                "status": types.Schema(
                    type=types.Type.STRING,
                    enum=["open", "matched", "resolved", "escalated"],
                ),
            },
        ),
    ),
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


# create_report can legitimately take a while (the first report after a
# server restart loads the text-embedding model before it can respond), so it
# gets a much longer timeout than ordinary tool calls. A short timeout was a
# duplicate-report trap: the client gave up, but the backend finished and
# saved the report anyway, and the model then "retried".
CREATE_REPORT_TIMEOUT = 120

# An identical report (same type, title and description) by the same person
# within this window is treated as the SAME report, not a new one.
DUPLICATE_WINDOW_MINUTES = 10


def _norm_text(value) -> str:
    return " ".join(str(value or "").lower().split())


def _parse_utc(value) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _find_recent_duplicate(client_http: httpx.AsyncClient, payload: dict) -> Optional[dict]:
    """
    Looks for a report this user already filed moments ago with the same
    type + title + description. Used (a) before every create_report, so a
    model that calls it twice -- or twice in one turn, or "retries" after a
    timeout -- can't file the same item twice, and (b) after a timeout, to
    find out whether the report was actually saved. Returns that existing
    report (as the API serialised it), or None.
    """
    me_resp = await client_http.get("/auth/me")
    if me_resp.status_code != 200:
        return None
    my_id = me_resp.json().get("id")

    resp = await client_http.get("/reports/", params={"report_type": payload["report_type"]})
    if resp.status_code != 200:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    wanted_title = _norm_text(payload.get("title"))
    wanted_desc = _norm_text(payload.get("description"))
    for r in resp.json():
        if r.get("reporter_id") != my_id:
            continue
        created = _parse_utc(r.get("created_at"))
        if created is None or created < cutoff:
            continue
        if _norm_text(r.get("title")) == wanted_title and _norm_text(r.get("description")) == wanted_desc:
            return r
    return None


def _already_created(existing: dict) -> dict:
    return {
        **existing,
        "already_created": True,
        "note": (
            "This report was already created moments ago, so nothing new was "
            "created. Tell the person it is already filed and reuse this id."
        ),
    }


def _prepare_report_payload(tool_input: dict) -> tuple[dict, Optional[dict]]:
    """
    Server-side gate for create_report: the model is told in the prompt to
    collect every mandatory field, but a prompt can't force it to. This
    runs BEFORE anything is sent to POST /reports/ and refuses the call --
    returning a message the model can act on -- if a mandatory field is
    missing or invalid. Also cleans the payload: trims whitespace, drops
    blank optional fields, and snaps category / collection_point to their
    canonical spelling ("id card" -> "ID Card", "prp" -> "PRP").

    Returns (clean_payload, problem). problem is None when it's OK to submit.
    """
    data = {}
    for key, value in tool_input.items():
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            continue
        data[key] = value

    report_type = str(data.get("report_type", "")).lower()
    if report_type not in ("lost", "found"):
        return data, {
            "error": "report_type must be 'lost' or 'found'.",
            "instruction": "Do NOT create the report yet -- ask the person whether the item is lost or found.",
        }
    data["report_type"] = report_type

    required = _REQUIRED_BASE + (_REQUIRED_LOST if report_type == "lost" else _REQUIRED_FOUND)
    missing = [f for f in required if f not in data]
    invalid = {}

    if "category" in data:
        canonical = _CATEGORY_BY_LOWER.get(str(data["category"]).lower())
        if canonical:
            data["category"] = canonical
        else:
            invalid["category"] = "must be one of: " + ", ".join(REPORT_CATEGORIES)

    if "collection_point" in data:
        point = str(data["collection_point"]).upper()
        if point in COLLECTION_POINTS:
            data["collection_point"] = point
        else:
            invalid["collection_point"] = "must be exactly one of: " + ", ".join(COLLECTION_POINTS)

    if missing or invalid:
        return data, {
            "error": "Report NOT created -- mandatory information is missing or invalid.",
            "missing_fields": missing,
            "invalid_fields": invalid,
            "instruction": (
                "Do NOT retry with guessed or invented values. Ask the person, "
                "one at a time, for each missing/invalid field, then show the "
                "summary and get their yes before calling create_report again."
            ),
        }

    return data, None


# Cap on how many reports one list_reports call hands back to the model, so a
# big platform can't blow up the context window. `total` always reports the
# real count, and `truncated` tells the model (and so the admin) more exist.
LIST_REPORTS_MAX = 50


async def _list_reports(client_http: httpx.AsyncClient, tool_input: dict) -> dict:
    """
    Admin-only list of reports, built from the existing GET /reports/ (which
    already returns every report to an admin and takes a report_type filter).
    Trimmed to the fields the assistant actually needs -- no photo paths,
    embeddings, or hidden answers -- and only the reporter's NAME (no
    email/phone) is passed along, to keep personal details out of the model
    context.
    """
    params = {}
    if tool_input.get("report_type"):
        params["report_type"] = tool_input["report_type"]

    resp = await client_http.get("/reports/", params=params)
    if resp.status_code != 200:
        return {"error": resp.text, "status_code": resp.status_code}

    reports = resp.json()
    wanted_status = tool_input.get("status")
    if wanted_status:
        reports = [r for r in reports if r.get("status") == wanted_status]

    trimmed = [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "report_type": r.get("report_type"),
            "status": r.get("status"),
            "category": r.get("category"),
            "color": r.get("color"),
            "brand": r.get("brand"),
            "location_name": r.get("location_name"),
            "collection_point": r.get("collection_point"),
            "is_high_risk": r.get("is_high_risk"),
            "days_open": r.get("days_open"),
            "created_at": r.get("created_at"),
            "reporter_name": (r.get("reporter") or {}).get("name"),
        }
        for r in reports[:LIST_REPORTS_MAX]
    ]
    return {
        "total": len(reports),
        "returned": len(trimmed),
        "truncated": len(reports) > LIST_REPORTS_MAX,
        "reports": trimmed,
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
            if name == "check_verification":
                resp = await h.post("/reports/check-verification", json=tool_input)
            elif name == "create_report":
                payload, problem = _prepare_report_payload(tool_input)
                if problem:
                    return problem

                # Never file the same item twice (see _find_recent_duplicate).
                existing = await _find_recent_duplicate(h, payload)
                if existing:
                    return _already_created(existing)

                try:
                    resp = await h.post("/reports/", json=payload, timeout=CREATE_REPORT_TIMEOUT)
                except httpx.TimeoutException:
                    # The backend may have finished saving even though we
                    # stopped waiting -- check before telling the model it
                    # failed, or it will retry and create a duplicate.
                    existing = await _find_recent_duplicate(h, payload)
                    if existing:
                        return _already_created(existing)
                    return {
                        "error": (
                            "The request timed out and the report does not appear "
                            "to have been saved. Tell the person it didn't go "
                            "through and ask if they'd like to try again."
                        )
                    }
            elif name == "find_matches":
                resp = await h.post(f"/matches/find/{tool_input['report_id']}")
            elif name == "get_report":
                resp = await h.get(f"/reports/{tool_input['report_id']}")
            elif name == "get_match":
                resp = await h.get(f"/matches/{tool_input['match_id']}")
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
            elif name == "list_my_claims":
                resp = await h.get("/custody/mine/claims")
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
            elif name == "resolve_disambiguation":
                resp = await h.post(f"/matches/{tool_input['match_id']}/disambiguate")
            elif name == "list_custody_records":
                resp = await h.get("/custody/")
            elif name == "escalate_stale_items":
                resp = await h.post("/reports/escalate-stale")
            elif name == "delete_report":
                resp = await h.delete(f"/reports/{tool_input['report_id']}")
            elif name == "get_dashboard_summary":
                return await _get_dashboard_summary(h)
            elif name == "list_reports":
                return await _list_reports(h, tool_input)
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
    # Logged-out (or expired-token) visitors only ever get the fixed intro +
    # "please log in" reply -- no Gemini call, no tools, no stored history.
    if user is None:
        return ChatResponse(
            reply=LOGIN_REQUIRED_REPLY,
            conversation_id=req.conversation_id or "",
        )

    is_admin = user.is_admin == "true"

    conversation_id = req.conversation_id or str(uuid.uuid4())
    # History is keyed by BOTH the user and the conversation_id, so one
    # account can never continue (or read the tool results of) another
    # account's conversation, even if the same browser tab is reused.
    conv_key = f"{user.id}:{conversation_id}"
    contents = _CONVERSATIONS.get(conv_key, [])

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    system_prompt = BASE_SYSTEM_PROMPT_TEMPLATE.format(today=today_str) + (
        ADMIN_SYSTEM_PROMPT_ADDITION if is_admin else ""
    )
    declarations = USER_TOOLS + (ADMIN_TOOLS if is_admin else [])

    contents.append(types.Content(role="user", parts=[types.Part(text=req.message)]))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=declarations)],
    )

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            # See module docstring "WHY generate_content runs in a thread".
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )
        except Exception:
            import traceback
            traceback.print_exc()
            return ChatResponse(
                reply="The assistant is a bit busy right now -- please try again in a moment.",
                conversation_id=conversation_id,
            )

        candidate_parts = response.candidates[0].content.parts
        function_calls = [p.function_call for p in candidate_parts if p.function_call]

        if not function_calls:
            reply_text = "".join(p.text for p in candidate_parts if p.text)
            contents.append(types.Content(role="model", parts=[types.Part(text=reply_text)]))
            _CONVERSATIONS[conv_key] = contents
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

    _CONVERSATIONS[conv_key] = contents
    return ChatResponse(
        reply="I'm having trouble finishing that request right now -- could you try rephrasing, or use the regular form instead?",
        conversation_id=conversation_id,
    )