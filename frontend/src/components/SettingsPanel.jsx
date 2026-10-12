import { useEffect, useState } from 'react';
import { Cloud, Cpu, Database, FileText, Loader2, RefreshCw, RotateCcw, Save, Trash2 } from 'lucide-react';
import {
  clearCollection,
  deleteFile,
  fetchFiles,
  fetchLocalModels,
  fetchRuntimeSettings,
  reindexPaper,
  resetRuntimeSettings,
  resetSessionMemory,
  testModelConnection,
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

function TextField({ label, value, onChange, placeholder, type = 'text', hint }) {
  return (
    <label className="block">
      <span className="flex items-center justify-between text-[11px] text-gray-600"><span>{label}</span>{hint && <span className="text-gray-400">{hint}</span>}</span>
      <input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} autoComplete={type === 'password' ? 'new-password' : undefined} className="mt-1 w-full rounded-md border border-gray-200 px-2.5 py-1.5 text-xs outline-none focus:border-violet-300" />
    </label>
  );
}

const PROCESSOR_LABELS = {
  cpu: 'CPU 运行',
  gpu: 'GPU 运行',
  mixed: 'CPU/GPU 混合',
  not_loaded: '未加载',
};

export default function SettingsPanel({ currentSessionId, onCollectionCleared, onLibraryUpdated, onMemoryReset, onSettingsSaved }) {
  const [files, setFiles] = useState([]);
  const [settings, setSettings] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [localModels, setLocalModels] = useState([]);
  const [localModelError, setLocalModelError] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [fileData, settingData] = await Promise.all([fetchFiles(), fetchRuntimeSettings()]);
      setFiles(fileData);
      setSettings(settingData.settings);
      setModelStatus(settingData.model_status);
      try {
        const models = await fetchLocalModels();
        setLocalModels(models.models || []);
        setLocalModelError('');
      } catch (modelErr) {
        setLocalModelError(modelErr.message);
      }
    } catch (err) {
      setError(err.message);
    }
  };
  useEffect(() => { load(); }, []);

  const setGroup = (group, key, value) => setSettings((current) => ({
    ...current,
    [group]: { ...current[group], [key]: value },
  }));

  const refreshModels = () => run('models', async () => {
    const data = await fetchLocalModels();
    setLocalModels(data.models || []);
    setLocalModelError('');
  }, '已刷新本机 Ollama 模型列表。');

  const run = async (name, action, success) => {
    setBusy(name); setError(''); setNotice('');
    try { await action(); if (success) setNotice(success); } catch (err) { setError(err.message); }
    setBusy('');
  };

  const save = () => run('save', async () => {
    const data = await updateRuntimeSettings(settings, apiKey, clearApiKey);
    setSettings(data.settings);
    setModelStatus(data.model_status);
    setApiKey('');
    setClearApiKey(false);
    onSettingsSaved?.(data);
  }, '设置已保存。模型、RAG 与记忆参数从下一次问答开始生效。');

  const restore = () => run('restore', async () => {
    const data = await resetRuntimeSettings();
    setSettings(data.settings);
    setModelStatus(data.model_status);
    setApiKey('');
    setClearApiKey(false);
    onSettingsSaved?.(data);
  }, '已恢复项目默认设置。');

  const testConnection = () => run('test-model', async () => {
    const result = await testModelConnection(settings.llm, apiKey);
    setNotice(`连接成功：${result.provider} / ${result.model}，测试耗时 ${result.latency_seconds} 秒。`);
  }, '');

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
    await run(`delete-${fileId}`, async () => {
      await deleteFile(fileId);
      setFiles(await fetchFiles());
      onLibraryUpdated?.();
    }, '论文已删除。');
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
        <div className="flex items-start justify-between gap-3">
          <div><h3 className="text-xs font-semibold text-gray-800">模型与提供方</h3><p className="text-[10px] text-gray-400">当前选择会用于下一次问答，无需重启容器。</p></div>
          <span className="max-w-[12rem] truncate rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-600" title={modelStatus?.model}>{modelStatus?.model || settings.llm.model}</span>
        </div>

        <label className="block">
          <span className="text-[11px] text-gray-600">模型来源</span>
          <select value={settings.llm.provider} onChange={(event) => {
            const provider = event.target.value;
            setSettings((current) => ({
              ...current,
              llm: {
                ...current.llm,
                provider,
                base_url: provider === 'ollama' && !current.llm.base_url.includes('11434')
                  ? 'http://host.docker.internal:11434/v1'
                  : current.llm.base_url,
              },
            }));
          }} className="mt-1 w-full rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-violet-300">
            <option value="ollama">本地 Ollama</option>
            <option value="openai_compatible">OpenAI 兼容 API</option>
          </select>
        </label>

        <TextField label="API Base URL" value={settings.llm.base_url} onChange={(value) => setGroup('llm', 'base_url', value)} placeholder="http://host.docker.internal:11434/v1" />

        {settings.llm.provider === 'ollama' && localModels.length > 0 && (
          <label className="block">
            <span className="flex items-center justify-between text-[11px] text-gray-600"><span>本机已安装模型</span><span className="text-gray-400">{localModels.length} 个</span></span>
            <select value={localModels.some((item) => item.name === settings.llm.model) ? settings.llm.model : ''} onChange={(event) => event.target.value && setGroup('llm', 'model', event.target.value)} className="mt-1 w-full rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-violet-300">
              <option value="">选择 Ollama 模型…</option>
              {localModels.map((item) => <option key={item.name} value={item.name}>{item.name}{item.parameter_size ? ` · ${item.parameter_size}` : ''}</option>)}
            </select>
          </label>
        )}

        <TextField label="模型名称" value={settings.llm.model} onChange={(value) => setGroup('llm', 'model', value)} placeholder={settings.llm.provider === 'ollama' ? 'qwen3:8b' : '模型部署名称'} hint="可手动填写" />

        {settings.llm.provider === 'openai_compatible' && (
          <div className="space-y-2 rounded-lg border border-sky-100 bg-sky-50/50 p-2.5">
            <TextField label="API Key" value={apiKey} onChange={(value) => { setApiKey(value); setClearApiKey(false); }} type="password" placeholder={modelStatus?.api_key_configured ? '已安全保存；留空表示不修改' : '填写服务商 API Key'} />
            <p className="text-[10px] leading-relaxed text-sky-700">密钥只提交到本机后端并保存在受 Git 忽略的数据目录；网页不会读取或回显完整密钥。</p>
            {modelStatus?.api_key_configured && <label className="flex items-center gap-2 text-[10px] text-red-600"><input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} />保存时清除已有 API Key</label>}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <NumberField label="快速模式输出" value={settings.llm.fast_max_tokens} min={64} max={32768} hint="tokens" onChange={(value) => setGroup('llm', 'fast_max_tokens', value)} />
          <NumberField label="深度模式输出" value={settings.llm.deep_max_tokens} min={64} max={65536} hint="tokens" onChange={(value) => setGroup('llm', 'deep_max_tokens', value)} />
        </div>
        <NumberField label="Temperature" value={settings.llm.temperature} min={0} max={2} step={0.1} hint="0–2" onChange={(value) => setGroup('llm', 'temperature', value)} />
        <Toggle label="端点支持深度推理参数" checked={settings.llm.reasoning_supported} onChange={(value) => setGroup('llm', 'reasoning_supported', value)} description="Ollama Qwen3 可启用；若外部 API 不支持 reasoning_effort，请关闭。" />

        {settings.llm.provider === 'ollama' && (
          <div className="space-y-1.5 rounded-lg border border-gray-100 p-2.5">
            {localModels.map((item) => item.name === settings.llm.model && (
              <div key={item.name} className="flex flex-wrap items-center gap-2 text-[10px] text-gray-500">
                <Cpu size={12} /><span>{PROCESSOR_LABELS[item.processor] || item.processor}</span>
                {item.quantization && <span>· {item.quantization}</span>}
                {item.context_length && <span>· 上下文 {item.context_length}</span>}
              </div>
            ))}
            {localModelError && <p className="text-[10px] leading-relaxed text-amber-700">{localModelError}</p>}
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button disabled={!!busy} onClick={refreshModels} className="flex items-center justify-center gap-1.5 rounded-md border border-gray-200 py-2 text-[11px] text-gray-600 disabled:opacity-50">{busy === 'models' ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}刷新本地模型</button>
          <button disabled={!!busy} onClick={testConnection} className="flex items-center justify-center gap-1.5 rounded-md border border-violet-200 bg-violet-50 py-2 text-[11px] text-violet-700 disabled:opacity-50">{busy === 'test-model' ? <Loader2 size={12} className="animate-spin" /> : settings.llm.provider === 'ollama' ? <Cpu size={12} /> : <Cloud size={12} />}测试当前连接</button>
        </div>
      </section>

      <section className="space-y-3 border-t border-gray-100 pt-4">
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
        <button disabled={!!busy} onClick={save} className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-violet-600 py-2 text-xs font-medium text-white disabled:opacity-50">{busy === 'save' ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}保存全部设置</button>
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
