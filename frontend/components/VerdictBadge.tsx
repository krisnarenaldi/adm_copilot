// components/VerdictBadge.tsx
import React from "react";

interface VerdictBadgeProps {
  verdict: "VALID DISPUTE FOUND" | "VALID ADM / NO DISPUTE";
}

export function VerdictBadge({ verdict }: VerdictBadgeProps) {
  const isDispute = verdict === "VALID DISPUTE FOUND";
  return (
    <div
      className={`inline-block px-6 py-3 rounded-full font-bold text-white text-lg ${
        isDispute ? "bg-green-500" : "bg-red-500"
      }`}
    >
      {verdict}
    </div>
  );
}
