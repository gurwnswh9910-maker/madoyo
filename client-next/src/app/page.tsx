"use client";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="flex flex-col items-center justify-center py-12 md:py-24 text-center">
      <div className="px-4 py-1 rounded-full text-sm font-bold mb-6 border border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10">
        MAB 전략 최적화 AI
      </div>

      <h2 className="text-4xl md:text-6xl font-extrabold mb-6 leading-tight">
        터지는 SNS 게시물,<br />
        <span className="bg-gradient-to-r from-[#6c5ce7] to-[#a29bfe] bg-clip-text text-transparent">
          15초 만에 완성하세요
        </span>
      </h2>

      <p className="text-xl text-gray-400 mb-10 max-w-2xl">
        수천 개의 성공적인 게시물을 학습한 AI가 당신의 제품에 가장 알맞은 소구점과 전략을 찾아 카피를 작성해 드립니다.
      </p>

      <Link
        href="/generate"
        className="btn-primary px-8 py-4 rounded-xl text-lg flex items-center gap-2"
        style={{ boxShadow: "0 0 20px var(--accent-glow)" }}
      >
        ⚡ 지금 바로 시작하기
      </Link>

      {/* 기능 소개 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-20 w-full max-w-4xl">
        {[
          { icon: "🎯", title: "MAB 전략 최적화", desc: "수천 개의 실제 성과 데이터를 학습한 AI가 최적의 전략을 자동 선택합니다." },
          { icon: "📊", title: "실시간 품질 채점", desc: "생성된 카피를 즉시 채점하여 가장 높은 점수의 카피만 제공합니다." },
          { icon: "🔄", title: "자동 학습 루프", desc: "실제 게시물 성과 데이터가 다시 AI에 반영되어 지속적으로 품질이 향상됩니다." },
        ].map((card) => (
          <div key={card.title} className="glass-panel p-6 rounded-2xl text-left">
            <div className="text-3xl mb-3">{card.icon}</div>
            <h3 className="text-lg font-bold mb-2">{card.title}</h3>
            <p className="text-gray-400 text-sm">{card.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
