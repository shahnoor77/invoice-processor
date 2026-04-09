import { useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Bell, Sun, Moon } from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';

const titles: Record<string, string> = {
  '/settings': 'Settings',
  '/invoices': 'Invoice Processing',
};

const getTitle = (pathname: string) => {
  if (pathname.startsWith('/invoices/')) return 'Invoice Details';
  return titles[pathname] || 'InvoiceFlow';
};

export function AppHeader() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const title = getTitle(location.pathname);

  return (
    <header className="h-11 border-b border-border bg-background flex items-center justify-between px-4 sticky top-0 z-40">
      <motion.h1
        key={title}
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-sm font-semibold text-foreground"
      >
        {title}
      </motion.h1>

      <div className="flex items-center gap-3">
        <button className="relative p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-all">
          <Bell size={15} />
          <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-primary" />
        </button>
        <button
          onClick={toggleTheme}
          className="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-all"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center">
          <span className="text-primary text-[10px] font-semibold">AU</span>
        </div>
      </div>
    </header>
  );
}
