export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">ADM Copilot</h1>
        <p className="text-lg text-gray-600 mb-8">
          AI-powered travel audit assistant for Agency Debit Memos
        </p>
        <a
          href="/login"
          className="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
        >
          Get Started
        </a>
      </div>
    </main>
  );
}
