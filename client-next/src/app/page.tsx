"use client";
import Link from "next/link";
import Image from "next/image";

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-16 md:gap-24 py-12 md:py-20">
      {/* 히어로 섹션 */}
      <section className="flex flex-col md:flex-row items-center gap-10 md:gap-16 text-center md:text-left">
        {/* 모바일에서는 이미지를 먼저 보여주어 시각적 임팩트 부여 (order-first) */}
        <div className="flex-1 w-full max-w-lg md:max-w-xl relative animate-float order-first md:order-last">
          <div className="absolute inset-0 bg-gradient-to-tr from-[#6c5ce7]/20 to-[#a29bfe]/20 blur-3xl -z-10 rounded-full"></div>
          <Image 
            src="/images/hero_img.png" 
            alt="SnapThread AI Dashboard Mockup" 
            width={700}
            height={400}
            className="rounded-2xl shadow-2xl border border-white/10 glass-panel w-full h-auto"
            priority
          />
        </div>

        <div className="flex-1 space-y-6">
          <div className="inline-block px-4 py-1.5 rounded-full text-xs font-bold border border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10 animate-fade-in shadow-[0_0_15px_rgba(108,92,231,0.2)]">
            SnapThread — 데이터가 증명하는 성과
          </div>

          <h1 
            className="font-extrabold leading-[1.2] tracking-tight whitespace-pre-line break-keep"
            style={{ fontSize: "clamp(1.75rem, 8vw, 4rem)" }}
          >
            <span className="inline-block whitespace-nowrap">이제 감(Feel)으로 쓰는</span><br />
            <span className="bg-gradient-to-r from-[#6c5ce7] to-[#a29bfe] bg-clip-text text-transparent inline-block whitespace-nowrap">시대는 끝났습니다.</span>
          </h1>

          <h2 className="text-lg md:text-2xl text-gray-200 font-medium leading-relaxed max-w-2xl mx-auto md:mx-0">
            검증된 데이터와 AI 스코어링이 완성하는 <br className="hidden md:block" />
            가장 확실한 1등 카피, SnapThread
          </h2>

          <p className="text-base md:text-lg text-gray-400 max-w-xl leading-relaxed mx-auto md:mx-0">
            상품 이미지나 URL 한 줄만 던져주세요. 수만 개의 떡상 데이터를 학습한 AI가 
            제품의 핵심 소구점을 분석하여 터지는 전략을 제안합니다.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 pt-4 justify-center md:justify-start">
            <Link
              href="/generate"
              className="btn-primary px-10 py-4 rounded-xl text-lg font-bold flex items-center justify-center gap-2 hover:scale-105 transition-all duration-300 active:scale-95"
              style={{ boxShadow: "0 10px 40px var(--accent-glow)" }}
            >
              ⚡ 카피 생성하기
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
