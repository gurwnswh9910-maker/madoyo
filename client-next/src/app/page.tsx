"use client";
import Link from "next/link";
import Image from "next/image";

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-16 md:gap-24 py-12 md:py-20">
      {/* 히어로 섹션 */}
      <section className="relative flex flex-col md:flex-row items-center gap-10 md:gap-16 text-center md:text-left min-h-[500px]">
        {/* 히어로 이미지: 배경 레이어로 활용하여 겹침 효과 구현 */}
        <div className="w-full md:absolute md:right-[-10%] md:top-1/2 md:-translate-y-1/2 md:w-[60%] lg:w-[55%] animate-float z-10 pointer-events-none transition-all duration-500">
          <div className="relative">
            {/* 좌측 페이드 아웃 효과 (고급스러운 겹침 연출) */}
            <div className="absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-[#030303] via-[#030303]/40 to-transparent z-20 hidden md:block"></div>
            
            <div className="absolute inset-0 bg-gradient-to-tr from-[#6c5ce7]/10 to-[#a29bfe]/10 blur-3xl -z-10 rounded-full"></div>
            <Image 
              src="/images/hero_img.png" 
              alt="SnapThread AI Dashboard Mockup" 
              width={800}
              height={500}
              className="rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.5)] border border-white/10 glass-panel w-full h-auto opacity-70 md:opacity-100"
              priority
            />
          </div>
        </div>

        {/* 텍스트 콘텐츠: 이미지 위에 띄우기 (z-20) */}
        <div className="flex-1 space-y-7 z-20 max-w-2xl">
          <div className="inline-block px-4 py-1.5 rounded-full text-xs font-bold border border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10 animate-fade-in shadow-[0_0_15px_rgba(108,92,231,0.2)]">
            SnapThread — 데이터가 증명하는 성과
          </div>

          <h1 
            className="font-extrabold leading-[1.2] tracking-tight whitespace-pre-line break-keep drop-shadow-2xl"
            style={{ fontSize: "clamp(2rem, 8vw, 4.5rem)" }}
          >
            <span className="inline-block whitespace-nowrap">이제 감(Feel)으로 쓰는</span><br />
            <span className="bg-gradient-to-r from-[#6c5ce7] to-[#a29bfe] bg-clip-text text-transparent inline-block whitespace-nowrap">시대는 끝났습니다.</span>
          </h1>

          <h2 className="text-xl md:text-2xl text-gray-200 font-medium leading-relaxed max-w-xl mx-auto md:mx-0">
            검증된 데이터와 AI 스코어링이 완성하는 <br className="hidden md:block" />
            가장 확실한 1등 카피, SnapThread
          </h2>

          <p className="text-base md:text-lg text-gray-400 max-w-lg leading-relaxed mx-auto md:mx-0 bg-black/30 md:bg-transparent rounded-lg p-2 md:p-0 backdrop-blur-sm md:backdrop-blur-none">
            상품 이미지나 URL 한 줄만 던져주세요. 수만 개의 떡상 데이터를 학습한 AI가 
            제품의 핵심 소구점을 분석하여 터지는 전략을 제안합니다.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 pt-4 justify-center md:justify-start">
            <Link
              href="/generate"
              className="btn-primary px-10 py-4 rounded-xl text-lg font-bold flex items-center justify-center gap-2 hover:scale-105 transition-all duration-300 active:scale-95 glow-effect"
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
