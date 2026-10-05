import { useState, useRef, useEffect } from 'react';
import { sendChatMessage } from '../api/client';
import { useAuth } from '../context/AuthContext';

// Floating chat widget, mounted once in App.jsx so it's available on every
// page. Message BUBBLES are kept in React state for display only. The
// actual conversation memory Gemini uses lives server-side, keyed by
// conversationId -- see backend/app/routers/chatbot.py's module docstring
// for why (short version: keeping tool-call results server-side stops the
// assistant from "forgetting" it already created a report or found a
// match on an earlier turn). Refreshing the page starts a new
// conversation either way, which is fine for a lost & found helper.
//
// The chat is also wiped whenever the logged-in account changes (logout,
// login, or a different user signing in) -- this widget stays mounted
// across all of those, so without the reset below the next person would
// inherit the previous person's bubbles and server-side conversation.
export default function ChatWidget() {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]); // [{ role, content }] -- display only
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  // Bumped every time the account changes. A reply that was still in flight
  // when that happened belongs to the OLD session, so handleSend compares
  // against this and drops it instead of showing it to the new user.
  const sessionRef = useRef(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  // Keyed on the user's id (not the user object) so refreshUser() returning
  // a fresh object for the SAME account doesn't wipe the chat.
  useEffect(() => {
    sessionRef.current += 1;
    setMessages([]);
    setConversationId(null);
    setInput('');
    setLoading(false);
  }, [userId]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const mySession = sessionRef.current;
    const nextMessages = [...messages, { role: 'user', content: text }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      const res = await sendChatMessage(text, conversationId);
      if (mySession !== sessionRef.current) return; // account changed mid-request
      // Logged-out replies come back with an empty conversation_id; keep it
      // null so nothing stale is sent along after the next login.
      setConversationId(res.conversation_id || null);
      setMessages([...nextMessages, { role: 'assistant', content: res.reply }]);
    } catch (err) {
      if (mySession !== sessionRef.current) return;
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: "Sorry, I couldn't reach the assistant. Please try again." },
      ]);
    } finally {
      if (mySession === sessionRef.current) setLoading(false);
    }
  }

  return (
    <div className="chat-widget">
      {open && (
        <div className="chat-widget__panel">
          <div className="chat-widget__header">
            <span>FindIt Assistant</span>
            <button onClick={() => setOpen(false)} aria-label="Close chat">×</button>
          </div>

          <div className="chat-widget__messages">
            {messages.length === 0 && (
              <div className="chat-widget__empty">
                Hi! Lost or found something on campus? Tell me about it and I'll help.
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`chat-widget__bubble chat-widget__bubble--${m.role}`}
                // Keeps the assistant's line breaks (field lists, summaries) instead of
                // collapsing them into one paragraph.
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {m.content}
              </div>
            ))}
            {loading && <div className="chat-widget__bubble chat-widget__bubble--assistant">...</div>}
            <div ref={bottomRef} />
          </div>

          <form className="chat-widget__input-row" onSubmit={handleSend}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>Send</button>
          </form>
        </div>
      )}

      <button className="chat-widget__toggle" onClick={() => setOpen((o) => !o)} aria-label="Toggle chat">
        {open ? (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
            <path
              d="M18 6 6 18M6 6l12 12"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true">
            <path
              d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.5 8.5 0 0 1 21 11.5Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
    </div>
  );
}