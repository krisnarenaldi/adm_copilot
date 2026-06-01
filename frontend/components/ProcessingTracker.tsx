// components/ProcessingTracker.tsx
import React from "react";

interface ProcessingStep {
  label: string;
  state: "pending" | "active" | "completed";
}

interface ProcessingTrackerProps {
  steps: ProcessingStep[];
}

export function ProcessingTracker({ steps }: ProcessingTrackerProps) {
  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        {steps.map((step, index) => (
          <React.Fragment key={index}>
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${
                  step.state === "completed"
                    ? "bg-green-500 text-white"
                    : step.state === "active"
                    ? "bg-blue-500 text-white animate-pulse"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {step.state === "completed" ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  index + 1
                )}
              </div>
              <p
                className={`mt-2 text-xs ${
                  step.state === "active" ? "text-blue-600 font-medium" : step.state === "completed" ? "text-green-600" : "text-gray-500"
                }`}
              >
                {step.label}
              </p>
            </div>
            {index < steps.length - 1 && (
              <div className="flex-1 h-0.5 mx-2 bg-gray-200">
                {steps[index].state === "completed" && steps[index + 1].state !== "pending" ? (
                  <div className="h-full bg-green-500" />
                ) : null}
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
