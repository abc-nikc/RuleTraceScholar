import { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react';

const LABELS = {
  supported: { text: 'Supported', tone: 'text-emerald-700', icon: ShieldCheck },
  caution: { text: 'Use with caution', tone: 'text-amber-700', icon: AlertTriangle },
  insufficient: { text: 'Insufficient evidence', tone: 'text-red-700', icon: ShieldAlert },
};

function pct(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

export default function ExplanationPanel({ explanation }) {
  const [open, setOpen] = useState(false);
  const [claimsOpen, setClaimsOpen] = useState(false);
  if (!explanation) return null;

  const label = LABELS[explanation.decision] || LABELS.caution;
  const StatusIcon = label.icon;
  const rules = explanation.rule_trace || [];
  const claims = (explanation.claims || []).filter((claim) => claim.requires_evidence);

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-slate-50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <StatusIcon size={15} className={label.tone} />
          <span className="text-xs font-semibold text-slate-700">TRACE evidence report</span>
          <span className={`text-xs ${label.tone}`}>{label.text}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-mono font-semibold text-slate-700">
            {explanation.reliability_percent}/100
          </span>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-100 px-3 py-3 space-y-4">
          <div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full ${
                  explanation.decision === 'supported'
                    ? 'bg-emerald-500'
                    : explanation.decision === 'caution'
                      ? 'bg-amber-500'
                      : 'bg-red-500'
                }`}
                style={{ width: `${explanation.reliability_percent || 0}%` }}
              />
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
              Uncalibrated evidence-quality index, not a probability that the answer is true.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {[
              ['Coverage', explanation.metrics?.citation_coverage],
              ['Valid refs', explanation.metrics?.citation_validity],
              ['Traceable', explanation.metrics?.traceability],
              ['Diversity', explanation.metrics?.source_diversity],
              ['Density', explanation.metrics?.evidence_density],
            ].map(([name, value]) => (
              <div key={name} className="rounded-lg bg-slate-50 px-2 py-2">
                <div className="text-[10px] uppercase tracking-wide text-slate-400">{name}</div>
                <div className="mt-0.5 text-xs font-semibold text-slate-700">{pct(value)}</div>
              </div>
            ))}
          </div>

          <div>
            <div className="flex items-center gap-1.5 mb-2 text-xs font-semibold text-slate-600">
              <GitBranch size={13} /> Rule activation trace
            </div>
            <div className="space-y-1.5">
              {rules.map((rule) => (
                <div key={rule.rule_id} className="flex items-start gap-2 text-xs">
                  {rule.passed
                    ? <CheckCircle2 size={13} className="mt-0.5 text-emerald-500 shrink-0" />
                    : <XCircle size={13} className="mt-0.5 text-red-500 shrink-0" />}
                  <div className="min-w-0">
                    <span className="font-medium text-slate-700">{rule.rule_id} {rule.name}</span>
                    <span className="ml-1 text-slate-400">
                      {pct(rule.value)} / {pct(rule.threshold)} required
                    </span>
                    <p className="text-[11px] text-slate-500">{rule.rationale}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {claims.length > 0 && (
            <div>
              <button
                onClick={() => setClaimsOpen(!claimsOpen)}
                className="flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-800"
              >
                {claimsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                Claim-to-evidence map ({claims.length})
              </button>
              {claimsOpen && (
                <div className="mt-2 space-y-2 max-h-72 overflow-y-auto">
                  {claims.map((claim) => (
                    <div key={claim.claim_id} className="rounded-lg border border-slate-100 p-2.5">
                      <div className="flex gap-2">
                        <span className={`text-[10px] font-mono ${claim.grounded ? 'text-emerald-600' : 'text-red-600'}`}>
                          {claim.claim_id}
                        </span>
                        <p className="text-xs text-slate-700">{claim.text}</p>
                      </div>
                      {claim.evidence?.map((source) => (
                        <div key={`${claim.claim_id}-${source.ref}`} className="mt-1.5 pl-7 text-[11px] text-slate-500">
                          <span className="font-semibold">[{source.ref}]</span>{' '}
                          {[source.paper_id, source.section, source.page && `p.${source.page}`].filter(Boolean).join(' · ')}
                          {source.excerpt && <p className="mt-0.5 text-slate-400 line-clamp-2">{source.excerpt}</p>}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {(explanation.counterfactuals || []).length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-600 mb-1">What would improve this answer</div>
              <ul className="space-y-1 text-[11px] text-slate-500 list-disc pl-4">
                {explanation.counterfactuals.map((item, index) => (
                  <li key={`${item.target_rule}-${index}`}>{item.action}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
