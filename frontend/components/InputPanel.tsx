"use client";

import React, { useState } from "react";
import { AirlineSelector } from "./AirlineSelector";
import { FileDropZone } from "./FileDropZone";
import { ProcessingTracker } from "./ProcessingTracker";

interface InputPanelProps {
  onSubmit: (admFile: File, fareRulesFile: File | null, airlineCode: string) => void;
  isProcessing: boolean;
  processingSteps: { label: string; state: "pending" | "active" | "completed" }[];
  error?: string;
  onErrorDismiss?: () => void;
}

export function InputPanel({
  onSubmit,
  isProcessing,
  processingSteps,
  error,
  onErrorDismiss,
}: InputPanelProps) {
  const [airlineCode, setAirlineCode] = useState("");
  const [admFile, setAdmFile] = useState<File | null>(null);
  const [fareRulesFile, setFareRulesFile] = useState<File | null>(null);
  const [airlineError, setAirlineError] = useState("");
  const [admFileError, setAdmFileError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAirlineError("");
    setAdmFileError("");

    let hasError = false;
    if (!airlineCode) {
      setAirlineError("Please select an airline");
      hasError = true;
    }
    if (!admFile) {
      setAdmFileError("Please upload an ADM PDF file");
      hasError = true;
    }
    if (hasError) return;

    onSubmit(admFile as File, fareRulesFile, airlineCode);
  }

  return (
    <div className="bg-white p-6 rounded-lg shadow-md">
      <h2 className="text-2xl font-semibold mb-6">Start an Audit</h2>
      <form onSubmit={handleSubmit} className="space-y-6">
        <AirlineSelector
          value={airlineCode}
          onChange={setAirlineCode}
          error={airlineError}
          disabled={isProcessing}
        />
        <FileDropZone
          label="Upload Fare Rules (Optional)"
          file={fareRulesFile}
          onFileChange={setFareRulesFile}
          disabled={isProcessing}
        />
        <FileDropZone
          label="Upload ADM PDF"
          file={admFile}
          onFileChange={setAdmFile}
          error={admFileError}
          disabled={isProcessing}
        />
        {error && (
          <div className="flex items-center justify-between bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
            <p className="text-sm">{error}</p>
            <button
              type="button"
              onClick={onErrorDismiss}
              className="text-red-500 hover:text-red-700"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        <button
          type="submit"
          disabled={isProcessing}
          className={`w-full py-3 px-4 rounded-md font-semibold text-white transition-colors ${
            isProcessing ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {isProcessing ? "Processing..." : "Run Audit"}
        </button>
      </form>
      {isProcessing && (
        <div className="mt-8">
          <ProcessingTracker steps={processingSteps} />
        </div>
      )}
    </div>
  );
}
