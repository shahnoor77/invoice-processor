import React, { createContext, useContext, useReducer, useCallback } from 'react';
import { apiLogin } from '@/lib/api';

interface AuthState {
  isAuthenticated: boolean;
  user: { email: string; name: string } | null;
  loading: boolean;
}

type AuthAction =
  | { type: 'LOGIN_SUCCESS'; payload: { email: string; name: string } }
  | { type: 'LOGOUT' }
  | { type: 'SET_LOADING'; payload: boolean };

const stored = localStorage.getItem('invoiceflow-user');
const initialState: AuthState = {
  isAuthenticated: !!localStorage.getItem('token'),
  user: stored ? JSON.parse(stored) : null,
  loading: false,
};

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOGIN_SUCCESS':
      return { isAuthenticated: true, user: action.payload, loading: false };
    case 'LOGOUT':
      return { isAuthenticated: false, user: null, loading: false };
    case 'SET_LOADING':
      return { ...state, loading: action.payload };
    default:
      return state;
  }
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialState);

  const login = useCallback(async (email: string, password: string) => {
    dispatch({ type: 'SET_LOADING', payload: true });
    try {
      const data = await apiLogin(email, password);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('invoiceflow-user', JSON.stringify({ email, name: data.name }));
      dispatch({ type: 'LOGIN_SUCCESS', payload: { email, name: data.name } });
      return true;
    } catch {
      dispatch({ type: 'SET_LOADING', payload: false });
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('invoiceflow-user');
    dispatch({ type: 'LOGOUT' });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
