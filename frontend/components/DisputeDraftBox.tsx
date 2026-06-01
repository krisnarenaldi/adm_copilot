"use client";

import React, { useState } from "react";

interface DisputeDraftBoxProps {
  disputeDraft: string;
}

export function DisputeDraftBox({ disputeDraft }: DisputeDraftBoxProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(disputeDraft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }

  return (
    <div className="bg-gray-50 p-6 rounded-lg">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Dispute Draft</h3>
        <button
          onClick={handleCopy}
          className={`px-4 py-2 rounded-md font-medium transition-colors ${
            copied ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700 hover:bg-blue-200"
          }`}
        >
          {copied ? (
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
              Copied!
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy to Clipboard
            </div>
          )}
        </button>
      </div>
      <textarea
        readOnly
        value={disputeDraft}
        className="w-full h-64 p-4 border border-gray-300 rounded-md bg-white text-gray-700 resize-none"
      />
    </div>
  );
}
