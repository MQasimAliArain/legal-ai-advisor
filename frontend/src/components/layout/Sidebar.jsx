import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Gavel, 
  MessageSquare, 
  Settings, 
  LogOut, 
  PanelLeftClose, 
  PanelLeft, 
  User,
  Plus,
  AlertCircle,
  MoreVertical,
  Pin,
  Edit2,
  Share2,
  Trash2,
  Check,
  Copy,
  X,
  Globe,
  Sun,
  Moon,
  Shield,
  FileText
} from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';
import { useTheme } from '../../context/ThemeContext';

export default function Sidebar({ 
  user, 
  onLogout, 
  isOpen, 
  setIsOpen, 
  onNewChat,
  recentChats = [],
  onSelectChat,
  onDeleteChat,
  onRenameChat,
  onPinChat
}) {
  const { t, lang, setLanguage } = useLanguage();
  const { theme, setTheme, isDark } = useTheme();

  const navigate = useNavigate();
  const [showLogoutModal, setShowLogoutModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [activeSettingsTab, setActiveSettingsTab] = useState('language'); // language, theme, privacy, terms

  const [chatToDelete, setChatToDelete] = useState(null);
  const [shareChat, setShareChat] = useState(null);
  
  // Menu positioning state
  const [activeMenu, setActiveMenu] = useState(null); // { id, top, left }
  const [editingChatId, setEditingChatId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [toastMessage, setToastMessage] = useState('');

  const menuRef = useRef(null);

  // Close popup menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setActiveMenu(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const confirmLogout = () => {
    setShowLogoutModal(false);
    if (onLogout) {
      onLogout();
      navigate('/');
    }
  };

  const handleOpenSettings = () => {
    setShowSettingsModal(true);
  };

  const handleOpenMenu = (e, chatId) => {
    e.stopPropagation();
    if (activeMenu?.id === chatId) {
      setActiveMenu(null);
      return;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    setActiveMenu({
      id: chatId,
      top: rect.bottom + 4,
      left: Math.min(rect.left, window.innerWidth - 160)
    });
  };

  const handleTogglePin = (chat) => {
    if (onPinChat) {
      onPinChat(chat.id);
    }
    setActiveMenu(null);
    if (lang === 'ur') {
      setToastMessage(chat.pinned ? 'گفتگو ان پن کر دی گئی' : 'گفتگو اوپر پن کر دی گئی');
    } else {
      setToastMessage(chat.pinned ? 'Chat unpinned' : 'Chat pinned to top');
    }
    setTimeout(() => setToastMessage(''), 2200);
  };

  const handleShareClick = (chat) => {
    setShareChat(chat);
    setActiveMenu(null);
  };

  const getShareUrl = () => {
    return `${window.location.origin}/chat/${shareChat?.id || ''}`;
  };

  const handleCopyShareLink = () => {
    navigator.clipboard.writeText(getShareUrl());
    setToastMessage(lang === 'ur' ? 'لنک کاپی ہو گیا!' : 'Link copied to clipboard!');
    setTimeout(() => setToastMessage(''), 2200);
  };

  const handleSaveRename = (chatId) => {
    if (editTitle.trim()) {
      onRenameChat(chatId, editTitle.trim());
      setToastMessage(lang === 'ur' ? 'گفتگو کا نام تبدیل ہو گیا' : 'Chat renamed');
      setTimeout(() => setToastMessage(''), 2200);
    }
    setEditingChatId(null);
  };

  const confirmDeleteChat = () => {
    if (chatToDelete) {
      onDeleteChat(chatToDelete.id);
      setToastMessage(lang === 'ur' ? 'گفتگو حذف کر دی گئی' : 'Chat deleted');
      setTimeout(() => setToastMessage(''), 2200);
    }
    setChatToDelete(null);
  };

  const handleLanguageSelect = (selectedLang) => {
    setLanguage(selectedLang);
    setToastMessage(selectedLang === 'ur' ? 'زبان تبدیل ہو گئی' : 'Language changed to English');
    setTimeout(() => setToastMessage(''), 2200);
  };

  // Separate pinned and unpinned chats
  const pinnedChats = recentChats.filter((c) => c.pinned);
  const unpinnedChats = recentChats.filter((c) => !c.pinned);

  // Reusable Chat Item Component
  const renderChatItem = (chat) => (
    <div key={chat.id} className="relative group">
      {editingChatId === chat.id && isOpen ? (
        <div className="flex items-center gap-1 p-1">
          <input
            type="text"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSaveRename(chat.id)}
            className={`border text-xs px-2 py-1 rounded w-full focus:outline-none ${
              isDark 
                ? 'bg-slate-950 border-emerald-500 text-white' 
                : 'bg-white border-emerald-500 text-slate-900'
            }`}
            autoFocus
          />
          <button
            onClick={() => handleSaveRename(chat.id)}
            className="p-1 bg-emerald-500 text-slate-950 rounded hover:bg-emerald-600 cursor-pointer"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div 
          className={`flex items-center justify-between w-full rounded-lg transition-colors text-xs cursor-pointer ${
            isOpen ? 'px-2 py-1.5' : 'px-1 py-1.5 justify-center'
          } ${
            isDark 
              ? 'text-slate-300 hover:bg-slate-800/80' 
              : 'text-slate-700 hover:bg-slate-200/70'
          }`}
        >
          <button
            onClick={() => onSelectChat(chat)}
            className={`flex items-center truncate cursor-pointer ${
              isOpen ? 'gap-2.5 flex-1 text-left' : 'justify-center w-8 h-8'
            }`}
            title={chat.title}
          >
            <MessageSquare className={`w-4 h-4 shrink-0 ${
              isDark ? 'text-slate-400 group-hover:text-emerald-400' : 'text-slate-500 group-hover:text-emerald-600'
            }`} />
            {isOpen && (
              <span className="truncate flex-1 font-medium">
                {chat.title}
              </span>
            )}
            {chat.pinned && isOpen && (
              <Pin className="w-3 h-3 text-emerald-400 fill-emerald-400 shrink-0 ml-1" />
            )}
          </button>

          {/* Three Dots Action Button */}
          {isOpen && (
            <button
              onClick={(e) => handleOpenMenu(e, chat.id)}
              className={`p-1 rounded transition cursor-pointer ml-1 ${
                isDark 
                  ? 'hover:bg-slate-700/60 text-slate-400 hover:text-white' 
                  : 'hover:bg-slate-300/60 text-slate-500 hover:text-slate-900'
              }`}
            >
              <MoreVertical className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Toast Notification Banner */}
      {toastMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
          <div className={`border font-bold text-sm px-6 py-3.5 rounded-2xl shadow-2xl flex items-center gap-3 backdrop-blur-md animate-in fade-in zoom-in-95 duration-150 ${
            isDark 
              ? 'bg-slate-900/95 border-emerald-500/50 text-white' 
              : 'bg-white/95 border-emerald-500 text-slate-900 shadow-emerald-500/10'
          }`}>
            <div className="w-7 h-7 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center border border-emerald-500/40">
              <Check className="w-4 h-4 stroke-3" />
            </div>
            <span>{toastMessage}</span>
          </div>
        </div>
      )}

      <aside 
        className={`border-r flex flex-col justify-between h-dvh shrink-0 transition-all duration-200 fixed inset-y-0 left-0 z-40 md:static md:translate-x-0 ${
          isOpen
            ? 'translate-x-0 w-64 max-w-[82vw] p-3.5'
            : '-translate-x-full w-64 md:translate-x-0 md:w-[68px] py-3.5 px-2'
        } ${
          isDark 
            ? 'bg-slate-900 border-slate-800 text-slate-200' 
            : 'bg-slate-50 border-slate-200 text-slate-800'
        }`}
      >
        <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
          {/* Brand & Toggle Button */}
          {isOpen ? (
            <div className="flex items-center justify-between gap-2 mb-4 shrink-0">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-9 h-9 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg flex items-center justify-center shrink-0">
                  <Gavel className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <h1 className={`text-base font-bold leading-tight truncate ${isDark ? 'text-white' : 'text-slate-900'}`}>{t('appTitle')}</h1>
                  <p className="text-[10px] text-emerald-500 font-medium leading-tight truncate">{t('pkEdition')}</p>
                </div>
              </div>

              <button
                onClick={() => setIsOpen(!isOpen)}
                className={`p-1.5 rounded-lg transition-colors cursor-pointer shrink-0 ${
                  isDark 
                    ? 'hover:bg-slate-800 text-slate-400 hover:text-white' 
                    : 'hover:bg-slate-200 text-slate-600 hover:text-slate-900'
                }`}
                title="Collapse Sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 mb-4 shrink-0">
              <div className="w-9 h-9 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg flex items-center justify-center">
                <Gavel className="w-4 h-4" />
              </div>
              <button
                onClick={() => setIsOpen(!isOpen)}
                className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors cursor-pointer ${
                  isDark 
                    ? 'hover:bg-slate-800 text-slate-400 hover:text-white' 
                    : 'hover:bg-slate-200 text-slate-600 hover:text-slate-900'
                }`}
                title="Expand Sidebar"
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* New Chat Button */}
          <button
            onClick={onNewChat}
            title={!isOpen ? t('newChat') : undefined}
            className={`flex items-center justify-center bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-semibold transition-all cursor-pointer mb-4 shrink-0 ${
              isOpen ? 'w-full gap-2 py-2 px-3 rounded-lg text-xs' : 'w-9 h-9 mx-auto rounded-lg'
            }`}
          >
            <Plus className="w-4 h-4 shrink-0 stroke-[2.5]" />
            {isOpen && <span>{t('newChat')}</span>}
          </button>

          {/* Chat List Container */}
          <div className="space-y-2.5 mb-3 flex-1 min-h-0 overflow-y-auto">
            {/* Pinned Section */}
            {pinnedChats.length > 0 && (
              <div className="space-y-0.5">
                {isOpen && (
                  <p className="text-[10px] font-semibold text-emerald-500 px-2 py-1 uppercase tracking-wider flex items-center gap-1">
                    <Pin className="w-3 h-3 fill-emerald-500" />
                    {lang === 'ur' ? 'پن شدہ' : 'Pinned'}
                  </p>
                )}
                {pinnedChats.map(renderChatItem)}
              </div>
            )}

            {/* Recents Section */}
            <div className="space-y-0.5">
              {isOpen && recentChats.length > 0 && (
                <p className={`text-[10px] font-semibold px-2 py-1 uppercase tracking-wider ${
                  isDark ? 'text-slate-500' : 'text-slate-400'
                }`}>
                  {t('recents')}
                </p>
              )}
              {unpinnedChats.map(renderChatItem)}
            </div>
          </div>
        </div>

        {/* Footer Actions: Settings & Profile */}
        <div className={`pt-2.5 pb-12 md:pb-1 border-t space-y-1.5 shrink-0 ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
          {/* Settings option - always accessible whether logged in or not */}
          <button 
            onClick={handleOpenSettings}
            title={!isOpen ? t('settings') : undefined}
            className={`flex items-center transition rounded-lg text-xs font-medium cursor-pointer ${
              isOpen ? 'w-full gap-2.5 px-2 py-1.5' : 'w-9 h-9 mx-auto justify-center'
            } ${
              isDark 
                ? 'text-slate-400 hover:text-white hover:bg-slate-800/60' 
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
            }`}
          >
            <Settings className="w-4 h-4 shrink-0" />
            {isOpen && <span>{t('settings')}</span>}
          </button>

          {/* Profile / Login Block */}
          {user ? (
            isOpen ? (
              <div className={`flex items-center justify-between px-2 py-1.5 rounded-lg border ${
                isDark ? 'bg-slate-950/80 border-slate-800' : 'bg-white border-slate-200'
              }`}>
                {(() => {
                  const displayName = user.user_metadata?.username || user.name || user.email?.split('@')[0] || 'User';
                  return (
                    <div className="flex items-center gap-2 overflow-hidden min-w-0">
                      <div className="w-7 h-7 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center font-bold text-emerald-400 text-xs shrink-0">
                        {displayName[0].toUpperCase()}
                      </div>
                      <div className="truncate min-w-0">
                        <p className={`text-xs font-semibold leading-tight truncate ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>
                          {displayName}
                        </p>
                        <p className={`text-[10px] leading-tight truncate ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                          {user.email}
                        </p>
                      </div>
                    </div>
                  );
                })()}

                <button
                  onClick={() => setShowLogoutModal(true)}
                  className={`p-1 rounded transition-colors cursor-pointer ml-1 shrink-0 ${
                    isDark 
                      ? 'hover:bg-slate-800 text-slate-400 hover:text-red-400' 
                      : 'hover:bg-slate-100 text-slate-500 hover:text-red-500'
                  }`}
                  title={t('logout')}
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="flex justify-center pt-0.5">
                {(() => {
                  const displayName = user.user_metadata?.username || user.name || user.email?.split('@')[0] || 'User';
                  return (
                    <button
                      type="button"
                      onClick={() => setShowLogoutModal(true)}
                      title={`${displayName} (${t('logout')})`}
                      className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center font-bold text-emerald-400 text-xs cursor-pointer hover:bg-emerald-500/30 transition-colors"
                    >
                      {displayName[0].toUpperCase()}
                    </button>
                  );
                })()}
              </div>
            )
          ) : (
            <button
              onClick={() => navigate('/login')}
              title={!isOpen ? t('login') : undefined}
              className={`flex items-center justify-center bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 hover:bg-emerald-500/20 rounded-lg text-xs font-medium cursor-pointer transition-colors ${
                isOpen ? 'w-full gap-2 py-1.5 px-2' : 'w-9 h-9 mx-auto'
              }`}
            >
              <User className="w-4 h-4 shrink-0" />
              {isOpen && <span>{t('login')}</span>}
            </button>
          )}
        </div>
      </aside>

      {/* Floating Context Menu */}
      {activeMenu && (
        <div
          ref={menuRef}
          style={{ top: `${activeMenu.top}px`, left: `${activeMenu.left}px` }}
          className={`fixed z-50 border rounded-lg shadow-2xl p-1 w-36 text-xs ${
            isDark 
              ? 'bg-slate-950 border-slate-800 text-slate-300' 
              : 'bg-white border-slate-200 text-slate-700 shadow-slate-300'
          }`}
        >
          {(() => {
            const chat = recentChats.find((c) => c.id === activeMenu.id);
            if (!chat) return null;

            return (
              <>
                <button
                  onClick={() => handleTogglePin(chat)}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left transition cursor-pointer ${
                    isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-100'
                  }`}
                >
                  <Pin className="w-3.5 h-3.5 text-slate-400" />
                  {chat.pinned
                    ? (lang === 'ur' ? 'ان پن کریں' : 'Unpin')
                    : (lang === 'ur' ? 'پن کریں' : 'Pin')}
                </button>

                <button
                  onClick={() => {
                    setEditingChatId(chat.id);
                    setEditTitle(chat.title);
                    setActiveMenu(null);
                  }}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left transition cursor-pointer ${
                    isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-100'
                  }`}
                >
                  <Edit2 className="w-3.5 h-3.5 text-slate-400" />
                  {lang === 'ur' ? 'نام تبدیل کریں' : 'Rename'}
                </button>

                <button
                  onClick={() => handleShareClick(chat)}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-left transition cursor-pointer ${
                    isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-100'
                  }`}
                >
                  <Share2 className="w-3.5 h-3.5 text-slate-400" />
                  {lang === 'ur' ? 'شیئر کریں' : 'Share'}
                </button>

                <button
                  onClick={() => {
                    setChatToDelete(chat);
                    setActiveMenu(null);
                  }}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 hover:bg-red-500/10 text-red-400 hover:text-red-300 rounded text-left transition cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  {lang === 'ur' ? 'حذف کریں' : 'Delete'}
                </button>
              </>
            );
          })()}
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div
          onClick={() => setShowSettingsModal(false)}
          className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className={`border rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden flex flex-col md:flex-row md:h-[520px] relative ${
              isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}
          >
            <button
              onClick={() => setShowSettingsModal(false)}
              className={`absolute top-4 right-4 p-1.5 rounded-lg transition cursor-pointer z-10 ${
                isDark ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <X className="w-5 h-5" />
            </button>

            {/* Modal Left Sidebar */}
            <div className={`w-full md:w-56 p-4 border-b md:border-b-0 md:border-r flex flex-col space-y-1 shrink-0 ${
              isDark ? 'bg-slate-950/50 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex items-center gap-2 px-3 py-2 mb-2">
                <Settings className="w-5 h-5 text-emerald-500" />
                <h2 className="font-bold text-sm uppercase tracking-wider">{t('settings')}</h2>
              </div>

              <button
                onClick={() => setActiveSettingsTab('language')}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition cursor-pointer text-left ${
                  activeSettingsTab === 'language'
                    ? 'bg-emerald-500 text-slate-950'
                    : isDark ? 'text-slate-300 hover:bg-slate-800' : 'text-slate-700 hover:bg-slate-200'
                }`}
              >
                <Globe className="w-4 h-4 shrink-0" />
                {lang === 'ur' ? 'زبان' : 'Language'}
              </button>

              <button
                onClick={() => setActiveSettingsTab('theme')}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition cursor-pointer text-left ${
                  activeSettingsTab === 'theme'
                    ? 'bg-emerald-500 text-slate-950'
                    : isDark ? 'text-slate-300 hover:bg-slate-800' : 'text-slate-700 hover:bg-slate-200'
                }`}
              >
                {theme === 'dark' ? <Moon className="w-4 h-4 shrink-0" /> : <Sun className="w-4 h-4 shrink-0" />}
                {lang === 'ur' ? 'تھیم' : 'Theme'}
              </button>

              <button
                onClick={() => setActiveSettingsTab('privacy')}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition cursor-pointer text-left ${
                  activeSettingsTab === 'privacy'
                    ? 'bg-emerald-500 text-slate-950'
                    : isDark ? 'text-slate-300 hover:bg-slate-800' : 'text-slate-700 hover:bg-slate-200'
                }`}
              >
                <Shield className="w-4 h-4 shrink-0" />
                {lang === 'ur' ? 'ڈیٹا اور رازداری' : 'Data & Privacy'}
              </button>

              <button
                onClick={() => setActiveSettingsTab('terms')}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition cursor-pointer text-left ${
                  activeSettingsTab === 'terms'
                    ? 'bg-emerald-500 text-slate-950'
                    : isDark ? 'text-slate-300 hover:bg-slate-800' : 'text-slate-700 hover:bg-slate-200'
                }`}
              >
                <FileText className="w-4 h-4 shrink-0" />
                {lang === 'ur' ? 'شرائط و ضوابط' : 'Terms & Conditions'}
              </button>
            </div>

            {/* Modal Right Content Body */}
            <div className="flex-1 p-6 overflow-y-auto">
              {/* Language Tab */}
              {activeSettingsTab === 'language' && (
                <div className="space-y-5">
                  <h3 className="text-base font-bold flex items-center gap-2 border-b pb-3 border-slate-700/50">
                    <Globe className="w-5 h-5 text-emerald-500" /> {lang === 'ur' ? 'انٹرفیس کی زبان' : 'Interface Language'}
                  </h3>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    {lang === 'ur'
                      ? 'قانونی اے آئی اسسٹنٹ انٹرفیس کے لیے اپنی پسندیدہ زبان منتخب کریں۔'
                      : 'Choose your preferred language for the legal AI assistant interface.'}
                  </p>

                  <div className="space-y-3 pt-1">
                    <button
                      onClick={() => handleLanguageSelect('en')}
                      className={`w-full flex items-center justify-between p-3.5 rounded-xl border transition cursor-pointer ${
                        lang === 'en'
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500 font-bold'
                          : isDark ? 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700' : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-bold">🇺🇸</span>
                        <div className="text-left">
                          <p className="text-xs font-semibold">English</p>
                          <p className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>Standard English Interface</p>
                        </div>
                      </div>
                      {lang === 'en' && <Check className="w-4 h-4 text-emerald-500" />}
                    </button>

                    <button
                      onClick={() => handleLanguageSelect('ur')}
                      className={`w-full flex items-center justify-between p-3.5 rounded-xl border transition cursor-pointer ${
                        lang === 'ur'
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500 font-bold'
                          : isDark ? 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700' : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-bold">🇵🇰</span>
                        <div className="text-left">
                          <p className="text-xs font-semibold">اردو (Urdu)</p>
                          <p className={`text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>پاکستانی وکیل ایڈیشن</p>
                        </div>
                      </div>
                      {lang === 'ur' && <Check className="w-4 h-4 text-emerald-500" />}
                    </button>
                  </div>
                </div>
              )}

              {/* Theme Tab */}
              {activeSettingsTab === 'theme' && (
                <div className="space-y-5">
                  <h3 className="text-base font-bold flex items-center gap-2 border-b pb-3 border-slate-700/50">
                    {theme === 'dark' ? <Moon className="w-5 h-5 text-emerald-500" /> : <Sun className="w-5 h-5 text-emerald-500" />} {lang === 'ur' ? 'ظاہری شکل اور تھیم' : 'Appearance & Theme'}
                  </h3>
                  <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
                    {lang === 'ur'
                      ? 'پورے ایپلیکیشن کے لیے اپنی پسندیدہ تھیم منتخب کریں۔'
                      : 'Select your preferred interface theme for the entire application.'}
                  </p>

                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <button
                      onClick={() => setTheme('dark')}
                      className={`p-4 rounded-xl border flex flex-col items-center gap-3 transition cursor-pointer ${
                        theme === 'dark'
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-400 font-bold'
                          : isDark ? 'border-slate-800 bg-slate-950 text-slate-400' : 'border-slate-200 bg-slate-100 text-slate-600'
                      }`}
                    >
                      <Moon className="w-6 h-6" />
                      <span className="text-xs">{lang === 'ur' ? 'ڈارک تھیم' : 'Dark Theme'}</span>
                    </button>

                    <button
                      onClick={() => setTheme('light')}
                      className={`p-4 rounded-xl border flex flex-col items-center gap-3 transition cursor-pointer ${
                        theme === 'light'
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-600 font-bold'
                          : isDark ? 'border-slate-800 bg-slate-950 text-slate-400' : 'border-slate-200 bg-slate-100 text-slate-600'
                      }`}
                    >
                      <Sun className="w-6 h-6" />
                      <span className="text-xs">{lang === 'ur' ? 'لائٹ تھیم' : 'Light Theme'}</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Data & Privacy Tab */}
              {activeSettingsTab === 'privacy' && (
                <div className="space-y-4">
                  <h3 className="text-base font-bold flex items-center gap-2 border-b pb-3 border-slate-700/50">
                    <Shield className="w-5 h-5 text-emerald-500" /> {lang === 'ur' ? 'ڈیٹا اور رازداری کی پالیسی' : 'Data & Privacy Policy'}
                  </h3>

                  <div className={`text-xs leading-relaxed space-y-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                    <p>
                      <strong>1. {lang === 'ur' ? 'رازداریت:' : 'Confidentiality:'}</strong> {lang === 'ur'
                        ? 'تمام قانونی سوالات، کیس اپ لوڈز اور سیاق و سباق کا ڈیٹا محفوظ پروٹوکولز کے تحت انکرپٹڈ ہے۔'
                        : 'All legal queries, case uploads, and context inputs are encrypted using enterprise-grade protocols.'}
                    </p>
                    <p>
                      <strong>2. {lang === 'ur' ? 'ماڈل ٹریننگ کا تحفظ:' : 'Model Training Protection:'}</strong> {lang === 'ur'
                        ? 'آپ کے نجی قانونی دستاویزات اور کلائنٹ ڈیٹا کو عوامی اے آئی ماڈلز کی تربیت کے لیے استعمال نہیں کیا جاتا۔'
                        : 'Your private legal documents and client data are never used to train public AI models.'}
                    </p>
                    <p>
                      <strong>3. {lang === 'ur' ? 'ڈیٹا کنٹرول:' : 'Data Control:'}</strong> {lang === 'ur'
                        ? 'آپ اپنی چیٹ ہسٹری کے مکمل مالک ہیں اور کسی بھی وقت سائیڈ بار سے انفرادی چیٹس حذف کر سکتے ہیں۔'
                        : 'You retain full ownership of your chat history. You can clear or delete individual chats at any time directly from the sidebar.'}
                    </p>
                  </div>
                </div>
              )}

              {/* Terms & Conditions Tab */}
              {activeSettingsTab === 'terms' && (
                <div className="space-y-4">
                  <h3 className="text-base font-bold flex items-center gap-2 border-b pb-3 border-slate-700/50">
                    <FileText className="w-5 h-5 text-emerald-500" /> {lang === 'ur' ? 'شرائط و ضوابط' : 'Terms & Conditions'}
                  </h3>

                  <div className={`text-xs leading-relaxed space-y-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                    <p>
                      <strong>1. {lang === 'ur' ? 'قانونی معلومات کی وضاحت:' : 'Legal Information Disclaimer:'}</strong> {lang === 'ur'
                        ? 'لیگل اے آئی کے فراہم کردہ جوابات صرف تحقیق اور معلومات کے لیے ہیں اور باضابطہ قانونی مشورہ نہیں ہیں۔'
                        : 'Answers provided by Legal AI are for research and informational reference only and do not constitute formal legal counsel.'}
                    </p>
                    <p>
                      <strong>2. {lang === 'ur' ? 'پیشہ ورانہ تصدیق:' : 'Professional Verification:'}</strong> {lang === 'ur'
                        ? 'وکلاء اور قانونی ماہرین عدالت میں دائر کرنے سے قبل قانونی حوالوں اور عدالتی نظائر کی خود تصدیق کریں۔'
                        : 'Advocates and legal practitioners must independently verify statutory citations and judicial precedents before filing in court.'}
                    </p>
                    <p>
                      <strong>3. {lang === 'ur' ? 'قابل قبول استعمال:' : 'Acceptable Use:'}</strong> {lang === 'ur'
                        ? 'صارفین ڈیجیٹل ٹولز اور ڈیٹا پرائیویسی سے متعلق مقامی قوانین کی پابندی کرنے کے پابند ہیں۔'
                        : 'Users agree to comply with applicable local laws and regulations governing digital tools and data privacy.'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Share Modal */}
      {shareChat && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`border rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-5 relative ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <button
              onClick={() => setShareChat(null)}
              className={`absolute top-4 right-4 p-1 rounded-lg transition cursor-pointer ${
                isDark ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
                <Share2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold">{lang === 'ur' ? 'قانونی سوال شیئر کریں' : 'Share Legal Query'}</h3>
                <p className={`text-xs truncate max-w-[280px] ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>"{shareChat.title}"</p>
              </div>
            </div>

            {/* Social Share Buttons */}
            <div className="grid grid-cols-3 gap-3 pt-1">
              <a
                href={`https://api.whatsapp.com/send?text=${encodeURIComponent(`Check out my legal query: "${shareChat.title}" - ${getShareUrl()}`)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex flex-col items-center justify-center gap-2 p-3 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-500 transition cursor-pointer group"
              >
                <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="text-sm font-bold">WA</span>
                </div>
                <span className="text-xs font-semibold">WhatsApp</span>
              </a>

              <a
                href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(getShareUrl())}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex flex-col items-center justify-center gap-2 p-3 rounded-xl bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 text-blue-500 transition cursor-pointer group"
              >
                <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="text-sm font-bold">in</span>
                </div>
                <span className="text-xs font-semibold">LinkedIn</span>
              </a>

              <a
                href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(getShareUrl())}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex flex-col items-center justify-center gap-2 p-3 rounded-xl bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-indigo-500 transition cursor-pointer group"
              >
                <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="text-sm font-bold">f</span>
                </div>
                <span className="text-xs font-semibold">Facebook</span>
              </a>
            </div>

            {/* Copy Link Input Section */}
            <div className="space-y-1.5 pt-2">
              <label className={`text-[11px] font-semibold uppercase tracking-wider ${
                isDark ? 'text-slate-400' : 'text-slate-500'
              }`}>
                {lang === 'ur' ? 'یا لنک کاپی کریں' : 'Or copy link'}
              </label>
              <div className={`flex items-center gap-2 border rounded-xl p-1.5 ${
                isDark ? 'bg-slate-950 border-slate-800' : 'bg-slate-50 border-slate-200'
              }`}>
                <input
                  type="text"
                  readOnly
                  value={getShareUrl()}
                  className={`bg-transparent text-xs px-2 w-full focus:outline-none truncate ${
                    isDark ? 'text-slate-300' : 'text-slate-700'
                  }`}
                />
                <button
                  onClick={handleCopyShareLink}
                  className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-3 py-1.5 rounded-lg text-xs transition shrink-0 cursor-pointer"
                >
                  <Copy className="w-3.5 h-3.5" />
                  {lang === 'ur' ? 'کاپی' : 'Copy'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {chatToDelete && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`border rounded-2xl p-6 max-w-sm w-full shadow-2xl text-center space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 text-red-500 flex items-center justify-center mx-auto">
              <Trash2 className="w-6 h-6" />
            </div>
            
            <h3 className="text-lg font-bold">{lang === 'ur' ? 'گفتگو حذف کریں؟' : 'Delete Chat?'}</h3>
            <p className={`text-xs leading-relaxed ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
              {lang === 'ur' ? (
                <>کیا آپ واقعی <span className="font-semibold text-emerald-500">"{chatToDelete.title}"</span> کو حذف کرنا چاہتے ہیں؟ یہ عمل واپس نہیں ہو سکتا۔</>
              ) : (
                <>Are you sure you want to delete <span className="font-semibold text-emerald-500">"{chatToDelete.title}"</span>? This action cannot be undone.</>
              )}
            </p>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setChatToDelete(null)}
                className={`flex-1 py-2 px-4 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  isDark ? 'bg-slate-800 hover:bg-slate-700 text-slate-200' : 'bg-slate-200 hover:bg-slate-300 text-slate-700'
                }`}
              >
                {lang === 'ur' ? 'منسوخ کریں' : 'Cancel'}
              </button>
              <button
                onClick={confirmDeleteChat}
                className="flex-1 py-2 px-4 bg-red-500 hover:bg-red-600 text-white rounded-lg text-xs font-semibold transition cursor-pointer"
              >
                {lang === 'ur' ? 'حذف کریں' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Log Out Confirmation Modal */}
      {showLogoutModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className={`border rounded-2xl p-6 max-w-sm w-full shadow-2xl text-center space-y-4 ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 text-red-500 flex items-center justify-center mx-auto">
              <AlertCircle className="w-6 h-6" />
            </div>
            
            <h3 className="text-lg font-bold">{lang === 'ur' ? 'لاگ آؤٹ کی تصدیق' : 'Log Out Confirmation'}</h3>
            <p className={`text-xs leading-relaxed ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
              {lang === 'ur' ? 'کیا آپ واقعی اپنا موجودہ سیشن ختم کرنا چاہتے ہیں؟' : 'Are you sure you want to exit your current session?'}
            </p>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setShowLogoutModal(false)}
                className={`flex-1 py-2 px-4 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  isDark ? 'bg-slate-800 hover:bg-slate-700 text-slate-200' : 'bg-slate-200 hover:bg-slate-300 text-slate-700'
                }`}
              >
                {lang === 'ur' ? 'منسوخ کریں' : 'Cancel'}
              </button>
              <button
                onClick={confirmLogout}
                className="flex-1 py-2 px-4 bg-red-500 hover:bg-red-600 text-white rounded-lg text-xs font-semibold transition cursor-pointer"
              >
                {t('logout')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
