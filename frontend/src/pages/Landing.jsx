import { useNavigate } from 'react-router-dom';
import { Scale, ShieldCheck, Zap, MessageSquare } from 'lucide-react';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col justify-between">
      {/* Header / Logo */}
      <header className="p-6 flex items-center justify-between max-w-6xl mx-auto w-full">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-amber-500/10 rounded-lg border border-amber-500/20">
            <Scale className="w-8 h-8 text-amber-500" />
          </div>
          <span className="text-2xl font-bold tracking-tight">Legal AI</span>
        </div>
      </header>

      {/* Hero Section */}
      <main className="max-w-4xl mx-auto px-6 text-center py-12">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 text-sm mb-6">
          <Zap className="w-4 h-4" /> AI-Powered Legal Assistant
        </div>

        <h1 className="text-4xl md:text-6xl font-extrabold mb-6 leading-tight">
          Instant Legal Guidance <br />
          <span className="text-amber-500">At Your Fingertips</span>
        </h1>

        <p className="text-slate-300 text-lg md:text-xl mb-10 max-w-2xl mx-auto leading-relaxed">
          Navigate Pakistani laws, penal codes, and legal procedures with ease. 
          Get clear, instant answers to your complex legal questions in English and Urdu.
        </p>

        <button
          onClick={() => navigate('/chat')}
          className="px-8 py-4 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded-xl text-lg shadow-lg hover:shadow-amber-500/20 transition-all cursor-pointer"
        >
          Get Started
        </button>

        {/* Feature Highlights */}
        <div className="grid md:grid-cols-3 gap-6 mt-16 text-left">
          <div className="p-5 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <ShieldCheck className="w-6 h-6 text-amber-500 mb-3" />
            <h3 className="font-semibold text-lg mb-1">Accurate References</h3>
            <p className="text-slate-400 text-sm">Cites relevant sections from PPC, labor laws, and legal frameworks.</p>
          </div>

          <div className="p-5 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <MessageSquare className="w-6 h-6 text-amber-500 mb-3" />
            <h3 className="font-semibold text-lg mb-1">Bilingual Voice & Text</h3>
            <p className="text-slate-400 text-sm">Supports seamless interaction in both English and Roman Urdu / Urdu.</p>
          </div>

          <div className="p-5 bg-slate-800/50 rounded-xl border border-slate-700/50">
            <Scale className="w-6 h-6 text-amber-500 mb-3" />
            <h3 className="font-semibold text-lg mb-1">Document Insights</h3>
            <p className="text-slate-400 text-sm">Upload contracts and legal files to summarize or clarify key clauses.</p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="p-6 text-center text-slate-500 text-sm border-t border-slate-800">
        © {new Date().getFullYear()} Legal AI Advisor. Educational purpose only.
      </footer>
    </div>
  );
}