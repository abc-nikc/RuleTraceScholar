import ReactMarkdown from 'react-markdown';
import { User, Bot, ChevronDown, ChevronRight, Upload, CircleHelp, Sparkles, Search } from 'lucide-react';
import { useState } from 'react';
import ExplanationPanel from './ExplanationPanel';
import AuditPanel from './AuditPanel';

function CitationList({ citations, subQueries }) {
  const [open, setOpen] = useState(false);
  if ((!citations || citations.length === 0) && (!subQueries || subQueries.length === 0)) return null;

  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        RAG 轨迹 · {citations?.length || 0} 条证据
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {(subQueries || []).length > 0 && (
            <div className="rounded-lg border border-cyan-100 bg-cyan-50 px-3 py-2">
              <p className="text-[11px] font-semibold text-cyan-800">智能体查询分解</p>
              <ol className="mt-1 space-y-0.5 text-[10px] leading-relaxed text-cyan-700">
                {subQueries.map((query, index) => <li key={index}>{index + 1}. {query}</li>)}
              </ol>
            </div>
          )}
          {(citations || []).map((c, i) => (
            <div key={i} className="text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
              <div className="flex flex-wrap items-center gap-1">
                <span className="font-medium text-gray-700">[{i + 1}]</span>
                {c.retrieval_rank && <span className="rounded bg-cyan-50 px-1.5 py-0.5 text-[9px] text-cyan-700">rank {c.retrieval_rank}</span>}
                {typeof c.retrieval_relevance === 'number' && <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[9px] text-violet-700">relevance {c.retrieval_relevance.toFixed(3)}</span>}
                {c.node_type && <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[9px] text-gray-600">{c.node_type}</span>}
              </div>
              <p className="mt-1 text-[10px] text-gray-500">{[c.paper_id, c.section, c.page && `Page ${c.page}`].filter(Boolean).join(' | ') || 'Unknown source'}</p>
              {c.evidence_excerpt && (
                <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-gray-500">
                  {c.evidence_excerpt}
                </p>
              )}
              {c.chunk_id && <p className="mt-1 break-all font-mono text-[9px] text-gray-400">chunk {c.chunk_id}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ role, content, citations, explanation, claimTests, capsule, repair, subQueries }) {
  const isUser = role === 'user';

  return (
    <div className={`flex gap-4 ${isUser ? 'justify-end' : ''}`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center shrink-0 mt-1">
          <Bot size={15} className="text-gray-500" />
        </div>
      )}
      <div className={`max-w-[90%] sm:max-w-[75%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? 'bg-black text-white'
              : 'bg-gray-50 text-gray-800 border border-gray-100'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="prose prose-sm prose-gray max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </div>
        {!isUser && <CitationList citations={citations} subQueries={subQueries} />}
        {!isUser && <ExplanationPanel explanation={explanation} />}
        {!isUser && <AuditPanel claimTests={claimTests} capsule={capsule} repair={repair} />}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-black flex items-center justify-center shrink-0 mt-1">
          <User size={15} className="text-white" />
        </div>
      )}
    </div>
  );
}

export default function ChatMessages({ messages, loading, onOpenUpload, onOpenGuide, onOpenDiscovery }) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {messages.length === 0 && !loading && (
          <div className="mx-auto mt-8 max-w-xl text-center text-gray-400 sm:mt-24">
            <Bot size={40} className="mx-auto mb-4 text-gray-300" />
            <p className="text-lg font-medium text-gray-500">RuleTrace Scholar</p>
            <p className="mt-1 text-sm">上传论文后可直接一键精读，无需自己设计问题</p>
            <div className="mt-6 grid grid-cols-1 gap-3 text-left sm:grid-cols-3">
              <button
                type="button"
                onClick={onOpenDiscovery}
                className="rounded-xl border border-cyan-100 bg-cyan-50/50 p-4 transition-colors hover:border-cyan-200 hover:bg-cyan-50"
              >
                <Search size={18} className="mb-2 text-cyan-600" />
                <p className="text-sm font-medium text-cyan-900">发现真实论文</p>
                <p className="mt-1 text-xs leading-relaxed text-cyan-600">检索 arXiv、Semantic Scholar 与 Crossref，并可信导入全文</p>
              </button>
              <button
                type="button"
                onClick={onOpenUpload}
                className="rounded-xl border border-gray-200 p-4 transition-colors hover:border-gray-300 hover:bg-gray-50"
              >
                <Upload size={18} className="mb-2 text-gray-500" />
                <p className="text-sm font-medium text-gray-700">上传论文</p>
                <p className="mt-1 text-xs leading-relaxed text-gray-400">导入 PDF，完成结构解析与知识库索引</p>
              </button>
              <button
                type="button"
                onClick={onOpenGuide}
                className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 transition-colors hover:border-indigo-200 hover:bg-indigo-50"
              >
                <Sparkles size={18} className="mb-2 text-indigo-500" />
                <p className="text-sm font-medium text-indigo-800">智能研究向导</p>
                <p className="mt-1 text-xs leading-relaxed text-indigo-500">一键精读、方法解析、实验核查和创新提炼</p>
              </button>
            </div>
            <button
              type="button"
              onClick={onOpenGuide}
              className="mt-4 inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600"
            >
              <CircleHelp size={13} /> 查看所有功能及使用方法
            </button>
          </div>
        )}
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            role={m.role}
            content={m.content}
            citations={m.citations}
            explanation={m.explanation}
            claimTests={m.claim_tests}
            capsule={m.capsule}
            repair={m.repair}
            subQueries={m.sub_queries}
          />
        ))}
        {loading && !messages.some((m) => m.role === 'assistant' && !m.finalized) && (
          <div className="flex gap-4">
            <div className="w-7 h-7 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
              <Bot size={15} className="text-gray-500" />
            </div>
            <div className="bg-gray-50 rounded-2xl px-4 py-3 border border-gray-100">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
