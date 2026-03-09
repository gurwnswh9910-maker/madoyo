"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { apiPost, apiGet } from "./api";

interface User {
  user_id: string;
  email: string;
  plan: string;
  credits: number;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved = localStorage.getItem("auth_token");
    if (saved) {
      setToken(saved);
      apiGet("/auth/me")
        .then((data) => setUser(data))
        .catch(() => {
          localStorage.removeItem("auth_token");
          setToken(null);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const data = await apiPost("/auth/login", { email, password });
    localStorage.setItem("auth_token", data.access_token);
    setToken(data.access_token);
    setUser({ user_id: data.user_id, email: data.email, plan: data.plan, credits: data.credits });
  };

  const register = async (email: string, password: string) => {
    const data = await apiPost("/auth/register", { email, password });
    localStorage.setItem("auth_token", data.access_token);
    setToken(data.access_token);
    setUser({ user_id: data.user_id, email: data.email, plan: data.plan, credits: data.credits });
  };

  const logout = () => {
    localStorage.removeItem("auth_token");
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const data = await apiGet("/auth/me");
      setUser(data);
    } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
