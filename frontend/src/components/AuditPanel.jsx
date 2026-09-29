import { useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Hash,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Scale,
} from 'lucide-react';

const STATUS = {
  pass: { icon: CheckCircle2, tone: 'text-emerald-600' },
  warning: { icon: AlertTriangle, tone: 'text-amber-600' },
  fail: { icon: XCircle, tone: 'text-red-600' },
  untestable: { icon: FlaskConical, tone: 'text-slate-400' },
};

const SEMANTIC_STATUS = {
  entailed: { label: '支持', tone: 'text-emerald-600' },
  contradicted: { label: '矛盾', tone: 'text-red-600' },
  insufficient: { label: '不足', tone: 'text-amber-600' },
};

export default function AuditPanel({ claimTests, capsule, repair }) {
  const [open, setOpen] = useState(false);
  if (!claimTests && !capsule && !repair) return null;
  const counts = claimTests?.counts || {};
  const semantic = claimTests?.semantic_checks;

  return (
    <div className="mt-2 rounded-xl border border-indigo-100 bg-indigo-50/30 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-indigo-50/60"
      >
        <div className="flex items-center gap-2">
          <FlaskConical size={14} className="text-indigo-600" />
          <span className="text-xs font-semibold text-slate-700">Scientific claim tests</span>
          <span className="text-[11px] text-slate-500">
            {counts.pass || 0} pass · {counts.warning || 0} review · {counts.fail || 0} fail
          </span>
          {claimTests?.release_decision && (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
              claimTests.release_decision === 'supported'
                ? 'bg-emerald-100 text-emerald-700'
                : claimTests.release_decision === 'blocked'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-amber-100 text-amber-700'
            }`}>
              {claimTests.release_decision === 'supported' ? '可支持' : claimTests.release_decision === 'blocked' ? '阻止直接采信' : '需复核'}
            </span>
          )}
        </div>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </button>

      {open && (
        <div className="border-t border-indigo-100 px-3 py-3 space-y-3">
          {(claimTests?.tests || []).map((test) => {
            const style = STATUS[test.status] || STATUS.untestable;
            const Icon = style.icon;
            return (
              <div key={test.test_id} className="flex items-start gap-2">
                <Icon size={13} className={`mt-0.5 shrink-0 ${style.tone}`} />
                <div>
                  <p className="text-xs font-medium text-slate-700">{test.claim_id} · {test.name}</p>
                  <p className="text-[11px] leading-relaxed text-slate-500">{test.detail}</p>
                </div>
              </div>
            );
          })}
          {repair?.attempted && (
            <div className="pt-2 border-t border-indigo-100 flex items-start gap-2">
              <RefreshCw size={13} className={`mt-0.5 shrink-0 ${repair.applied ? 'text-emerald-600' : 'text-amber-600'}`} />
              <div>
                <p className="text-xs font-medium text-slate-700">
                  自动补证：{repair.applied ? '已采用改进结果' : '已尝试，保留原答案'}
                </p>
                <p className="text-[11px] leading-relaxed text-slate-500">
                  TRACE {repair.before_decision || 'unknown'} ({repair.before_score ?? '—'})
                  {repair.after_decision && ` → ${repair.after_decision} (${repair.after_score ?? '—'})`}
                  {Number.isInteger(repair.added_evidence) && ` · 新增 ${repair.added_evidence} 条候选证据`}
                </p>
              </div>
            </div>
          )}
          {semantic && (
            <div className="pt-2 border-t border-indigo-100 space-y-2">
              <div className="flex items-start gap-2">
                <Scale size={13} className="mt-0.5 shrink-0 text-violet-600" />
                <div>
                  <p className="text-xs font-medium text-slate-700">
                    语义证据审计 · {semantic.decision === 'pass' ? '通过' : semantic.decision === 'conflict' ? '发现冲突' : semantic.decision === 'review' ? '需要复核' : '不可用'}
                  </p>
                  <p className="text-[10px] text-slate-400">模型辅助判断，不等同于科学事实证明</p>
                </div>
              </div>
              {(semantic.judgements || []).map((item, index) => {
                const style = SEMANTIC_STATUS[item.verdict] || SEMANTIC_STATUS.insufficient;
                return (
                  <div key={`${item.claim_id}-${index}`} className="ml-5 rounded-lg bg-white/70 px-2.5 py-2">
                    <p className={`text-[11px] font-medium ${style.tone}`}>{item.claim_id} · {style.label}</p>
                    <p className="mt-0.5 text-[10px] leading-relaxed text-slate-500">{item.rationale}</p>
                  </div>
                );
              })}
              {(semantic.conflicts || []).map((item, index) => (
                <div key={`conflict-${index}`} className="ml-5 rounded-lg border border-red-100 bg-red-50 px-2.5 py-2">
                  <p className="text-[11px] font-medium text-red-700">证据 [{item.left_ref}] ↔ [{item.right_ref}] · {item.relation}</p>
                  <p className="mt-0.5 text-[10px] leading-relaxed text-red-600">{item.rationale}</p>
                </div>
              ))}
            </div>
          )}
          {capsule && (
            <div className="pt-2 border-t border-indigo-100 flex items-start gap-2">
              <Hash size={13} className="mt-0.5 text-indigo-500 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-700">Research Replay Capsule</p>
                <p className="text-[10px] font-mono text-slate-400 break-all">{capsule.capsule_id}</p>
                <p className="text-[10px] font-mono text-slate-400 break-all">SHA-256 {capsule.capsule_hash}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
