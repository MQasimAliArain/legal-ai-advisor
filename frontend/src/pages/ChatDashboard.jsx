// src/pages/ChatDashboard.jsx
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Send } from 'lucide-react';
import Sidebar from '../components/layout/Sidebar';
import BookAnswerNote from '../components/chat/BookAnswerNote';
import { useLanguage } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';
import { supabase } from '../supabase/supabaseClient';

const SHORT_DISCLAIMER =
  'Disclaimer: For prototype informational purposes only; not formal legal advice.';

const STORAGE_PREFIX = 'legal_ai_advisor_chats_v1_';

const getAccountStorageKey = (account) => {
  const identifier = account?.id || account?.email;
  return identifier ? `${STORAGE_PREFIX}${encodeURIComponent(String(identifier).toLowerCase())}` : null;
};

const readStoredAccountChats = (storageKey) => {
  if (!storageKey || typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeStoredAccountChats = (storageKey, chats) => {
  if (!storageKey || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(chats));
  } catch {
    // Ignore storage quota or private-mode errors
  }
};

export default function ChatDashboard({ user, onLogout }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [recentChats, setRecentChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [activeUser, setActiveUser] = useState(user || null);

  const chatContainerRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);
  const hydratedStorageKeyRef = useRef(null);

  const { lang, t } = useLanguage();
  const { isDark } = useTheme();
  const navigate = useNavigate();

  // Keep activeUser synced with prop or Supabase session across refresh / tab off-and-on
  useEffect(() => {
    if (user) {
      setActiveUser(user);
      return;
    }

    let isMounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (isMounted && data?.session?.user) {
        setActiveUser(data.session.user);
      }
    });

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!isMounted) return;
      if (session?.user) {
        setActiveUser(session.user);
      } else {
        setActiveUser(null);
      }
    });

    return () => {
      isMounted = false;
      authListener?.subscription?.unsubscribe();
    };
  }, [user]);

  const effectiveUser = user || activeUser;
  const storageKey = getAccountStorageKey(effectiveUser);

  // Hydrate chats for the current account on mount, refresh, or account change
  useEffect(() => {
    if (!storageKey) {
      hydratedStorageKeyRef.current = null;
      return;
    }

    if (hydratedStorageKeyRef.current === storageKey) {
      return;
    }

    hydratedStorageKeyRef.current = storageKey;
    const savedChats = readStoredAccountChats(storageKey);
    setRecentChats(savedChats);

    if (savedChats.length > 0) {
      const latestChat = savedChats[0];
      setCurrentChatId(latestChat.id);
      setMessages(Array.isArray(latestChat.messages) ? latestChat.messages : []);
      shouldAutoScrollRef.current = true;
      requestAnimationFrame(() => scrollToBottom('auto'));
    } else {
      setCurrentChatId(null);
      setMessages([]);
    }
  }, [storageKey]);

  // Persist account chats whenever recentChats changes for a signed-in account
  useEffect(() => {
    if (!storageKey || hydratedStorageKeyRef.current !== storageKey) return;
    writeStoredAccountChats(storageKey, recentChats);
  }, [storageKey, recentChats]);

  const scrollToBottom = (behavior = 'smooth') => {
    const el = chatContainerRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior,
    });
  };

  const handleChatScroll = () => {
    const el = chatContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= 100;
  };

  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      requestAnimationFrame(() => {
        scrollToBottom(messages.length <= 1 ? 'auto' : 'smooth');
      });
    }
  }, [messages, isLoading]);

  // Helper to detect language from input string
  const detectLanguage = (text) => {
    // 1. Check for Pure Urdu Script
    const urduRegex = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/;
    if (urduRegex.test(text)) {
      return 'pure_urdu';
    }

    // 2. Check for English indicator words
    const englishWords = ['how', 'what', 'where', 'when', 'why', 'who', 'is', 'are', 'the', 'to', 'can', 'should', 'file'];
    const cleanWords = text.toLowerCase().replace(/[.,?!]/g, '').split(/\s+/);
    const englishMatches = cleanWords.filter(word => englishWords.includes(word)).length;

    // 3. Check for Roman Urdu indicator words
    const romanUrduWords = [
      'kesay', 'kaise', 'karen', 'kare', 'krain', 'kia', 'kya',
      'hai', 'hain', 'mein', 'mai', 'se', 'ko', 'par', 'pe', 'nahi', 'nahin',
      'sza', 'saza', 'qatil', 'qatl', 'thana', 'muqadma', 'kanoon', 'qanoon'
    ];
    const romanUrduMatches = cleanWords.filter(word => romanUrduWords.includes(word)).length;

    if (romanUrduMatches > 0 && romanUrduMatches >= englishMatches) {
      return 'roman_urdu';
    }

    return 'english';
  };

  // Fallback response when FastAPI / ChromaDB backend API is not reachable
  const getUnconnectedModelNotice = (language) => {
    if (language === 'pure_urdu') {
      return `ChromaDB اور FastAPI بیک اینڈ فی الحال منسلک نہیں ہے۔ براہ کرم یقینی بنائیں کہ ChromaDB اور FastAPI سرور چل رہے ہیں۔`;
    }
    if (language === 'roman_urdu') {
      return `ChromaDB aur FastAPI backend filhal connect nahi hai. Barah-e-karam check karein ke ChromaDB aur FastAPI server chal rahe hain.`;
    }
    return `The ChromaDB / FastAPI backend is not reachable right now. Please make sure ChromaDB (port 8000) and FastAPI (port 8001) are running.`;
  };

  const handleLogoutAction = () => {
    if (storageKey) {
      writeStoredAccountChats(storageKey, recentChats);
    }
    hydratedStorageKeyRef.current = null;
    setMessages([]);
    setRecentChats([]);
    setCurrentChatId(null);
    setActiveUser(null);

    if (onLogout) {
      onLogout();
    }
  };

  const handleSend = async (e) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    // Check Supabase active database session before allowing query submission
    const { data: { session } } = await supabase.auth.getSession();

    // If the user is not authenticated, redirect them directly to the login page when submitting a query
    if (!effectiveUser && !session) {
      navigate('/login');
      return;
    }

    const currentAccountKey = storageKey || getAccountStorageKey(session?.user);
    if (currentAccountKey && hydratedStorageKeyRef.current !== currentAccountKey) {
      hydratedStorageKeyRef.current = currentAccountKey;
    }

    shouldAutoScrollRef.current = true;
    const userQuery = input.trim();
    const newMessages = [...messages, { role: 'user', content: userQuery }];
    setMessages(newMessages);
    setInput('');
    setIsLoading(true);

    let activeId = currentChatId;

    if (!activeId) {
      activeId = Date.now();
      setCurrentChatId(activeId);
      setRecentChats((prev) => {
        const updatedChats = [
          {
            id: activeId,
            title: userQuery,
            pinned: false,
            createdAt: Date.now(),
            messages: newMessages,
          },
          ...prev,
        ];
        if (currentAccountKey) {
          writeStoredAccountChats(currentAccountKey, updatedChats);
        }
        return updatedChats;
      });
    } else {
      setRecentChats((prev) => {
        const updatedChats = prev.map((c) =>
          c.id === activeId ? { ...c, messages: newMessages } : c
        );
        if (currentAccountKey) {
          writeStoredAccountChats(currentAccountKey, updatedChats);
        }
        return updatedChats;
      });
    }

    const detectedLang = detectLanguage(userQuery);
    let assistantMessage = {
      role: 'assistant',
      content: '',
      reference: null,
      disclaimer: SHORT_DISCLAIMER,
    };

    try {
      const apiBaseUrl = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');
      const response = await fetch(`${apiBaseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userQuery, language: detectedLang }),
      });

      if (response.ok) {
        const data = await response.json();
        assistantMessage = {
          role: 'assistant',
          content: data.reply || getUnconnectedModelNotice(detectedLang),
          reference: data.reference || null,
          disclaimer: data.disclaimer || SHORT_DISCLAIMER,
        };
      } else {
        assistantMessage = {
          role: 'assistant',
          content: getUnconnectedModelNotice(detectedLang),
          reference: null,
          disclaimer: SHORT_DISCLAIMER,
        };
      }
    } catch {
      assistantMessage = {
        role: 'assistant',
        content: getUnconnectedModelNotice(detectedLang),
        reference: null,
        disclaimer: SHORT_DISCLAIMER,
      };
    } finally {
      setIsLoading(false);
    }

    shouldAutoScrollRef.current = true;
    setMessages((prev) => {
      const updated = [...prev, assistantMessage];
      setRecentChats((chats) => {
        const updatedChats = chats.map((c) =>
          c.id === activeId ? { ...c, messages: updated } : c
        );
        if (currentAccountKey) {
          writeStoredAccountChats(currentAccountKey, updatedChats);
        }
        return updatedChats;
      });
      return updated;
    });
  };

  const handleNewChat = () => {
    shouldAutoScrollRef.current = true;
    setMessages([]);
    setCurrentChatId(null);
  };

  const handleSelectChat = (chat) => {
    shouldAutoScrollRef.current = true;
    setCurrentChatId(chat.id);
    setMessages(chat.messages || []);
    requestAnimationFrame(() => scrollToBottom('auto'));
  };

  const handleDeleteChat = (chatId) => {
    setRecentChats((prev) => {
      const filtered = prev.filter((c) => c.id !== chatId);
      if (storageKey) {
        writeStoredAccountChats(storageKey, filtered);
      }
      return filtered;
    });
    if (currentChatId === chatId) {
      handleNewChat();
    }
  };

  const handleRenameChat = (chatId, newTitle) => {
    setRecentChats((prev) => {
      const updated = prev.map((c) =>
        c.id === chatId ? { ...c, title: newTitle } : c
      );
      if (storageKey) {
        writeStoredAccountChats(storageKey, updated);
      }
      return updated;
    });
  };

  const handlePinChat = (chatId) => {
    setRecentChats((prev) => {
      const updated = prev.map((c) =>
        c.id === chatId ? { ...c, pinned: !c.pinned } : c
      );

      const sorted = updated.sort((a, b) => {
        if (a.pinned !== b.pinned) {
          return b.pinned ? 1 : -1;
        }
        return (b.createdAt || b.id) - (a.createdAt || a.id);
      });

      if (storageKey) {
        writeStoredAccountChats(storageKey, sorted);
      }
      return sorted;
    });
  };

  return (
    <div className={`flex h-screen overflow-hidden transition-colors duration-300 ${
      isDark ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-900'
    } ${lang === 'ur' ? 'font-sans' : ''}`}>

      {/* Sidebar Component */}
      <Sidebar
        user={effectiveUser}
        onLogout={handleLogoutAction}
        isOpen={isSidebarOpen}
        setIsOpen={setIsSidebarOpen}
        onNewChat={handleNewChat}
        recentChats={recentChats}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onPinChat={handlePinChat}
      />

      {/* Main Chat Content */}
      <div className="flex-1 flex flex-col justify-between h-screen min-w-0 overflow-hidden">

        {/* Header */}
        <header className={`p-4 border-b flex justify-between items-center px-6 transition-colors ${
          isDark
            ? 'bg-slate-800/80 border-slate-700/80'
            : 'bg-white/80 border-slate-200 shadow-sm'
        }`}>
          <h1 className={`text-lg font-bold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
            {t('appTitle')}
          </h1>

          {!effectiveUser && (
            <button
              onClick={() => navigate('/login')}
              className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 text-amber-500 px-3 py-1.5 rounded-lg text-xs hover:bg-amber-500/20 transition-all cursor-pointer"
            >
              <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
              <span>{t('notLoggedInWarning')}</span>
            </button>
          )}
        </header>

        {/* Chat Messages */}
        <main
          ref={chatContainerRef}
          onScroll={handleChatScroll}
          style={{ scrollbarGutter: 'stable' }}
          className="flex-1 w-full px-4 py-6 sm:px-6 overflow-y-scroll scroll-smooth"
        >
          <div className="max-w-4xl w-full mx-auto flex flex-col gap-6">
            {messages.length === 0 ? (
              <div className={`text-center mt-20 text-sm ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                {t('typeQueryPrompt')}
              </div>
            ) : (
              messages.map((m, idx) =>
                m.role === 'user' ? (
                  <div
                    key={idx}
                    className={`self-end p-4 rounded-xl max-w-2xl w-fit text-sm leading-relaxed whitespace-pre-line ${
                      isDark
                        ? 'bg-emerald-500/10 text-emerald-200 border border-emerald-500/20'
                        : 'bg-emerald-50 text-emerald-900 border border-emerald-300 shadow-sm'
                    }`}
                  >
                    <div>{m.content}</div>
                  </div>
                ) : (
                  <div
                    key={idx}
                    className={`w-full py-1 text-sm sm:text-[15px] leading-7 whitespace-pre-line text-left ${
                      isDark ? 'text-slate-100' : 'text-slate-800'
                    }`}
                  >
                    <div>{m.content}</div>
                    <BookAnswerNote reference={m.reference} disclaimer={m.disclaimer} />
                  </div>
                )
              )
            )}
            {isLoading && (
              <div className={`w-full py-1 text-sm animate-pulse text-left ${
                isDark ? 'text-slate-400' : 'text-slate-500'
              }`}>
                {t('connectingServer')}
              </div>
            )}
          </div>
        </main>

        {/* Chat Input Bar */}
        <footer className={`p-4 border-t transition-colors ${
          isDark
            ? 'bg-slate-800/80 border-slate-700/80'
            : 'bg-white/80 border-slate-200 shadow-sm'
        }`}>
          <form onSubmit={handleSend} className="max-w-4xl w-full mx-auto flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={effectiveUser ? t('askQuestion') : t('loginRequired')}
              className={`flex-1 rounded-lg px-4 py-2.5 text-sm border focus:outline-none focus:border-emerald-500 transition-colors ${
                isDark
                  ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500'
                  : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
              }`}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading}
              className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-5 py-2.5 rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer text-sm disabled:opacity-50"
            >
              <Send className="w-4 h-4" /> {t('send')}
            </button>
          </form>
        </footer>

      </div>
    </div>
  );
}
