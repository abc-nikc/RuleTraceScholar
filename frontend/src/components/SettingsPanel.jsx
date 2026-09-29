import { useEffect, useState } from 'react';
import { Database, FileText, Loader2, RotateCcw, Save, Trash2 } from 'lucide-react';
import {
  clearCollection,
  deleteFile,
  fetchFiles,
  fetchRuntimeSettings,
  reindexPaper,
  resetRuntimeSettings,
  resetSessionMemory,
  updateRuntimeSettings,
} from '../api';

function NumberField({ label, value, min, max, step = 1, onChange, hint }) {
  return (
    <label className="block">
      <span className="flex items-center justify-between text-[11px] text-gray-600"><span>{label}</span><span className="text-gray-400">{hint}</span></span>
      <input type="number" value={value} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} className="mt-1 w-full rounded-md border border-gray-200 px-2.5 py-1.5 text-xs outline-none focus:border-violet-300" />
    </label>
  );
}

function Toggle({ label, checked, onChange, description }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-3 rounded-lg border border-gray-100 p-2.5">
      <span><span className="block text-xs font-medium text-gray-700">{label}</span><span className="mt-0.5 block text-[10px] leading-relaxed text-gray-400">{description}</span></span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-0.5 accent-violet-600" />
    </label>
  );
}

