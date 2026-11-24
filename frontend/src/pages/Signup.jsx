import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { supabase } from '../supabase/supabaseClient';
import { User, Mail, Lock, AlertCircle, Eye, EyeOff, Phone, MapPin, Scale } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';

export default function Signup() {
  const { lang } = useLanguage();
  const { isDark } = useTheme();
  const isUr = lang === 'ur';

  const [role, setRole] = useState('user');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [contactNumber, setContactNumber] = useState('');
  const [location, setLocation] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  // Helper function to validate username (at least 3 chars, must contain letters, no pure numbers)
  const validateUsername = (name) => {
    const trimmed = name.trim();
    if (trimmed.length < 3) return false;
    const hasLetters = /[a-zA-Z]/.test(trimmed);
    return hasLetters;
  };

  // Helper function to validate password strength
  const validatePassword = (pass) => {
    // Min 8 chars, at least one uppercase, one lowercase, one number, one special character
    const strongPasswordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
    return strongPasswordRegex.test(pass);
  };

  // Helper function to validate real email format
  const validateEmail = (mail) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(mail);
  };

  // Helper function to validate contact number for lawyers
  const validateContactNumber = (phone) => {
    const cleaned = phone.trim();
    const phoneRegex = /^[+]?[\d\s\-()]{7,20}$/;
    return phoneRegex.test(cleaned) && /\d{7,}/.test(cleaned.replace(/\D/g, ''));
  };

  // Helper function to validate location / area for lawyers
  const validateLocation = (area) => {
    return area.trim().length >= 2;
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // 1. Username validation
    if (!validateUsername(username)) {
      setError(
        isUr
          ? 'صارف نام کم از کم 3 حروف کا ہونا چاہیے اور اس میں حروف تہجی شامل ہوں (صرف اعداد نہیں ہو سکتے)۔'
          : 'Username must be at least 3 characters long and include letters (cannot be pure numbers).'
      );
      setLoading(false);
      return;
    }

    // 2. Email validation
    if (!validateEmail(email)) {
      setError(isUr ? 'براہ کرم ایک درست ای میل ایڈریس درج کریں۔' : 'Please enter a valid email address.');
      setLoading(false);
      return;
    }

    // 2b. Lawyer-specific fields validation
    if (role === 'lawyer') {
      if (!validateContactNumber(contactNumber)) {
        setError(isUr ? 'براہ کرم ایک درست رابطہ نمبر درج کریں۔' : 'Please enter a valid contact number.');
        setLoading(false);
        return;
      }

      if (!validateLocation(location)) {
        setError(isUr ? 'براہ کرم اپنا مقام یا علاقہ درج کریں۔' : 'Please enter your location or area.');
        setLoading(false);
        return;
      }
    }

    // 3. Password strength validation
    if (!validatePassword(password)) {
      setError(
        isUr
          ? 'پاس ورڈ کم از کم 8 حروف کا ہونا چاہیے اور اس میں بڑا حرف، چھوٹا حرف، عدد اور خاص علامت شامل ہو۔'
          : 'Password must be at least 8 characters long and include uppercase, lowercase, number, and special character.'
      );
      setLoading(false);
      return;
    }

    // 4. Confirm password matching
    if (password !== confirmPassword) {
      setError(isUr ? 'پاس ورڈز مماثل نہیں ہیں۔' : 'Passwords do not match.');
      setLoading(false);
      return;
    }

    try {
      const metadata = {
        username: username.trim(),
        role,
      };

      if (role === 'lawyer') {
        metadata.contact_number = contactNumber.trim();
        metadata.location = location.trim();
      }

      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: metadata,
        },
      });

      if (signUpError) {
        throw signUpError;
      }

      // Check if Supabase returned a user with empty identities (indicates email already exists)
      if (data?.user && data.user.identities && data.user.identities.length === 0) {
        setError(
          isUr
            ? 'یہ ای میل پہلے سے رجسٹرڈ ہے۔ براہ کرم لاگ ان کریں۔'
            : 'This email is already registered. Please log in instead.'
        );
        setLoading(false);
        return;
      }

      // Direct login on successful signup, navigating straight to chat dashboard
      navigate('/chat');
    } catch (err) {
      const msg = err.message || '';
      if (msg.toLowerCase().includes('already registered') || msg.toLowerCase().includes('already exists')) {
        setError(
          isUr
            ? 'یہ ای میل پہلے سے رجسٹرڈ ہے۔ براہ کرم لاگ ان کریں۔'
            : 'This email is already registered. Please log in instead.'
        );
      } else {
        setError(msg || (isUr ? 'سائن اپ کے دوران ایک خرابی پیش آئی۔' : 'An error occurred during sign up.'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      dir={isUr ? 'rtl' : 'ltr'}
      className={`flex min-h-screen items-center justify-center px-4 transition-colors ${
        isDark ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-900'
      }`}
    >
      {/* Inline style to hide browser native password reveal icons */}
      <style>{`
        input::-ms-reveal,
        input::-ms-clear {
          display: none;
        }
      `}</style>

      <div
        className={`w-full max-w-md rounded-2xl p-8 border shadow-2xl ${
          isDark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200'
        }`}
      >
        <h2 className="text-2xl font-bold mb-2 text-center">
          {isUr ? 'اکاؤنٹ بنائیں' : 'Create an Account'}
        </h2>
        <p className={`text-xs text-center mb-6 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
          {isUr ? 'پاکستانی قانونی مشاورت کے لیے لیگل اے آئی میں شامل ہوں' : 'Join Legal AI for smart Pakistani legal advisory'}
        </p>
        
        {error && (
          <div className="mb-4 rounded-xl bg-red-500/10 p-3 text-xs text-red-400 border border-red-500/20 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSignup} className="space-y-4">
          <div>
            <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {isUr ? 'اکاؤنٹ کی قسم' : 'Account Type'}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setRole('user')}
                className={`flex items-center justify-center gap-2 rounded-xl border py-2.5 text-xs font-semibold transition-colors cursor-pointer ${
                  role === 'user'
                    ? 'bg-emerald-500/15 border-emerald-500 text-emerald-400'
                    : isDark
                      ? 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                      : 'bg-slate-100 border-slate-300 text-slate-600 hover:text-slate-900'
                }`}
              >
                <User className="w-4 h-4" />
                <span>{isUr ? 'صارف' : 'User'}</span>
              </button>
              <button
                type="button"
                onClick={() => setRole('lawyer')}
                className={`flex items-center justify-center gap-2 rounded-xl border py-2.5 text-xs font-semibold transition-colors cursor-pointer ${
                  role === 'lawyer'
                    ? 'bg-emerald-500/15 border-emerald-500 text-emerald-400'
                    : isDark
                      ? 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                      : 'bg-slate-100 border-slate-300 text-slate-600 hover:text-slate-900'
                }`}
              >
                <Scale className="w-4 h-4" />
                <span>{isUr ? 'وکیل' : 'Lawyer'}</span>
              </button>
            </div>
          </div>

          <div>
            <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {isUr ? 'صارف نام' : 'Username'}
            </label>
            <div className="relative">
              <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                <User className="w-4 h-4" />
              </span>
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                  isUr ? 'pr-10 pl-4' : 'pl-10 pr-4'
                } ${
                  isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                }`}
                placeholder={isUr ? 'مثلاً قاسم' : 'e.g Qasim'}
              />
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {isUr ? 'کم از کم 3 حروف کا ہو اور اس میں حروف تہجی شامل ہوں۔' : 'Must be 3+ chars and include letters.'}
            </p>
          </div>

          <div>
            <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {isUr ? 'ای میل ایڈریس' : 'Email Address'}
            </label>
            <div className="relative">
              <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                <Mail className="w-4 h-4" />
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                  isUr ? 'pr-10 pl-4' : 'pl-10 pr-4'
                } ${
                  isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                }`}
                placeholder="name@example.com"
              />
            </div>
          </div>

          {role === 'lawyer' && (
            <>
              <div>
                <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                  {isUr ? 'رابطہ نمبر' : 'Contact Number'}
                </label>
                <div className="relative">
                  <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                    <Phone className="w-4 h-4" />
                  </span>
                  <input
                    type="tel"
                    required
                    value={contactNumber}
                    onChange={(e) => setContactNumber(e.target.value)}
                    className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                      isUr ? 'pr-10 pl-4' : 'pl-10 pr-4'
                    } ${
                      isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                    }`}
                    placeholder="+92 300 1234567"
                  />
                </div>
              </div>

              <div>
                <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                  {isUr ? 'مقام / علاقہ' : 'Location / Area'}
                </label>
                <div className="relative">
                  <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                    <MapPin className="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    required
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                      isUr ? 'pr-10 pl-4' : 'pl-10 pr-4'
                    } ${
                      isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                    }`}
                    placeholder={isUr ? 'مثلاً گلبرگ، لاہور' : 'e.g. Gulberg, Lahore'}
                  />
                </div>
              </div>
            </>
          )}

          <div>
            <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {isUr ? 'پاس ورڈ' : 'Password'}
            </label>
            <div className="relative">
              <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                <Lock className="w-4 h-4" />
              </span>
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                  isUr ? 'pr-10 pl-10' : 'pl-10 pr-10'
                } ${
                  isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                }`}
                placeholder={isUr ? 'کم از کم 8 حروف، بڑا/چھوٹا حرف، عدد، علامت' : 'Min 8 chars, Upper, Lower, Number, Symbol'}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className={`absolute inset-y-0 flex items-center text-slate-400 hover:text-white cursor-pointer ${
                  isUr ? 'left-0 pl-3' : 'right-0 pr-3'
                }`}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {isUr
                ? 'کم از کم 8 حروف میں بڑا حرف، چھوٹا حرف، عدد اور خاص علامت شامل ہو۔'
                : 'Must contain 8+ chars with uppercase, lowercase, number & symbol.'}
            </p>
          </div>

          <div>
            <label className={`block text-xs font-semibold uppercase tracking-wider mb-1 ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              {isUr ? 'پاس ورڈ کی تصدیق کریں' : 'Confirm Password'}
            </label>
            <div className="relative">
              <span className={`absolute inset-y-0 flex items-center text-slate-500 ${isUr ? 'right-0 pr-3' : 'left-0 pl-3'}`}>
                <Lock className="w-4 h-4" />
              </span>
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className={`w-full rounded-xl border py-2.5 text-xs focus:outline-none focus:border-emerald-500 transition-colors ${
                  isUr ? 'pr-10 pl-10' : 'pl-10 pr-10'
                } ${
                  isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
                }`}
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className={`absolute inset-y-0 flex items-center text-slate-400 hover:text-white cursor-pointer ${
                  isUr ? 'left-0 pl-3' : 'right-0 pr-3'
                }`}
              >
                {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 py-3 font-bold text-xs transition-colors disabled:opacity-50 cursor-pointer shadow-lg shadow-emerald-500/10"
          >
            {loading
              ? (isUr ? 'اکاؤنٹ بن رہا ہے اور لاگ ان ہو رہا ہے...' : 'Creating Account & Logging In...')
              : (isUr ? 'سائن اپ کریں' : 'Sign Up')}
          </button>
        </form>

        <p className={`mt-6 text-center text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
          {isUr ? 'پہلے سے اکاؤنٹ موجود ہے؟' : 'Already have an account?'}{' '}
          <Link to="/login" className="text-emerald-400 hover:underline font-semibold">
            {isUr ? 'لاگ ان کریں' : 'Log in'}
          </Link>
        </p>
      </div>
    </div>
  );
}
