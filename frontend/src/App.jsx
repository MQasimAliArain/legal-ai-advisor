import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import ResetPassword from './pages/ResetPassword';
import ChatDashboard from './pages/ChatDashboard';
import { supabase } from './supabase/supabaseClient';

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isPasswordRecovery, setIsPasswordRecovery] = useState(false);

  useEffect(() => {
    // Check if URL contains a recovery hash fragment immediately on load
    const hash = window.location.hash;
    if (hash && hash.includes('type=recovery')) {
      setIsPasswordRecovery(true);
      setLoading(false);
      return;
    }

    // Check active session on load and verify user exists in Supabase database
    const checkUserSession = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        
        if (session?.user) {
          const { data: { user: verifiedUser }, error } = await supabase.auth.getUser();
          
          if (error || !verifiedUser) {
            // User was deleted from Supabase dashboard -> clear stale session
            await supabase.auth.signOut();
            setUser(null);
          } else {
            setUser(verifiedUser);
          }
        } else {
          setUser(null);
        }
      } catch (err) {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkUserSession();

    // Listen for changes in auth state (login/logout/recovery)
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'PASSWORD_RECOVERY') {
        setIsPasswordRecovery(true);
        setLoading(false);
        return;
      }

      if (session?.user) {
        const { data: { user: verifiedUser }, error } = await supabase.auth.getUser();
        if (error || !verifiedUser) {
          await supabase.auth.signOut();
          setUser(null);
        } else {
          setUser(verifiedUser);
        }
      } else {
        setUser(null);
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setUser(null);
  };

  if (loading) {
    return <div className="flex h-screen items-center justify-center bg-slate-950 text-white">Loading...</div>;
  }

  // If user clicked a password recovery link, force them to the reset password page
  if (isPasswordRecovery) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<ResetPassword />} />
        </Routes>
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* Landing Page */}
        <Route path="/" element={<Landing />} />

        {/* Login Page */}
        <Route path="/login" element={!user ? <Login /> : <Navigate to="/chat" />} />

        {/* Signup Page */}
        <Route path="/signup" element={!user ? <Signup /> : <Navigate to="/chat" />} />

        {/* Reset Password Page */}
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* Chat Dashboard Route with proper logout handler */}
        <Route path="/chat" element={<ChatDashboard user={user} onLogout={handleLogout} />} />

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}