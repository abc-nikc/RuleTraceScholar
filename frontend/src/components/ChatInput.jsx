import { useState, useRef } from 'react';
import { Send, BookOpenCheck } from 'lucide-react';

export default function ChatInput({ onSend, disabled, scopeLabel }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e) => {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      {scopeLabel && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center gap-1.5 px-1 text-[11px] text-indigo-600">
          <BookOpenCheck size={12} />
          <span className="truncate">当前对话限定论文：{scopeLabel}</span>
        </div>
      )}
      <div className="max-w-3xl mx-auto flex items-end gap-3 bg-gray-50 rounded-2xl border border-gray-200 px-4 py-2">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder="Ask a question about your papers..."
          rows={1}
          className="flex-1 resize-none bg-transparent outline-none text-sm text-gray-800 placeholder-gray-400 max-h-[200px]"
          disabled={disabled}
        />
        <button
          onClick={handleSubmit}
          aria-label="Send message"
          title="Send message"
          disabled={disabled || !text.trim()}
          className="p-2 rounded-lg bg-black text-white hover:bg-gray-800 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
