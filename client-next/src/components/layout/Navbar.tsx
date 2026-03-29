"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

export default function Navbar() {
  const { user, logout } = useAuth();

  return (
    <header className="flex flex-col sm:flex-row justify-between items-center pb-6 border-b border-gray-800 mb-8 gap-4">
      <Link href="/" className="flex items-center gap-2 cursor-pointer group">
        <span className="text-2xl group-hover:scale-110 transition-transform">⚡</span>
        <h1 className="text-xl font-bold tracking-tight">SnapThread</h1>
      </Link>

      <nav className="flex items-center gap-4 md:gap-8 overflow-x-auto w-full sm:w-auto justify-center sm:justify-end py-2 sm:py-0">
        <Link href="/generate" className="text-gray-400 hover:text-white transition-colors flex items-center gap-1.5 whitespace-nowrap text-sm md:text-base">
          📝 카피 생성
        </Link>

        {user ? (
          <div className="flex items-center gap-4">
            <Link href="/mypage" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
              <span className="bg-[var(--accent)] text-white text-xs px-2 py-0.5 rounded-full font-bold">
                {user.credits}크레딧
              </span>
              <span className="text-sm">{user.email}</span>
            </Link>
            <button onClick={logout} className="text-gray-500 hover:text-red-400 text-sm transition-colors">
              로그아웃
            </button>
          </div>
        ) : (
          <Link href="/login" className="btn-primary px-4 py-2 rounded-lg text-sm">
            로그인
          </Link>
        )}
      </nav>
    </header>
  );
}
