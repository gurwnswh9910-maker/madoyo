"use client";
import Link from "next/link";
import Image from "next/image";

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-16 md:gap-24 py-12 md:py-20">
      {/* 히어로 섹션: 텍스트 중심 중앙 정렬 레이아웃 */}
      <section className="relative flex flex-col items-center text-center py-10 md:py-20 min-h-[450px] overflow-hidden">
        {/* 중앙 배경 글로우 효과 (이미지 대신 신비로운 분위기 연출) */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-[var(--accent)]/10 blur-[150px] -z-10 rounded-full animate-pulse"></div>
        
        {/* 텍스트 콘텐츠: 중앙 배치 */}
        <div className="space-y-8 z-30 max-w-4xl mx-auto px-4">
          <div className="inline-block px-5 py-1.5 rounded-full text-xs font-bold border border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10 animate-fade-in shadow-[0_0_20px_rgba(108,92,231,0.2)]">
            SnapThread — 데이터가 증명하는 성과
          </div>

          <h1 
            className="font-extrabold leading-[1.2] tracking-tight whitespace-pre-line break-keep drop-shadow-xl"
            style={{ fontSize: "clamp(2.5rem, 9vw, 5rem)" }}
          >
            <span className="inline-block">이제 감(Feel)으로 쓰는</span><br />
            <span className="bg-gradient-to-r from-[#6c5ce7] to-[#a29bfe] bg-clip-text text-transparent inline-block">시대는 끝났습니다.</span>
          </h1>

          <h2 className="text-xl md:text-3xl text-gray-200 font-medium leading-relaxed max-w-2xl mx-auto">
            검증된 데이터와 AI 스코어링이 완성하는 <br className="hidden md:block" />
            가장 확실한 1등 카피, SnapThread
          </h2>

          <p className="text-lg md:text-xl text-gray-400 max-w-2xl leading-relaxed mx-auto italic opacity-80">
            상품 이미지나 URL 한 줄만 던져주세요. 수만 개의 떡상 데이터를 학습한 AI가 
            제품의 핵심 소구점을 분석하여 터지는 전략을 제안합니다.
          </p>

          <div className="flex flex-col sm:flex-row gap-6 pt-6 justify-center">
            <Link
              href="/generate"
              className="btn-primary px-12 py-5 rounded-2xl text-xl font-bold flex items-center justify-center gap-3 hover:scale-105 transition-all duration-300 active:scale-95 glow-effect shadow-[0_0_30px_rgba(108,92,231,0.3)]"
            >
              ⚡ 1초만에 카피 생성하기
            </Link>
          </div>
        </div>
      </section>

      {/* 기능 소개 섹션 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
        {[
          { icon: "🎯", title: "지능형 전략 기반", desc: "단순한 생성지가 아닙니다. 빅데이터로 입증된 '수익형' 전략을 먼저 수립합니다." },
          { icon: "📊", title: "정밀 랭킹 채점", desc: "파인튜닝된 AI가 100여 개의 후보군 중 가장 터질 확률이 높은 1등만 가려냅니다." },
          { icon: "⚡", title: "URL 한 줄의 마법", desc: "URL에서 이미지와 텍스트를 자동 추출하여 즉시 수익화 파이프라인으로 연결합니다." },
        ].map((card) => (
          <div key={card.title} className="glass-panel p-8 rounded-3xl border border-white/5 hover:border-[var(--accent)]/30 transition-all group">
            <div className="text-4xl mb-4 group-hover:scale-110 transition-transform">{card.icon}</div>
            <h3 className="text-xl font-bold mb-3">{card.title}</h3>
            <p className="text-gray-400 leading-relaxed text-sm">{card.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
