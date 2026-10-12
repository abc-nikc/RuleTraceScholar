import { useState, useEffect, useRef, useCallback } from 'react';
import { Upload, Settings, ChevronLeft, CircleHelp, Search, Database, Menu } from 'lucide-react';
import Sidebar from './components/Sidebar';
import ChatMessages from './components/ChatMessages';
import ChatInput from './components/ChatInput';
import FileUpload from './components/FileUpload';
import SettingsPanel from './components/SettingsPanel';
import GuidePanel from './components/GuidePanel';
import DiscoveryPanel from './components/DiscoveryPanel';
import KnowledgePanel from './components/KnowledgePanel';
import { fetchSessions, fetchHistory, deleteSession, fetchRuntimeSettings, streamChat } from './api';

const ACTIVE_SESSION_KEY = 'ruletrace-scholar.active-session';
const THINKING_MODE_KEY = 'ruletrace-scholar.deep-thinking';

function normalizeHistory(messages = []) {
  return messages.map((message) => ({
    ...message,
    citations: message.citations || [],
    explanation: message.explanation || null,
    claim_tests: message.claim_tests || null,
    repair: message.repair || null,
    capsule: message.capsule || null,
    finalized: true,
  }));
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [paperScope, setPaperScope] = useState([]);
  const [loading, setLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState('');
  const [deepThinking, setDeepThinking] = useState(
    () => window.localStorage.getItem(THINKING_MODE_KEY) === 'true'
  );
  const [modelProfile, setModelProfile] = useState(null);
  const [panel, setPanel] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const cancelRef = useRef(null);
  const bottomRef = useRef(null);
  const restoredRef = useRef(false);

  const selectSession = useCallback(async (id) => {
    setCurrentId(id);
    window.localStorage.setItem(ACTIVE_SESSION_KEY, id);
    setPaperScope([]);
    setPanel(null);
    try {
      const data = await fetchHistory(id);
      setMessages(normalizeHistory(data.messages));
    } catch (error) {
      setMessages([{ role: 'assistant', content: `无法恢复该会话：${error.message}`, citations: [], finalized: true }]);
    }
  }, []);

  const loadSessions = useCallback(async ({ restore = false } = {}) => {
    try {
      const items = await fetchSessions();
      setSessions(items);
      if (restore && !restoredRef.current) {
        restoredRef.current = true;
        const savedId = window.localStorage.getItem(ACTIVE_SESSION_KEY);
        const target = items.find((item) => item.session_id === savedId) || items[0];
        if (target) await selectSession(target.session_id);
      }
    } catch (error) {
      if (restore) {
        setMessages([{ role: 'assistant', content: `无法加载历史会话：${error.message}`, citations: [], finalized: true }]);
      }
    }
  }, [selectSession]);

  useEffect(() => { loadSessions({ restore: true }); }, [loadSessions]);

  useEffect(() => {
    fetchRuntimeSettings()
      .then((data) => setModelProfile(data.model_status || null))
      .catch(() => setModelProfile(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const newChat = () => {
    if (cancelRef.current) cancelRef.current();
    setCurrentId(null);
    window.localStorage.removeItem(ACTIVE_SESSION_KEY);
    setMessages([]);
    setPaperScope([]);
    setPanel(null);
  };

  const handleDelete = async (id) => {
    await deleteSession(id);
    if (currentId === id) newChat();
    loadSessions();
  };

  const handleSend = (query, options = {}) => {
    if (cancelRef.current) cancelRef.current();

    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setLoading(true);
    setAgentStatus('analyzing');

    let sessionId = options.newSession ? null : currentId;
    let answer = '';
    let citations = [];
    let subQueries = [];

    const requestPaperIds = Object.prototype.hasOwnProperty.call(options, 'paperIds')
      ? options.paperIds
      : paperScope;

    const cancel = streamChat(query, sessionId, (evt) => {
      switch (evt.type) {
        case 'session_id':
          sessionId = evt.data;
          setCurrentId(evt.data);
          window.localStorage.setItem(ACTIVE_SESSION_KEY, evt.data);
          break;
        case 'answer':
          answer = evt.data;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === 'assistant' && !last.finalized) {
              return prev.slice(0, -1).concat({ ...last, content: answer });
            }
            return [...prev, { role: 'assistant', content: answer, citations: [], sub_queries: subQueries, finalized: false }];
          });
          break;
        case 'sub_queries':
          subQueries = evt.data || [];
          break;
        case 'status':
          setAgentStatus(evt.data || '');
          break;
        case 'citations':
          citations = evt.data;
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, citations, finalized: true }
                : m
            )
          );
          break;
        case 'explanation':
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, explanation: evt.data }
                : m
            )
          );
          break;
        case 'claim_tests':
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, claim_tests: evt.data }
                : m
            )
          );
          break;
        case 'capsule':
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, capsule: evt.data }
                : m
            )
          );
          break;
        case 'repair':
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, repair: evt.data }
                : m
            )
          );
          break;
        case 'done':
          setLoading(false);
          setAgentStatus('');
          loadSessions();
          break;
        case 'error':
          setMessages((prev) => {
            const errorMessage = { role: 'assistant', content: `请求失败：${evt.data}`, citations: [], finalized: true };
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && !last.finalized) {
              return prev.slice(0, -1).concat({ ...last, content: `${last.content}\n\n> ${errorMessage.content}`, finalized: true });
            }
            return [...prev, errorMessage];
          });
          setLoading(false);
          setAgentStatus('');
          break;
      }
    }, requestPaperIds, deepThinking);

    cancelRef.current = cancel;
  };

  const analysisPrompts = {
    overview: (paper) => `请只基于论文《${paper}》生成一份详细、适合初次阅读者的中文精读报告。请系统覆盖：1. 论文要解决的问题与研究背景；2. 核心思想和主要贡献；3. 方法或模型的完整流程、输入输出及关键模块；4. 数据集、实验设置、对比基线和评价指标；5. 关键实验结果及其含义；6. 消融实验或敏感性分析；7. 局限性、适用边界与可能风险；8. 可以复现或进一步研究的方向；9. 给出5个由浅入深的后续追问。每个事实性结论都必须紧跟可追溯引用；资料不足的部分请明确标注，不要猜测。`,
    method: (paper) => `请只基于论文《${paper}》详细解析其方法。请说明研究问题、总体架构、输入输出、每个核心模块、训练或推理流程、损失函数与关键公式的含义，并用编号步骤给出完整工作流。最后指出与常见方法相比真正发生变化的部分。所有事实性描述必须附引用，证据不足时明确说明。`,
    experiment: (paper) => `请只基于论文《${paper}》审计其实验部分。请整理数据集、划分方式、基线、评价指标、实现设置、主要结果、消融实验和效率结果；将关键数值及对应结论逐项列出，并检查这些数值能否在引用证据中找到。区分作者报告的事实与根据结果作出的推断，不要补造缺失信息。`,
    innovation: (paper) => `请只基于论文《${paper}》分析其创新性与研究启发。请区分作者明确声称的贡献、从方法和实验中可以得到的合理推断、以及尚未被证据支持的设想；分析技术新意、实用价值、局限、可复现点和可进一步改进的方向。所有论文事实必须附引用。`,
  };

  const handleAnalyzePaper = (paper, action = 'overview') => {
    if (!paper?.paper_id || loading) return;
    const makePrompt = analysisPrompts[action] || analysisPrompts.overview;
    setPanel(null);
    setCurrentId(null);
    setMessages([]);
    setPaperScope([paper.paper_id]);
    handleSend(makePrompt(paper.paper_id), {
      newSession: true,
      paperIds: [paper.paper_id],
    });
  };

  const togglePanel = (name) => setPanel((prev) => (prev === name ? null : name));

  return (
    <div className="relative flex h-screen overflow-hidden bg-white">
      {sidebarOpen && <button aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-20 bg-black/20 lg:hidden" />}
      <Sidebar
        sessions={sessions}
        currentId={currentId}
        onSelect={(id) => { selectSession(id); setSidebarOpen(false); }}
        onNew={() => { newChat(); setSidebarOpen(false); }}
        onDelete={handleDelete}
        mobileOpen={sidebarOpen}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-white">
          <div>
            <div className="flex items-center gap-2">
              <button onClick={() => setSidebarOpen(true)} aria-label="Open sidebar" className="rounded-lg p-1.5 hover:bg-gray-50 lg:hidden"><Menu size={17} className="text-gray-500" /></button>
              <div>
                <h1 className="text-sm font-semibold text-gray-800">RuleTrace Scholar</h1>
                <p className="hidden text-[10px] text-gray-400 sm:block">Explainable agentic RAG</p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => togglePanel('upload')}
              aria-label="Upload papers"
              title="Upload papers"
              className={`p-2 rounded-lg transition-colors ${panel === 'upload' ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
            >
              <Upload size={16} className="text-gray-500" />
            </button>
            <button
              onClick={() => togglePanel('discovery')}
              aria-label="Discover academic papers"
              title="Discover papers"
              className={`p-2 rounded-lg transition-colors ${panel === 'discovery' ? 'bg-cyan-50' : 'hover:bg-gray-50'}`}
            >
              <Search size={16} className={panel === 'discovery' ? 'text-cyan-700' : 'text-gray-500'} />
            </button>
            <button
              onClick={() => togglePanel('knowledge')}
              aria-label="Inspect RAG and uploaded papers"
              title="RAG and uploaded papers"
              className={`p-2 rounded-lg transition-colors ${panel === 'knowledge' ? 'bg-violet-50' : 'hover:bg-gray-50'}`}
            >
              <Database size={16} className={panel === 'knowledge' ? 'text-violet-700' : 'text-gray-500'} />
            </button>
            <button
              onClick={() => togglePanel('guide')}
              aria-label="Open research guide"
              title="Research guide"
              className={`p-2 rounded-lg transition-colors ${panel === 'guide' ? 'bg-indigo-50' : 'hover:bg-gray-50'}`}
            >
              <CircleHelp size={16} className={panel === 'guide' ? 'text-indigo-600' : 'text-gray-500'} />
            </button>
            <button
              onClick={() => togglePanel('settings')}
              aria-label="Open settings"
              title="Open settings"
              className={`p-2 rounded-lg transition-colors ${panel === 'settings' ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
            >
              <Settings size={16} className="text-gray-500" />
            </button>
          </div>
        </header>

        <div className="relative flex flex-1 min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <ChatMessages
              messages={messages}
              loading={loading}
              status={agentStatus}
              onOpenUpload={() => setPanel('upload')}
              onOpenGuide={() => setPanel('guide')}
              onOpenDiscovery={() => setPanel('discovery')}
            />
            <div ref={bottomRef} />
            <ChatInput
              onSend={handleSend}
              disabled={loading}
              scopeLabel={paperScope[0] || ''}
              deepThinking={deepThinking}
              modelProfile={modelProfile}
              onDeepThinkingChange={(enabled) => {
                setDeepThinking(enabled);
                window.localStorage.setItem(THINKING_MODE_KEY, String(enabled));
              }}
            />
          </div>

          {panel && (
            <div className={`absolute inset-y-0 right-0 z-20 w-full border-l border-gray-200 bg-white shadow-xl lg:static lg:shadow-none ${panel === 'knowledge' ? 'max-w-[48rem]' : panel === 'discovery' ? 'max-w-[34rem]' : panel === 'settings' ? 'max-w-[28rem]' : 'max-w-72'}`}>
              <div className="h-full overflow-y-auto">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  {panel === 'upload' ? 'Upload Files' : panel === 'discovery' ? 'Discover Papers' : panel === 'knowledge' ? 'Knowledge & Papers Inspector' : panel === 'guide' ? 'Research Guide' : 'Settings'}
                </span>
                <button onClick={() => setPanel(null)} className="p-1 rounded hover:bg-gray-100">
                  <ChevronLeft size={14} className="text-gray-400" />
                </button>
              </div>
              {panel === 'upload' && (
                <FileUpload
                  onUploaded={loadSessions}
                  onAnalyze={handleAnalyzePaper}
                  disabled={loading}
                />
              )}
              {panel === 'guide' && <GuidePanel onAnalyze={handleAnalyzePaper} disabled={loading} />}
              {panel === 'discovery' && (
                <DiscoveryPanel
                  onImported={loadSessions}
                  onAnalyze={handleAnalyzePaper}
                  disabled={loading}
                />
              )}
              {panel === 'knowledge' && <KnowledgePanel />}
              {panel === 'settings' && <SettingsPanel currentSessionId={currentId} onCollectionCleared={loadSessions} onMemoryReset={() => setMessages([])} onSettingsSaved={(data) => setModelProfile(data.model_status || null)} />}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
