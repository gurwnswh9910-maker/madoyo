import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import Navbar from "@/components/layout/Navbar";
import Toast from "@/components/layout/Toast";

export const metadata: Metadata = {
  title: "CopyGen SaaS — AI 카피 생성기",
  description: "MAB 전략 최적화 + 임베딩 기반 스코어링을 활용한 고성과 SNS 카피 생성 서비스",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen flex flex-col">
        <AuthProvider>
          <div className="flex-1 w-full max-w-7xl mx-auto p-4 md:p-8 flex flex-col">
            <Navbar />
            <main className="flex-1 w-full relative">{children}</main>
          </div>
          <Toast />
        </AuthProvider>
      </body>
    </html>
  );
}
