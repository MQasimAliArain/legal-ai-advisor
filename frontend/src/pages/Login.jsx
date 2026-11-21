import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { supabase } from '../supabase/supabaseClient';
import { Mail, Lock, AlertCircle, Gavel, Eye, EyeOff, X, Check } from 'lucide-react';

const LAST_ACCOUNT_STORAGE_KEY = 'legal_ai_advisor_last_account_v1';

const saveLastAccountInfo = (account) => {
  if (!account || typeof window === 'undefined') return;
  try {
    const payload = {
      id: account.id || null,
      email: account.email ? String(account.email).toLowerCase() : null,
    };
    if (payload.id || payload.email) {
      window.localStorage.setItem(LAST_ACCOUNT_STORAGE_KEY, JSON.stringify(payload));
    }
  } catch {
    // Ignore storage quota or private-mode errors
  }
};

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Forgot password modal state
  const [showForgotPasswordModal, setShowForgotPasswordModal] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetMessage, setResetMessage] = useState(null);
  const [resetError, setResetError] = useState(null);

  const navigate = useNavigate();

  const validateEmailFormat = (mail) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(mail);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const trimmedEmail = email.trim();

    // 1. Check if email/password is empty or malformed (e.g., "qasimaliarain")
    if (!trimmedEmail || !password || !validateEmailFormat(trimmedEmail)) {
      setError('Invalid login credentials');
      setLoading(false);
      return;
    }

    try {
      // 2. Check if email exists in public.profiles first
      const { data: profileCheck, error: lookupError } = await supabase
        .from('profiles')
        .select('email')
        .ilike('email', trimmedEmail)
        .maybeSingle();

      if (!lookupError && !profileCheck) {
        setError('Incorrect email');
        setLoading(false);
        return;
      }

      // 3. Attempt password sign-in
      const { data, error: loginError } = await supabase.auth.signInWithPassword({
        email: trimmedEmail,
        password,
      });

      if (loginError) {
        const msg = loginError.message.toLowerCase();
        if (msg.includes('invalid login credentials') || msg.includes('invalid grant')) {
          setError('Incorrect password');
        } else if (msg.includes('email not confirmed')) {
          setError('Please confirm your email address before logging in.');
        } else {
          setError(loginError.message);
        }
        setLoading(false);
      } else {
        const signedInUser = data?.user || data?.session?.user || { email: trimmedEmail };
        saveLastAccountInfo(signedInUser);
        navigate('/chat');
      }
    } catch (err) {
      setError('An unexpected error occurred during login.');
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setResetLoading(true);
    setResetError(null);
    setResetMessage(null);

    const trimmedResetEmail = resetEmail.trim();

    if (!validateEmailFormat(trimmedResetEmail)) {
      setResetError('Please enter a valid email address.');
      setResetLoading(false);
      return;
    }

    try {
      const { error: resetErr } = await supabase.auth.resetPasswordForEmail(trimmedResetEmail, {
        redirectTo: `${window.location.origin}/login`,
      });

      if (resetErr) {
        setResetError(resetErr.message);
      } else {
        setResetMessage('Password reset link sent! Check your inbox.');
      }
    } catch (err) {
      setResetError('Failed to send password reset email.');
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 text-white">
      {/* Inline style to hide browser native password reveal icons */}
      <style>{`
        input::-ms-reveal,
        input::-ms-clear {
          display: none;
        }
      `}</style>

      <div className="w-full max-w-md rounded-2xl bg-slate-900 p-8 border border-slate-800 shadow-2xl">
        <div className="flex justify-center mb-4">
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl">
            <Gavel className="w-6 h-6" />
          </div>
        </div>
        
        <h2 className="text-2xl font-bold mb-2 text-center">Welcome Back</h2>
        <p className="text-xs text-slate-400 text-center mb-6">Log in to your Legal AI account</p>
        
        {error && (
          <div className="mb-4 rounded-xl bg-red-500/10 p-3 text-xs text-red-400 border border-red-500/20 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} noValidate className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Email Address</label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                <Mail className="w-4 h-4" />
              </span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl bg-slate-800 border border-slate-700 pl-10 pr-4 py-2.5 text-xs text-white focus:outline-none focus:border-emerald-500 transition-colors"
                placeholder="name@example.com"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">Password</label>
              <button
                type="button"
                onClick={() => {
                  setResetEmail(email); // prefill with current email input if any
                  setResetError(null);
                  setResetMessage(null);
                  setShowForgotPasswordModal(true);
                }}
                className="text-[11px] text-emerald-400 hover:underline cursor-pointer font-medium"
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                <Lock className="w-4 h-4" />
              </span>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl bg-slate-800 border border-slate-700 pl-10 pr-10 py-2.5 text-xs text-white focus:outline-none focus:border-emerald-500 transition-colors"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-white cursor-pointer"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 py-3 font-bold text-xs transition-colors disabled:opacity-50 cursor-pointer shadow-lg shadow-emerald-500/10"
          >
            {loading ? 'Logging in...' : 'Log In'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-400">
          Don't have an account?{' '}
          <Link to="/signup" className="text-emerald-400 hover:underline font-semibold">Sign up</Link>
        </p>
      </div>

      {/* Forgot Password Modal */}
      {showForgotPasswordModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="border rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 relative bg-slate-900 border-slate-800 text-white">
            <button
              onClick={() => setShowForgotPasswordModal(false)}
              className="absolute top-4 right-4 p-1 rounded-lg transition cursor-pointer text-slate-400 hover:text-white hover:bg-slate-800"
            >
              <X className="w-5 h-5" />
            </button>

            <h3 className="text-lg font-bold">Reset Password</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Enter your email address below and we will send you a secure link to reset your password.
            </p>

            {resetError && (
              <div className="rounded-xl bg-red-500/10 p-3 text-xs text-red-400 border border-red-500/20 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{resetError}</span>
              </div>
            )}

            {resetMessage && (
              <div className="rounded-xl bg-emerald-500/10 p-3 text-xs text-emerald-400 border border-emerald-500/20 flex items-center gap-2">
                <Check className="w-4 h-4 shrink-0" />
                <span>{resetMessage}</span>
              </div>
            )}

            <form onSubmit={handleForgotPassword} className="space-y-4 pt-2">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Email Address</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                    <Mail className="w-4 h-4" />
                  </span>
                  <input
                    type="email"
                    required
                    value={resetEmail}
                    onChange={(e) => setResetEmail(e.target.value)}
                    className="w-full rounded-xl bg-slate-800 border border-slate-700 pl-10 pr-4 py-2.5 text-xs text-white focus:outline-none focus:border-emerald-500 transition-colors"
                    placeholder="name@example.com"
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForgotPasswordModal(false)}
                  className="flex-1 py-2.5 px-4 rounded-xl text-xs font-semibold transition cursor-pointer bg-slate-800 hover:bg-slate-700 text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resetLoading}
                  className="flex-1 py-2.5 px-4 bg-emerald-500 hover:bg-emerald-600 text-slate-950 rounded-xl text-xs font-bold transition cursor-pointer disabled:opacity-50"
                >
                  {resetLoading ? 'Sending...' : 'Send Reset Link'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
