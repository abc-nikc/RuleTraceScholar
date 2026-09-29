import { useEffect, useState } from 'react';
import { BookOpenCheck, Download, ExternalLink, FileSearch, Loader2, Search } from 'lucide-react';
import {
  discoverFromUploadedPaper,
  fetchFiles,
  importArxivPaper,
  searchAcademicPapers,
} from '../api';

function ProviderBadges({ providers }) {
  if (!providers.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {providers.map((provider) => (
        <span key={provider.provider} className={`rounded-full px-2 py-0.5 text-[10px] ${provider.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
          {provider.provider}: {provider.ok ? `${provider.count} results` : 'unavailable'}
        </span>
      ))}
    </div>
  );
}

export default function DiscoveryPanel({ onImported, onAnalyze, disabled }) {
  const [files, setFiles] = useState([]);
  const [selectedFileId, setSelectedFileId] = useState('');
  const [network, setNetwork] = useState(null);
  const [tab, setTab] = useState('references');
  const [loadingNetwork, setLoadingNetwork] = useState(false);
  const [query, setQuery] = useState('');
  const [keywordResults, setKeywordResults] = useState([]);
  const [keywordProviders, setKeywordProviders] = useState([]);
  const [searching, setSearching] = useState(false);
  const [importing, setImporting] = useState('');
  const [message, setMessage] = useState('');
  const [imported, setImported] = useState({});

  useEffect(() => {
    fetchFiles().then((items) => {
      setFiles(items || []);
      setSelectedFileId((current) => current || items?.[0]?.file_id || '');
    }).catch((error) => setMessage(error.message));
  }, []);

  const analyzeUploadedPaper = async () => {
    if (!selectedFileId || loadingNetwork) return;
    setLoadingNetwork(true); setMessage(''); setNetwork(null);
    try {
      const data = await discoverFromUploadedPaper(selectedFileId);
      setNetwork(data);
      setTab('references');
      if (!data.reference_count) setMessage('没有从该 PDF 中识别到独立参考文献条目，但仍可查看相关研究。');
    } catch (error) {
      setMessage(error.message);
    }
    setLoadingNetwork(false);
  };

  const runKeywordSearch = async (event) => {
    event?.preventDefault();
    if (query.trim().length < 2 || searching) return;
    setSearching(true); setMessage('');
    try {
      const data = await searchAcademicPapers(query.trim());
      setKeywordResults(data.papers || []);
      setKeywordProviders(data.providers || []);
      if (!(data.papers || []).length) setMessage('没有找到匹配论文，请尝试更具体的英文关键词。');
    } catch (error) {
      setMessage(error.message); setKeywordResults([]);
    }
    setSearching(false);
  };

  const importPaper = async (paper) => {
    const arxivId = paper.arxiv_id || (paper.source === 'arxiv' ? paper.source_id : '');
    if (!arxivId || importing) return;
    setImporting(arxivId);
    setMessage('正在下载、解析并建立双路索引，这可能需要几分钟…');
    try {
      const result = await importArxivPaper(arxivId, paper.title || `arXiv ${arxivId}`);
      setImported((previous) => ({ ...previous, [arxivId]: result }));
      setMessage(result.status === 'duplicate' ? '该论文已经在知识库中。' : '论文已完成解析与索引。');
      onImported?.(result);
      const items = await fetchFiles();
      setFiles(items || []);
    } catch (error) {
      setMessage(error.message);
    }
    setImporting('');
  };

  const renderPaper = (paper) => {
    const arxivId = paper.arxiv_id || (paper.source === 'arxiv' ? paper.source_id : '');
    const record = imported[arxivId];
    return (
      <article key={`${paper.source}-${paper.source_id}-${paper.title}`} className="rounded-xl border border-gray-200 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs font-semibold leading-relaxed text-gray-800">{paper.title}</p>
            <p className="mt-1 text-[10px] text-gray-400">{[paper.year, (paper.authors || []).slice(0, 2).join(', '), paper.citation_count != null && `${paper.citation_count} citations`].filter(Boolean).join(' · ')}</p>
          </div>
          {paper.url && <a href={paper.url} target="_blank" rel="noreferrer" title="Open source page" className="shrink-0 text-gray-400 hover:text-gray-700"><ExternalLink size={13} /></a>}
        </div>
        {paper.relation_reason && <p className="mt-2 rounded-md bg-violet-50 px-2 py-1.5 text-[10px] text-violet-700">{paper.relation_reason} · 匹配度 {Math.round((paper.related_score || 0) * 100)}%</p>}
        {paper.abstract && <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-gray-500">{paper.abstract}</p>}
        <div className="mt-2 flex gap-1.5">
          <button type="button" disabled={!arxivId || disabled || Boolean(importing)} onClick={() => importPaper(paper)} className="flex flex-1 items-center justify-center gap-1 rounded-md bg-cyan-700 px-2 py-1.5 text-[11px] font-medium text-white hover:bg-cyan-800 disabled:opacity-40">
            {importing === arxivId ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            {record ? '已导入' : arxivId ? '导入全文' : '暂无 arXiv 全文'}
          </button>
          {record?.paper_id && <button type="button" disabled={disabled} onClick={() => onAnalyze(record, 'overview')} className="flex items-center gap-1 rounded-md border border-cyan-200 px-2 py-1.5 text-[11px] text-cyan-800"><BookOpenCheck size={12} />精读</button>}
        </div>
      </article>
    );
  };

  return (
    <div className="space-y-4 p-4">
      <section className="rounded-xl border border-cyan-100 bg-cyan-50 p-3">
        <p className="text-xs font-semibold text-cyan-900">从已上传论文发现研究脉络</p>
        <p className="mt-1 text-[11px] leading-relaxed text-cyan-700">先从原始 PDF 本地解析参考文献，再根据论文标题、摘要和主题词联合检索 arXiv、Semantic Scholar 与 Crossref。</p>
      </section>

      {files.length === 0 ? (
        <p className="rounded-lg bg-gray-50 p-3 text-xs text-gray-500">请先上传至少一篇论文。</p>
      ) : (
        <section className="space-y-2">
          <label className="block text-[11px] font-medium text-gray-600">作为发现起点的论文</label>
          <select value={selectedFileId} onChange={(event) => { setSelectedFileId(event.target.value); setNetwork(null); }} className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs outline-none focus:border-cyan-400">
            {files.map((file) => <option key={file.file_id} value={file.file_id}>{file.filename}</option>)}
          </select>
          <button onClick={analyzeUploadedPaper} disabled={!selectedFileId || loadingNetwork} className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-700 py-2 text-xs font-medium text-white disabled:opacity-40">
            {loadingNetwork ? <Loader2 size={13} className="animate-spin" /> : <FileSearch size={13} />}解析参考文献并发现相关研究
          </button>
        </section>
      )}

      {message && <p className="rounded-lg bg-gray-50 px-3 py-2 text-[11px] leading-relaxed text-gray-600">{message}</p>}

      {network && (
        <>
          <section className="rounded-xl border border-gray-200 p-3">
            <p className="text-xs font-semibold leading-relaxed text-gray-800">{network.source_paper.title}</p>
            <p className="mt-1 text-[10px] text-gray-400">本地识别 {network.reference_count} 条参考文献 · 相关检索词：{network.source_paper.keywords.join(', ')}</p>
            <div className="mt-2"><ProviderBadges providers={network.providers || []} /></div>
          </section>
          <div className="grid grid-cols-2 rounded-lg bg-gray-100 p-1">
            <button onClick={() => setTab('references')} className={`rounded-md py-1.5 text-xs ${tab === 'references' ? 'bg-white font-medium shadow-sm' : 'text-gray-500'}`}>参考文献 {network.reference_count}</button>
            <button onClick={() => setTab('related')} className={`rounded-md py-1.5 text-xs ${tab === 'related' ? 'bg-white font-medium shadow-sm' : 'text-gray-500'}`}>相关研究 {network.related_papers.length}</button>
          </div>
          {tab === 'references' && <div className="space-y-2">{network.references.map((reference) => (
            <article key={reference.index} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
              <p className="text-[11px] leading-relaxed text-gray-600"><span className="mr-1 font-semibold text-gray-800">[{reference.index}]</span>{reference.citation}</p>
              <div className="mt-2 flex items-center gap-2">
                {reference.url && <a href={reference.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[10px] text-cyan-700"><ExternalLink size={10} />查看来源</a>}
                {reference.arxiv_id && <button disabled={disabled || Boolean(importing)} onClick={() => importPaper({ title: reference.citation.slice(0, 120), arxiv_id: reference.arxiv_id, source: 'arxiv', source_id: reference.arxiv_id })} className="flex items-center gap-1 text-[10px] text-violet-700"><Download size={10} />导入全文</button>}
              </div>
            </article>
          ))}</div>}
          {tab === 'related' && <div className="space-y-2">{network.related_papers.length ? network.related_papers.map(renderPaper) : <p className="rounded-lg bg-amber-50 p-3 text-[11px] text-amber-700">当前学术服务未返回相关结果；本地参考文献仍可正常查看。</p>}</div>}
        </>
      )}

      <details className="border-t border-gray-100 pt-4">
        <summary className="cursor-pointer text-xs font-medium text-gray-600">补充关键词检索</summary>
        <form onSubmit={runKeywordSearch} className="mt-3 flex gap-2">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如 explainable agentic RAG" className="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-2 text-xs outline-none focus:border-cyan-400" />
          <button type="submit" disabled={searching || query.trim().length < 2} className="rounded-lg bg-cyan-700 px-3 text-white disabled:opacity-40">{searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}</button>
        </form>
        <div className="mt-2"><ProviderBadges providers={keywordProviders} /></div>
        <div className="mt-3 space-y-2">{keywordResults.map(renderPaper)}</div>
      </details>
    </div>
  );
}
