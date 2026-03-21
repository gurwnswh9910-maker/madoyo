"use client";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { showToast } from "@/components/layout/Toast";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, register, loginWithKakao, loginWithGoogle } = useAuth();
  const router = useRouter();

  const handleSocialLogin = async (provider: "kakao" | "google") => {
    setLoading(true);
    try {
      if (provider === "kakao") await loginWithKakao();
      else await loginWithGoogle();
    } catch (err) {
      showToast("소셜 로그인 중 오류가 발생했습니다.", "error");
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) return;
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        showToast("로그인 성공! 🎉");
      } else {
        await register(email, password);
        showToast("가입 완료! 🎉");
      }
      router.push("/generate");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "오류가 발생했습니다.";
      showToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="glass-panel p-8 rounded-2xl w-full max-w-md">
        <h2 className="text-2xl font-bold mb-6 text-center">
          {mode === "login" ? "로그인" : "회원가입"}
        </h2>

        {/* 탭 */}
        <div className="flex gap-2 mb-6 p-1 bg-[var(--bg-secondary)] rounded-lg">
          <button
            onClick={() => setMode("login")}
            className={`flex-1 py-2 rounded-md text-sm font-semibold transition-colors ${mode === "login" ? "bg-[var(--accent)] text-white" : "text-gray-400"}`}
          >
            로그인
          </button>
          <button
            onClick={() => setMode("register")}
            className={`flex-1 py-2 rounded-md text-sm font-semibold transition-colors ${mode === "register" ? "bg-[var(--accent)] text-white" : "text-gray-400"}`}
          >
            회원가입
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="이메일"
            className="input-field"
            required
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            className="input-field"
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-3 rounded-xl text-center"
          >
            {loading ? "처리 중..." : mode === "login" ? "로그인" : "가입하기"}
          </button>
        </form>

        <div className="relative my-8">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-700"></div>
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-[var(--bg-primary)] px-2 text-gray-400">SNS 계정으로 시작하기</span>
          </div>
        </div>

        <div className="space-y-3">
          <button
            onClick={() => handleSocialLogin("kakao")}
            disabled={loading}
            className="flex items-center justify-center w-full py-3 px-4 rounded-xl bg-[#FEE500] text-[#191919] font-bold transition-all hover:bg-[#FADA0A] disabled:opacity-50"
          >
            <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/KakaoTalk_logo.svg/1200px-KakaoTalk_logo.svg.png" alt="Kakao" className="w-5 h-5 mr-2" />
            카카오로 시작하기
          </button>

          <button
            onClick={() => handleSocialLogin("google")}
            disabled={loading}
            className="flex items-center justify-center w-full py-3 px-4 rounded-xl bg-white text-gray-700 font-bold border border-gray-200 transition-all hover:bg-gray-50 disabled:opacity-50"
          >
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" className="w-5 h-5 mr-2" />
            구글로 시작하기
          </button>
        </div>


      </div>
    </div>
  );
}
