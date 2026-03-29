"use client";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiGet, apiPost } from "@/lib/api";
import { useRouter } from "next/navigation";
import { showToast } from "@/components/layout/Toast";

interface Plan {
  id: string;
  name: string;
  credits: number;
  price: number;
  description: string;
}

export default function MyPage() {
  const { user, loading, refreshUser } = useAuth();
  const router = useRouter();
  const [generations, setGenerations] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [selectedGenId, setSelectedGenId] = useState<string | null>(null);
  const [rewardUrl, setRewardUrl] = useState("");
  const [plans, setPlans] = useState<any[]>([]);
  const [showPlans, setShowPlans] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    apiGet("/billing/plans")
      .then((data) => setPlans(data.plans || []))
      .catch(() => {});
      
    // 히스토리 로드
    apiGet("/generations/me")
      .then((data) => {
        setGenerations(data.generations || []);
        setLoadingHistory(false);
      })
      .catch((e) => {
        console.error(e);
        setLoadingHistory(false);
      });
  }, []);

  if (loading || !user) return <div className="text-center py-20 text-gray-500">로딩 중...</div>;

  const handlePurchase = async (planId: string) => {
    try {
      showToast("결제창으로 이동합니다...", "success");
      const res = await apiPost("/billing/checkout", { plan: planId });
      if (res.payment_url) {
        window.location.href = res.payment_url;
      } else {
        throw new Error("결제 URL을 생성할 수 없습니다.");
      }
    } catch (e: any) {
      showToast(e.message || "결제 요청 중 오류가 발생했습니다.", "error");
    }
  };
  
  const handleSubmitUrl = async () => {
    if (!rewardUrl) return showToast("URL을 입력해주세요.", "error");
    if (!selectedGenId) return;
    
    try {
      const res = await apiPost(`/generations/${selectedGenId}/submit-url`, { url: rewardUrl });
      showToast(res.message || "보상 신청이 완료되었습니다.", "success");
      setSelectedGenId(null);
      setRewardUrl("");
      // Refresh
      const data = await apiGet("/generations/me");
      setGenerations(data.generations || []);
    } catch (e: any) {
      showToast(e.message || "제출 중 오류가 발생했습니다.", "error");
    }
  };

  return (
    <div className="max-w-4xl mx-auto pb-20">
      <h2 className="text-3xl font-bold mb-8">내 계정</h2>

      {/* 크레딧 카드 */}
      <div className="glass-panel p-8 rounded-2xl mb-8 flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="flex-1">
          <p className="text-gray-400 text-sm mb-1">남은 크레딧</p>
          <div className="flex items-baseline gap-2">
            <p className="text-5xl font-extrabold text-[var(--accent)]">{user.credits}</p>
            <span className="text-gray-400">Credits</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            카피 생성에 크레딧이 사용되며, 생성한 카피를 스레드에 업로드하고 URL을 제출하면 <strong>보상(환급)</strong>을 받을 수 있습니다!
          </p>
        </div>
        <div className="text-right">
          <p className="text-gray-400 text-sm mb-1">현재 플랜</p>
          <span className="bg-[var(--accent)]/20 text-[var(--accent)] px-4 py-1 rounded-full text-sm font-bold uppercase mb-4 inline-block">
            {user.plan}
          </span>
          <button onClick={() => setShowPlans(!showPlans)} className="btn-primary w-full py-3 rounded-xl">
            {showPlans ? "닫기" : "💎 크레딧 충전하기"}
          </button>
        </div>
      </div>

      {/* 요금제 목록 */}
      {showPlans && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {plans.map((plan) => (
            <div key={plan.id} className="glass-panel p-6 rounded-xl flex flex-col transition-transform hover:-translate-y-1">
              <h3 className="text-lg font-bold mb-1">{plan.name}</h3>
              <p className="text-gray-400 text-sm mb-4">{plan.description}</p>
              <p className="text-2xl font-extrabold mb-2">₩{plan.price.toLocaleString()}</p>
              <p className="text-sm text-[var(--accent)] mb-4">{plan.credits} 크레딧</p>
              <button onClick={() => handlePurchase(plan.id)} className="btn-primary py-2 rounded-lg mt-auto">
                구매하기
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 카피 보관함 (히스토리) */}
      <div className="glass-panel p-6 rounded-2xl">
        <div className="flex justify-between items-center mb-6">
          <div className="flex items-center gap-3">
            <h3 className="text-xl font-bold">내 카피 보관함</h3>
            {generations.filter(g => g.status === 'pending').length > 0 && (
              <span className="bg-[var(--accent)]/20 text-[var(--accent)] text-xs px-3 py-1 rounded-full animate-pulse font-bold">
                {generations.filter(g => g.status === 'pending').length}개 생성 대기 중...
              </span>
            )}
          </div>
          <span className="text-xs text-gray-400 bg-gray-800 px-3 py-1 rounded-full">
            생성 후 24시간 뒤 자동 삭제
          </span>
        </div>

        {loadingHistory ? (
          <div className="py-10 text-center text-gray-500">불러오는 중...</div>
        ) : generations.length === 0 ? (
          <div className="py-20 text-center flex flex-col items-center justify-center">
            <div className="text-5xl mb-4 opacity-30">📭</div>
            <p className="text-gray-400 mb-4">아직 생성한 카피가 없습니다.</p>
            <button onClick={() => router.push("/generate")} className="btn-primary px-6 py-2 rounded-xl">
              카피 만들러 가기
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {generations.map((gen) => {
              const date = new Date(gen.created_at).toLocaleString('ko-KR', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
              });
              let resultPreview = gen.status === 'pending' ? "⏳ AI가 데이터를 분석하고 카피를 생성 중입니다..." : "결과물 없음";
              if (gen.results && gen.results.copies) {
                // Bulk일 경우 Copies가 리스트이거나 딕셔너리일 수 있음
                if (Array.isArray(gen.results.copies) && gen.results.copies.length > 0) {
                  resultPreview = gen.results.copies[0].copy_text || gen.results.copies[0].text || "결과물 포함";
                }
              }

              return (
                <div key={gen.id} className="border border-gray-800 rounded-xl p-5 hover:border-[var(--accent)]/50 transition-colors">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <span className="text-xs text-gray-400 mr-3">{date}</span>
                      {gen.bulk_job_id && (
                        <span className="text-xs bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded mr-2">
                          대량생성 (엑셀)
                        </span>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded ${gen.status === 'completed' ? 'bg-green-500/20 text-green-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                        {gen.status === 'completed' ? '완료됨' : '처리 중'}
                      </span>
                    </div>
                  </div>
                  
                  <div className="text-sm text-gray-300 mb-4 line-clamp-2">
                    {resultPreview}
                  </div>
                  
                  <div className="flex justify-end gap-2">
                    {/* View Button */}
                    <button onClick={() => router.push(`/results/${gen.id}`)} className="text-sm text-gray-400 hover:text-white px-3 py-1 bg-gray-800 rounded-lg transition-colors">
                      자세히 보기
                    </button>
                    
                    {/* Reward Button */}
                    {gen.status === 'completed' && (
                      gen.reward_status === 'pending' ? (
                        <span className="text-sm px-4 py-1 rounded-lg bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 flex items-center">
                          ⏳ 보상 심사 대기 중 (24h)
                        </span>
                      ) : gen.reward_status === 'completed' ? (
                        <span className="text-sm px-4 py-1 rounded-lg bg-green-500/20 text-green-400 border border-green-500/30 flex items-center">
                          ✅ +2 크레딧 환급 완료
                        </span>
                      ) : (
                        <button 
                          onClick={() => setSelectedGenId(gen.id)}
                          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-4 py-1 rounded-lg transition-colors flex items-center"
                        >
                          🎁 스레드 URL 제출하고 크레딧 받기
                        </button>
                      )
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* URL 제출 프롬프트 모달 */}
      {selectedGenId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="glass-panel p-6 rounded-2xl max-w-lg w-full shadow-2xl animate-fade-in border border-[var(--accent)]/30">
            <h3 className="text-xl font-bold mb-2 flex items-center gap-2">
              <span>🔗</span> 보상 신청하기
            </h3>
            <p className="text-sm text-gray-300 mb-5 leading-relaxed">
              제작된 카피를 자신의 스레드(Threads) 계정에 업로드하셨나요?<br/>
              해당 게시물의 URL 주소를 입력해주세요. 시스템이 학습을 거친 뒤(24시간) <strong>최대 2 크레딧</strong>을 돌려드립니다!
            </p>
            
            <div className="mb-6">
              <label className="block text-xs text-gray-400 mb-2 pl-1">Threads 게시물 URL</label>
              <input
                type="url"
                value={rewardUrl}
                onChange={(e) => setRewardUrl(e.target.value)}
                placeholder="https://www.threads.net/@user/post/..."
                className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-[var(--accent)] transition-colors"
                autoFocus
              />
            </div>
            
            <div className="flex gap-3 justify-end">
              <button 
                onClick={() => { setSelectedGenId(null); setRewardUrl(""); }}
                className="px-5 py-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
              >
                취소
              </button>
              <button 
                onClick={handleSubmitUrl}
                className="btn-primary px-6 py-2 rounded-xl"
              >
                제출 및 보상 신청
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
