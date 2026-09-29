import { useCallback, useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  Layers3,
  Loader2,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { fetchInspectionPapers, fetchPaperChunks, originalPdfUrl } from '../api';

const PAGE_SIZE = 30;

function Badge({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-600',
    cyan: 'bg-cyan-50 text-cyan-700',
    violet: 'bg-violet-50 text-violet-700',
  };
  return <span className={`rounded-full px-2 py-0.5 text-[10px] ${tones[tone]}`}>{children}</span>;
}

export default function KnowledgePanel() {
  const [tab, setTab] = useState('knowledge');
  const [overview, setOverview] = useState(null);
  const [viewer, setViewer] = useState(null);
  const [selectedPaper, setSelectedPaper] = useState('');
  const [level, setLevel] = useState('children');
  const [chunkPage, setChunkPage] = useState(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      setOverview(await fetchInspectionPapers());
    } catch (error) {
      setMessage(error.message);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadChunks = async (paperId, nextLevel = level, nextOffset = 0) => {
    setSelectedPaper(paperId);
    setLevel(nextLevel);
    setOffset(nextOffset);
    setLoading(true);
    setMessage('');
    try {
      setChunkPage(await fetchPaperChunks(paperId, nextLevel, nextOffset, PAGE_SIZE));
    } catch (error) {
      setMessage(error.message);
    }
    setLoading(false);
  };

  const refresh = loadOverview;

  return (
    <div className="p-4 space-y-4">
      <div className="grid grid-cols-2 rounded-lg bg-gray-100 p-1">
        <button onClick={() => setTab('knowledge')} className={`rounded-md py-1.5 text-xs ${tab === 'knowledge' ? 'bg-white font-medium text-gray-800 shadow-sm' : 'text-gray-500'}`}>
          知识库 / RAG
        </button>
        <button onClick={() => setTab('papers')} className={`rounded-md py-1.5 text-xs ${tab === 'papers' ? 'bg-white font-medium text-gray-800 shadow-sm' : 'text-gray-500'}`}>
          查看上传的论文
        </button>
      </div>

      <div className="flex items-start justify-between gap-3 rounded-xl border border-violet-100 bg-violet-50 p-3">
        <div className="flex items-start gap-2">
          {tab === 'knowledge' ? <Database size={15} className="mt-0.5 text-violet-600" /> : <FileText size={15} className="mt-0.5 text-violet-600" />}
          <div>
            <p className="text-xs font-semibold text-violet-900">{tab === 'knowledge' ? '可检查的知识索引' : '上传论文原文件'}</p>
            <p className="mt-1 text-[11px] leading-relaxed text-violet-700">
              {tab === 'knowledge' ? '查看论文如何被解析为父块、子块，以及 RAG 使用的真实文本。' : '所有已上传论文都可在这里预览或打开原始 PDF，内容未经改写。'}
            </p>
          </div>
        </div>
        <button onClick={refresh} disabled={loading} className="text-violet-500 disabled:opacity-40" title="Refresh">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      {message && <p className="rounded-lg bg-red-50 px-3 py-2 text-[11px] text-red-600">{message}</p>}

      {tab === 'knowledge' && overview && (
        <>
          <section className="rounded-xl border border-gray-200 p-3">
            <p className="text-xs font-semibold text-gray-800">当前 RAG 管线</p>
            <p className="mt-1 text-[11px] leading-relaxed text-gray-500">{overview.rag.retrieval}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              <Badge tone="cyan">Top-K {overview.rag.top_k}</Badge>
              <Badge tone="cyan">Fetch-K {overview.rag.fetch_k}</Badge>
              <Badge tone="cyan">RRF-K {overview.rag.rrf_k}</Badge>
              <Badge tone="violet">缓存 {overview.rag.cache_entries} 条</Badge>
            </div>
            <p className="mt-2 break-all text-[10px] text-gray-400">Embedding: {overview.rag.embedding_model}</p>
            <p className="break-all text-[10px] text-gray-400">Reranker: {overview.rag.reranker_model}</p>
          </section>

          {(overview.papers || []).map((paper) => (
            <section key={paper.paper_id} className="rounded-xl border border-gray-200 p-3">
              <div className="flex items-start gap-2">
                <FileText size={14} className="mt-0.5 shrink-0 text-gray-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-gray-800">{paper.filename}</p>
                  <p className="mt-0.5 text-[10px] text-gray-400">{paper.page_count} 页 · {paper.size_bytes?.toLocaleString()} bytes</p>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                <Badge tone="cyan">子块 {paper.index.children}</Badge>
                <Badge tone="violet">父块 {paper.index.parents}</Badge>
                {Object.entries(paper.index.node_types || {}).slice(0, 5).map(([name, count]) => <Badge key={name}>{name} {count}</Badge>)}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                <button onClick={() => loadChunks(paper.paper_id, 'children', 0)} className="rounded-md border border-cyan-100 bg-cyan-50 py-1.5 text-[11px] text-cyan-700">查看子块</button>
                <button onClick={() => loadChunks(paper.paper_id, 'parents', 0)} className="rounded-md border border-violet-100 bg-violet-50 py-1.5 text-[11px] text-violet-700">查看父块</button>
              </div>
            </section>
          ))}

          {chunkPage && selectedPaper && (
            <section className="space-y-2 border-t border-gray-100 pt-4">
              <div className="flex items-center justify-between">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-gray-800"><Layers3 size={13} /> {level === 'children' ? '子块' : '父块'} {offset + 1}–{Math.min(offset + PAGE_SIZE, chunkPage.total)} / {chunkPage.total}</p>
                <div className="flex gap-1">
                  <button disabled={offset === 0 || loading} onClick={() => loadChunks(selectedPaper, level, Math.max(0, offset - PAGE_SIZE))} className="rounded p-1 hover:bg-gray-100 disabled:opacity-30"><ChevronLeft size={13} /></button>
                  <button disabled={offset + PAGE_SIZE >= chunkPage.total || loading} onClick={() => loadChunks(selectedPaper, level, offset + PAGE_SIZE)} className="rounded p-1 hover:bg-gray-100 disabled:opacity-30"><ChevronRight size={13} /></button>
                </div>
              </div>
              {chunkPage.items.map((chunk) => (
                <details key={chunk.chunk_id} className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                  <summary className="cursor-pointer text-[11px] font-medium text-gray-700">P{chunk.page} · {chunk.node_type} · {chunk.section || 'No section'}</summary>
                  <p className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-gray-600">{chunk.text}</p>
                  {chunk.vlm_description && <p className="mt-2 rounded bg-violet-50 p-2 text-[10px] text-violet-700">VLM: {chunk.vlm_description}</p>}
                  <p className="mt-2 break-all font-mono text-[9px] text-gray-400">chunk {chunk.chunk_id}{chunk.parent_id ? ` · parent ${chunk.parent_id}` : ''}</p>
                </details>
              ))}
            </section>
          )}
        </>
      )}

      {tab === 'papers' && overview && (
        <>
          <section className="space-y-2">
            {(overview.papers || []).length === 0 && <p className="rounded-lg bg-gray-50 p-3 text-xs text-gray-500">尚未上传论文。</p>}
            {(overview.papers || []).map((paper) => (
              <article key={paper.file_id} className="rounded-xl border border-gray-200 p-3">
                <div className="flex items-start gap-2">
                  <FileText size={14} className="mt-0.5 shrink-0 text-violet-500" />
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-xs font-semibold text-gray-800">{paper.filename}</p>
                    <p className="mt-1 text-[10px] text-gray-400">{paper.page_count} 页 · {(paper.size_bytes / 1024 / 1024).toFixed(1)} MB · {paper.index.children} 个检索块</p>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button onClick={() => setViewer(paper)} className="rounded-md bg-violet-600 py-1.5 text-[11px] font-medium text-white">在此预览</button>
                  <a href={originalPdfUrl(paper.file_id)} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-1 rounded-md border border-violet-200 py-1.5 text-[11px] text-violet-700"><ExternalLink size={11} />打开原文件</a>
                </div>
              </article>
            ))}
          </section>
          {viewer && (
            <section className="overflow-hidden rounded-xl border border-gray-200 bg-gray-50">
              <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
                <p className="min-w-0 truncate text-[11px] font-medium text-gray-700">{viewer.filename}</p>
                <button onClick={() => setViewer(null)} className="text-[10px] text-gray-500">关闭预览</button>
              </div>
              <iframe title={`原始论文 ${viewer.filename}`} src={`${originalPdfUrl(viewer.file_id)}#toolbar=1&navpanes=0`} className="h-[70vh] w-full bg-white" />
            </section>
          )}
        </>
      )}
    </div>
  );
}
