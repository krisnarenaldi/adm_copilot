import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "./providers/AuthProvider";

export const metadata: Metadata = {
  title: "ADM Copilot - AI-Powered Travel Audit Assistant",
  description: "Automate the investigation of Agency Debit Memos (ADMs). Compare ADMs against airline Fare Rules using AI to generate structured verdicts and formal dispute drafts.",
  openGraph: {
    title: "ADM Copilot - AI-Powered Travel Audit Assistant",
    description: "Automate the investigation of Agency Debit Memos (ADMs). Compare ADMs against airline Fare Rules using AI to generate structured verdicts and formal dispute drafts.",
    url: "https://adm-copilot.vercel.app",
    siteName: "ADM Copilot",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "ADM Copilot - AI-Powered Travel Audit Assistant",
    description: "Automate the investigation of Agency Debit Memos (ADMs). Compare ADMs against airline Fare Rules using AI to generate structured verdicts and formal dispute drafts.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-100 text-slate-800">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
