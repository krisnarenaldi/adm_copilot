"use client";

import { VerdictBadge } from "./VerdictBadge";
import { AnalysisBlock } from "./AnalysisBlock";
import { DisputeDraftBox } from "./DisputeDraftBox";
import { AuditResponse } from "@/lib/api";

interface ResultsPanelProps {
  result: AuditResponse;
}

export function ResultsPanel({ result }: ResultsPanelProps) {
  return (
    <div className="bg-white p-6 rounded-lg shadow-md space-y-6">
      <div className="text-center">
        <VerdictBadge verdict={result.verdict} />
      </div>
      <AnalysisBlock analysis={result.analysis} />
      <DisputeDraftBox disputeDraft={result.dispute_draft} />
    </div>
  );
}