export default function SettingsPanel({ currentSessionId, onCollectionCleared, onMemoryReset }) {
  const [files, setFiles] = useState([]);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [fileData, settingData] = await Promise.all([fetchFiles(), fetchRuntimeSettings()]);
      setFiles(fileData);
      setSettings(settingData.settings);
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => { load(); }, []);

  const setGroup = (group, key, value) => setSettings((current) => ({
    ...current,
    [group]: { ...current[group], [key]: value },
  }));

  const run = async (name, action, success) => {
    setBusy(name); setError(''); setNotice('');
    try { await action(); if (success) setNotice(success); } catch (err) { setError(err.message); }
    setBusy('');
  };

  const save = () => run('save', async () => {
    const data = await updateRuntimeSettings(settings);
    setSettings(data.settings);
  }, '设置已保存。RAG 与记忆参数从下一次问答开始生效。');

  const restore = () => run('restore', async () => {
    const data = await resetRuntimeSettings();
    setSettings(data.settings);
  }, '已恢复项目默认设置。');

  const handleReindex = async (file) => {
    if (!confirm(`将使用当前切分规则重建《${file.filename}》的向量索引。继续吗？`)) return;
    await run(`reindex-${file.file_id}`, async () => {
      const result = await reindexPaper(file.file_id);
      setFiles(await fetchFiles());
      setNotice(`重新索引完成：${result.children} 个子块，${result.parents} 个父块。`);
    }, '');
  };

  const handleDeleteFile = async (fileId) => {
    if (!confirm('删除后论文原文件和向量索引都将移除。继续吗？')) return;
    await run(`delete-${fileId}`, async () => { await deleteFile(fileId); setFiles(await fetchFiles()); }, '论文已删除。');
  };

  const handleMemoryReset = async () => {
    if (!currentSessionId || !confirm('这会清空当前会话的消息窗口、摘要和工作状态，但保留会话条目。继续吗？')) return;
    await run('memory', async () => {
      await resetSessionMemory(currentSessionId);
      onMemoryReset?.();
    }, '当前会话记忆已清空。');
  };

  const handleClear = async () => {
    if (!confirm('这会删除全部论文、原始 PDF 和向量索引。继续吗？')) return;
    await run('clear', async () => {
      await clearCollection(); setFiles([]); onCollectionCleared?.();
    }, '知识库已清空。');
  };

  if (!settings) return <div className="flex items-center gap-2 p-4 text-xs text-gray-400"><Loader2 size={14} className="animate-spin" />正在加载可编辑设置…</div>;

  return (
    <div className="space-y-5 p-4">
      <div className="rounded-lg bg-violet-50 p-3 text-[11px] leading-relaxed text-violet-700">这里修改的是运行时策略。RAG 和记忆立即影响后续问答；切分规则只影响新论文，已有论文需要手动重新索引。</div>
      {notice && <p className="rounded-md bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700">{notice}</p>}
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-[11px] text-red-700">{error}</p>}

      <section className="space-y-3">
        <div><h3 className="text-xs font-semibold text-gray-800">RAG 检索</h3><p className="text-[10px] text-gray-400">控制候选数量、融合和重排，不需要重启。</p></div>
        <div className="grid grid-cols-3 gap-2">
          <NumberField label="Top-K" value={settings.retrieval.top_k} min={1} max={20} onChange={(v) => setGroup('retrieval', 'top_k', v)} />
          <NumberField label="Fetch-K" value={settings.retrieval.fetch_k} min={1} max={100} onChange={(v) => setGroup('retrieval', 'fetch_k', v)} />
          <NumberField label="RRF-K" value={settings.retrieval.rrf_k} min={1} max={200} onChange={(v) => setGroup('retrieval', 'rrf_k', v)} />
        </div>
        <NumberField label="多样性权重" value={settings.retrieval.diversity_weight} min={0} max={1} step={0.05} hint="0–1" onChange={(v) => setGroup('retrieval', 'diversity_weight', v)} />
        <div className="grid gap-2 sm:grid-cols-3">
          <Toggle label="交叉编码重排" checked={settings.retrieval.rerank} onChange={(v) => setGroup('retrieval', 'rerank', v)} description="精排候选证据" />
          <Toggle label="父块扩展" checked={settings.retrieval.expand_parent} onChange={(v) => setGroup('retrieval', 'expand_parent', v)} description="补充完整上下文" />
          <Toggle label="证据多样性" checked={settings.retrieval.diversify} onChange={(v) => setGroup('retrieval', 'diversify', v)} description="减少重复片段" />
        </div>
      </section>

      <section className="space-y-3 border-t border-gray-100 pt-4">
        <div><h3 className="text-xs font-semibold text-gray-800">论文切分</h3><p className="text-[10px] text-gray-400">修改后点击下方论文的“重新索引”才会影响已有数据。</p></div>
        <div className="grid grid-cols-2 gap-2">
          <NumberField label="块大小" value={settings.chunking.chunk_size} min={200} max={2000} hint="字符" onChange={(v) => setGroup('chunking', 'chunk_size', v)} />
          <NumberField label="重叠长度" value={settings.chunking.chunk_overlap} min={0} max={500} hint="字符" onChange={(v) => setGroup('chunking', 'chunk_overlap', v)} />
        </div>
        <Toggle label="保留结构化节点" checked={settings.chunking.preserve_structured_nodes} onChange={(v) => setGroup('chunking', 'preserve_structured_nodes', v)} description="表格、图、标题和图注保持完整，不进行普通文本切分。" />
      </section>

      <section className="space-y-3 border-t border-gray-100 pt-4">
        <div><h3 className="text-xs font-semibold text-gray-800">会话记忆</h3><p className="text-[10px] text-gray-400">窗口外消息可压缩为摘要并持久化到 PostgreSQL。</p></div>
        <NumberField label="活动消息窗口" value={settings.memory.window_size} min={2} max={30} hint="条消息" onChange={(v) => setGroup('memory', 'window_size', v)} />
        <Toggle label="自动压缩旧消息" checked={settings.memory.summarization_enabled} onChange={(v) => setGroup('memory', 'summarization_enabled', v)} description="超过窗口时由模型生成可检查摘要。" />
        <button disabled={!currentSessionId || busy === 'memory'} onClick={handleMemoryReset} className="flex items-center gap-1.5 text-[11px] text-amber-700 disabled:text-gray-300"><RotateCcw size={12} />重置当前会话记忆</button>
      </section>

      <div className="flex gap-2 border-t border-gray-100 pt-4">
        <button disabled={!!busy} onClick={save} className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-violet-600 py-2 text-xs font-medium text-white disabled:opacity-50">{busy === 'save' ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}保存设置</button>
        <button disabled={!!busy} onClick={restore} className="flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-2 text-xs text-gray-600 disabled:opacity-50"><RotateCcw size={13} />恢复默认</button>
      </div>

      <section className="space-y-2 border-t border-gray-100 pt-4">
        <h3 className="text-xs font-semibold text-gray-800">已索引论文</h3>
        {files.length === 0 ? <p className="text-xs text-gray-400">暂无论文</p> : files.map((file) => (
          <div key={file.file_id} className="rounded-lg border border-gray-100 p-2.5">
            <div className="flex items-center gap-2 text-xs text-gray-600"><FileText size={13} className="shrink-0 text-gray-400" /><span className="min-w-0 flex-1 truncate">{file.filename}</span><span className="text-gray-400">{file.chunk_count}c</span></div>
            <div className="mt-2 flex gap-3 pl-5">
              <button disabled={!!busy} onClick={() => handleReindex(file)} className="flex items-center gap-1 text-[10px] text-violet-700 disabled:text-gray-300">{busy === `reindex-${file.file_id}` ? <Loader2 size={11} className="animate-spin" /> : <RotateCcw size={11} />}按当前规则重新索引</button>
              <button disabled={!!busy} onClick={() => handleDeleteFile(file.file_id)} className="flex items-center gap-1 text-[10px] text-red-500 disabled:text-gray-300"><Trash2 size={11} />删除</button>
            </div>
          </div>
        ))}
        <button disabled={!!busy} onClick={handleClear} className="flex items-center gap-1.5 pt-2 text-[11px] text-red-600 disabled:text-gray-300"><Database size={12} />清空全部知识库</button>
      </section>
    </div>
  );
}
