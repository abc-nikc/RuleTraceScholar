import { useEffect, useState } from 'react';
import {
  BookOpenCheck,
  FlaskConical,
  HelpCircle,
  Lightbulb,
  Route,
  ShieldCheck,
} from 'lucide-react';
import { fetchFiles } from '../api';

const actions = [
  {
    id: 'overview',
    title: '一键综合精读',
    description: '贡献、方法、实验、局限与阅读建议',
    icon: BookOpenCheck,
  },
  {
    id: 'method',
    title: '方法与流程解析',
    description: '拆解模型结构、输入输出与关键步骤',
    icon: Route,
  },
  {
    id: 'experiment',
    title: '实验结果核查',
    description: '整理数据集、指标、基线和关键数值',
    icon: FlaskConical,
  },
  {
    id: 'innovation',
    title: '创新与研究启发',
    description: '提炼创新点、可复现方向与改进空间',
    icon: Lightbulb,
  },
];

export default function GuidePanel({ onAnalyze, disabled }) {
  const [files, setFiles] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    fetchFiles()
      .then((data) => {
        const items = Array.isArray(data) ? data : data.files || [];
        setFiles(items);
        if (items.length) setSelectedId(items[0].file_id);
      })
      .catch(() => setLoadError('暂时无法读取论文列表，请稍后重试。'));
  }, []);

  const selected = files.find((file) => file.file_id === selectedId);

  return (
    <div className="p-4 space-y-5">
      <section className="rounded-xl border border-indigo-100 bg-indigo-50 p-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-indigo-900">
          <HelpCircle size={16} />
          不知道怎么提问？
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-indigo-700">
          选择一篇已上传论文，再点击下面的任务。智能体会自动检索、分解问题、生成带引用的报告，并执行 TRACE 证据检查。
        </p>
      </section>

      <section>
        <label className="mb-1.5 block text-xs font-medium text-gray-600">分析哪篇论文</label>
        {files.length ? (
          <select
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-700 outline-none focus:border-gray-400"
          >
            {files.map((file) => (
              <option key={file.file_id} value={file.file_id}>
                {file.filename}
              </option>
            ))}
          </select>
        ) : (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-700">
            {loadError || '还没有论文。请先点击顶部上传按钮导入 PDF。'}
          </p>
        )}
      </section>

      <section className="space-y-2">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.id}
              type="button"
              disabled={!selected || disabled}
              onClick={() => onAnalyze(selected, action.id)}
              className="w-full rounded-xl border border-gray-200 p-3 text-left transition-colors hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <div className="flex items-start gap-2.5">
                <Icon size={16} className="mt-0.5 shrink-0 text-gray-500" />
                <div>
                  <p className="text-xs font-semibold text-gray-700">{action.title}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-gray-400">{action.description}</p>
                </div>
              </div>
            </button>
          );
        })}
      </section>

      <section className="border-t border-gray-100 pt-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-gray-700">
          <ShieldCheck size={15} className="text-emerald-600" />
          如何检查回答
        </div>
        <ol className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-gray-500">
          <li>1. 展开 Sources 查看论文、章节、页码和证据原文。</li>
          <li>2. 展开 TRACE 查看论断—证据关系及可靠性规则。</li>
          <li>3. 展开 Audit 查看引用和数值是否通过自动检查。</li>
          <li>4. 对不充分结论继续追问，或按反事实建议补充证据。</li>
        </ol>
      </section>
    </div>
  );
}
