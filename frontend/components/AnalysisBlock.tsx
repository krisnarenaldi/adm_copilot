"use client";

import ReactMarkdown from "react-markdown";

interface AnalysisBlockProps {
  analysis: string;
}

export function AnalysisBlock({ analysis }: AnalysisBlockProps) {
  return (
    <div className="bg-gray-50 p-6 rounded-lg">
      <h3 className="text-lg font-semibold mb-4 text-gray-800">Analysis</h3>
      <div className="prose text-gray-700">
        <ReactMarkdown>{analysis}</ReactMarkdown>
      </div>
    </div>
  );
}
