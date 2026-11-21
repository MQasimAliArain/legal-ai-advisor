import { createContext, useContext, useState, useEffect } from 'react';

const LanguageContext = createContext();

const translations = {
  en: {
    appTitle: 'Legal AI',
    pkEdition: 'PK Edition',
    chatTab: 'Chat Consultation',
    settings: 'Settings',
    logout: 'Log out',
    login: 'Login / Signup',
    askQuestion: 'Ask a legal question...',
    loginRequired: 'Login required to send questions...',
    send: 'Send',
    notLoggedInWarning: 'You are not logged in. Login / Signup to ask questions.',
    typeQueryPrompt: 'Type your legal query below to get started.',
    recents: 'Recents',
    newChat: 'New Chat',
    connectingServer: 'Connecting to legal server...',
  },
  ur: {
    appTitle: 'قانونی اے آئی',
    pkEdition: 'پاکستان ایڈیشن',
    chatTab: 'قانونی گفتگو',
    settings: 'ترتیبات',
    logout: 'لاگ آؤٹ',
    login: 'لاگ ان / سائن اپ',
    askQuestion: 'اپنا قانونی سوال ٹائپ کریں...',
    loginRequired: 'سوال پوچھنے کے لیے لاگ ان کریں...',
    send: 'بھیجیں',
    notLoggedInWarning: 'آپ لاگ ان نہیں ہیں۔ سوالات پوچھنے کے لیے لاگ ان / سائن اپ کریں۔',
    typeQueryPrompt: 'شروع کرنے کے لیے ذیل میں اپنا قانونی سوال لکھیں۔',
    recents: 'حالیہ گفتگو',
    newChat: 'نئی گفتگو',
    connectingServer: 'قانونی سرور سے منسلک ہو رہا ہے...',
  }
};

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => {
    return localStorage.getItem('app-language') || 'en';
  });

  useEffect(() => {
    localStorage.setItem('app-language', lang);
  }, [lang]);

  const setLanguage = (newLang) => {
    setLang(newLang);
  };

  const t = (key) => {
    return translations[lang]?.[key] || key;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, language: lang, setLanguage, changeLanguage: setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}