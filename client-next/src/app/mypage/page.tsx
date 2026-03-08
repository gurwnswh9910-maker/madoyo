"use client";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { apiGet } from "@/lib/api";
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
  const [plans, setPlans] = useState<Plan[]>([]);
  const [showPlans, setShowPlans] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    apiGet("/billing/plans")
      .then((data) => setPlans(data.plans || []))
      .catch(() => {});
  }, []);

  if (loading || !user) return <div className="text-center py-20 text-gray-500">로딩 중...</div>;

  const handlePurchase = async (planId: string) => {
    showToast("결제 시스템은 프로덕션 배포 후 활성화됩니다.", "error");
    setShowPlans(false);
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h2 className="text-3xl font-bold mb-8">내 계정</h2>

      {/* 크레딧 카드 */}
      <div className="glass-panel p-8 rounded-2xl mb-8">
        <div className="flex justify-between items-center mb-4">
          <div>
            <p className="text-gray-400 text-sm mb-1">남은 크레딧</p>
            <p className="text-5xl font-extrabold text-[var(--accent)]">{user.credits}</p>
          </div>
          <div className="text-right">
            <p className="text-gray-400 text-sm mb-1">현재 플랜</p>
            <span className="bg-[var(--accent)]/20 text-[var(--accent)] px-4 py-1 rounded-full text-sm font-bold uppercase">
              {user.plan}
            </span>
          </div>
        </div>
        <button onClick={() => setShowPlans(!showPlans)} className="btn-primary w-full py-3 rounded-xl mt-4">
          {showPlans ? "닫기" : "💎 크레딧 충전하기"}
        </button>
      </div>

      {/* 요금제 목록 */}
      {showPlans && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {plans.map((plan) => (
            <div key={plan.id} className="glass-panel p-6 rounded-xl flex flex-col">
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

      {/* 계정 정보 */}
      <div className="glass-panel p-6 rounded-2xl">
        <h3 className="text-lg font-bold mb-4">계정 정보</h3>
        <div className="space-y-3">
          <div className="flex justify-between py-2 border-b border-gray-800">
            <span className="text-gray-400">이메일</span>
            <span>{user.email}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-gray-800">
            <span className="text-gray-400">플랜</span>
            <span className="capitalize">{user.plan}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-gray-400">크레딧</span>
            <span className="font-bold text-[var(--accent)]">{user.credits}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
