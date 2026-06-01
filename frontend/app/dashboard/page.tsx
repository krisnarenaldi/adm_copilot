"use client";

export const dynamic = "force-dynamic";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/app/providers/AuthProvider";
import { getJwt } from "@/lib/auth";
import { AuthGuard } from "@/components/AuthGuard";
import { InputPanel } from "@/components/InputPanel";
import { ResultsPanel } from "@/components/ResultsPanel";
import { submitAudit, uploadFareRules, AuditResponse } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
    const { logout, userEmail } = useAuth();
    const router = useRouter();
    const [isProcessing, setIsProcessing] = useState(false);
    const [processingStep, setProcessingStep] = useState(0);
    const [hasFareRulesFile, setHasFareRulesFile] = useState(false);
    const [result, setResult] = useState<AuditResponse | null>(null);
    const [error, setError] = useState("");

    // Processing steps matching user's requested flow
    const baseProcessingSteps = [
        { label: "Extracting ADM text...", state: "pending" as const },
        { label: "Matching Fare Rules via similarity search...", state: "pending" as const },
        { label: "Analyzing with AI...", state: "pending" as const },
    ];
    const processingSteps = (hasFareRules: boolean) =>
        hasFareRules
            ? [
                { label: "Uploading fare rules...", state: "pending" as const },
                ...baseProcessingSteps,
            ]
            : baseProcessingSteps;

    const getCurrentSteps = (currentStep: number, hasFareRules: boolean) => {
        const steps = processingSteps(hasFareRules);
        return steps.map((step, index) => {
            if (index < currentStep) {
                return { ...step, state: "completed" as const };
            }
            if (index === currentStep) {
                return { ...step, state: "active" as const };
            }
            return step;
        });
    };

    async function handleAuditSubmit(admFile: File, fareRulesFile: File | null, airlineCode: string) {
        setIsProcessing(true);
        setResult(null);
        setError("");
        setProcessingStep(0);
        setHasFareRulesFile(!!fareRulesFile);

        const jwt = getJwt();
        if (!jwt) {
            setError("Session expired, please log in again");
            setIsProcessing(false);
            return;
        }

        try {
            // Upload fare rules first if provided
            if (fareRulesFile) {
                await uploadFareRules(fareRulesFile, airlineCode, jwt);
                setProcessingStep(1);
            }

            // Now run the audit
            const auditResult = await submitAudit(admFile, airlineCode, jwt);
            setProcessingStep(fareRulesFile ? 3 : 2); // Mark last step as completed
            setResult(auditResult);
        } catch (err) {
            setError(err instanceof Error ? err.message : "An unexpected error occurred");
        } finally {
            setIsProcessing(false);
            setProcessingStep(0);
        }
    }

    return (
        <AuthGuard>
            <div className="min-h-screen">
                {/* Header */}
                <header className="bg-white shadow-sm border-b border-gray-200">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
                        <h1 className="text-xl font-bold">ADM Copilot Dashboard</h1>
                        <div className="flex items-center gap-4">
                            <span className="text-gray-600">{userEmail}</span>
                            <button
                                onClick={() => {
                                    logout();
                                    router.push("/");
                                }}
                                className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200"
                            >
                                Logout
                            </button>
                        </div>
                    </div>
                </header>

                {/* Main Content */}
                <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        {/* Input Panel Column */}
                        <div className="space-y-6">
                            <InputPanel
                                onSubmit={handleAuditSubmit}
                                isProcessing={isProcessing}
                                processingSteps={getCurrentSteps(processingStep, hasFareRulesFile)}
                                error={error}
                                onErrorDismiss={() => setError("")}
                            />
                        </div>

                        {/* Results Panel Column */}
                        <div>
                            {result && <ResultsPanel result={result} />}
                            {!result && !isProcessing && (
                                <div className="bg-white p-6 rounded-lg shadow-md text-center text-gray-500">
                                    <svg className="mx-auto h-16 w-16 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    <p className="text-lg">Upload an ADM to see audit results</p>
                                </div>
                            )}
                        </div>
                    </div>
                </main>
            </div>
        </AuthGuard>
    );
}
