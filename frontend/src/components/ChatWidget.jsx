import { useState, useRef, useEffect } from 'react';
import { sendChatMessage } from '../api/client';

// Floating chat widget, mounted once in App.jsx so it's available on every
// page. Keeps conversation history in React state only -- refreshing the
// page starts a new conversation, which is fine for a lost & found helper.
export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]); // [{ role, content }]
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const nextMessages = [...messages, { role: 'user', content: text }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      const res = await sendChatMessage(text, messages);
      setMessages([...nextMessages, { role: 'assistant', content: res.reply }]);
    } catch (err) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: "Sorry, I couldn't reach the assistant. Please try again." },
      ]);
    } finally {
      setLoading(false);
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
              <div key={i} className={`chat-widget__bubble chat-widget__bubble--${m.role}`}>
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
        {open ? '×' : '💬'}
      </button>
    </div>
  );
}