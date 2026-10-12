import { useState, useRef } from 'react';
import { Send, BookOpenCheck, Brain, Bot, Zap } from 'lucide-react';

export default function ChatInput({ onSend, disabled, scopeLabel, deepThinking, onDeepThinkingChange, modelProfile }) {
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
      <div className="mx-auto mb-2 flex max-w-3xl flex-wrap items-center justify-between gap-2 px-1">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDeepThinkingChange(!deepThinking)}
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-50 ${
            deepThinking
              ? 'border-violet-200 bg-violet-50 text-violet-700'
              : 'border-amber-200 bg-amber-50 text-amber-700'
          }`}
          title={deepThinking ? '适合复杂推理，纯 CPU 会明显更慢' : '适合日常检索问答'}
        >
          {deepThinking ? <Brain size={12} /> : <Zap size={12} />}
          {deepThinking ? '深度思考' : '快速回答'}
        </button>
        <div className="flex min-w-0 items-center gap-2">
          {modelProfile?.model && (
            <span className="inline-flex max-w-[14rem] items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-600" title={`${modelProfile.provider} · ${modelProfile.base_url}`}>
              <Bot size={11} className="shrink-0" />
              <span className="truncate">{modelProfile.provider === 'ollama' ? '本地' : 'API'} · {modelProfile.model}</span>
            </span>
          )}
          <span className="text-[10px] text-gray-400">
            {deepThinking ? '质量优先 · 响应较慢' : '速度优先 · 可随时切换'}
          </span>
        </div>
      </div>
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
