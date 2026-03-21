"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { supabase } from "./supabase";
import { apiGet } from "./api";

interface User {
  user_id: string;
  email: string;
  plan: string;
  credits: number;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  loginWithKakao: () => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 1. 초기 세션 확인
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        localStorage.setItem("auth_token", session.access_token);
        fetchUserInfo();
      } else {
        setLoading(false);
      }
    });

    // 2. 인증 상태 변화 감지
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        localStorage.setItem("auth_token", session.access_token);
        fetchUserInfo();
      } else {
        localStorage.removeItem("auth_token");
        setUser(null);
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchUserInfo = async () => {
    try {
      const data = await apiGet("/auth/me");
      setUser(data);
    } catch (err) {
      console.error("User info fetch failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
  };

  const register = async (email: string, password: string) => {
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
  };

  const loginWithKakao = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'kakao',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`
      }
    });
    if (error) throw error;
  };

  const loginWithGoogle = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`
      }
    });
    if (error) throw error;
  };

  const logout = async () => {
    await supabase.auth.signOut();
  };

  const refreshUser = async () => {
    await fetchUserInfo();
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, loginWithKakao, loginWithGoogle, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
