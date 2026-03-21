"use client";
import { useState, useRef, useEffect, Suspense } from "react";
import { apiGet, apiPost, pollTask } from "@/lib/api";
import { showToast } from "@/components/layout/Toast";
import { reportBug } from "@/lib/api";
import { useSearchParams } from "next/navigation";

interface CopyResult {
  rank: number;
  copy_text: string;
  strategy: string;
  score: number;
  showRefine: boolean;
  chatHistory: { role: string; content: string }[];
  refineInput: string;
  isRefining: boolean;
}

const LOADING_PHASES = [
  "🔍 유사 게시물 분석 중...",
  "🧠 전략 도출 중...",
  "✍️ 카피 작성 중...",
  "📊 품질 검증 중...",
];

function GenerateContent() {
  const searchParams = useSearchParams();
  const [text, setText] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [refUrl, setRefUrl] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [results, setResults] = useState<CopyResult[]>([]);
  const [loadingPhase, setLoadingPhase] = useState(0);
  const [publishUrl, setPublishUrl] = useState("");
  const [showPublishBanner, setShowPublishBanner] = useState(false);
  const [genId, setGenId] = useState<string | null>(null);

  // ID가 있을 경우 기존 데이터 로드
  useEffect(() => {
    const id = searchParams.get("id");
    if (id) {
      setLoadingPhase(0);
      setIsGenerating(true);
      apiGet(`/generations/${id}`)
        .then((data) => {
          setGenId(data.id);
          // 입력값 복원
          if (data.input_config) {
            setText(data.input_config.reference_copy || "");
            setRefUrl(data.input_config.url || data.input_config.reference_url || "");
            if (data.input_config.image_urls && data.input_config.image_urls.length > 0) {
              setImageUrl(data.input_config.image_urls[0]);
            }
          }
          // 결과값 복원
          if (data.results && data.results.copies) {
            setResults(
              data.results.copies.map((c: any) => ({
                ...c,
                copy_text: c.copy_text || c.copy || c.text || "",
                score: c.score || c.score_data?.mss_score_estimate || 0,
                showRefine: false,
                chatHistory: [{ role: "assistant", content: "무엇을 어떻게 수정할까요? (예: 더 재미있게 써줘)" }],
                refineInput: "",
                isRefining: false,
              }))
            );
          }
        })
        .catch((err) => {
          showToast("기록을 불러오지 못했습니다.", "error");
        })
        .finally(() => {
          setIsGenerating(false);
        });
    }
  }, [searchParams]);

  const isInputEmpty = !text.trim() && !imageUrl.trim() && !refUrl.trim();

  const startLoadingAnimation = () => {
    setLoadingPhase(0);
    let count = 0;
    const interval = setInterval(() => {
      count++;
      if (count === 2) setLoadingPhase(1);
      if (count === 5) setLoadingPhase(2);
      if (count === 12) setLoadingPhase(3);
    }, 1000);
    return interval;
  };

  const generateCopy = async () => {
    setIsGenerating(true);
    setResults([]);
    const interval = startLoadingAnimation();

    try {
      const reqBody = {
        reference_copy: text.trim() ? text : null,
        image_urls: imageUrl ? [imageUrl] : null,
        reference_url: refUrl.trim() ? refUrl : null,
      };

      const response = await apiPost("/generate", reqBody);

      // 비동기 모드 (task_id 반환)
      if (response.task_id) {
        const result = await pollTask(response.task_id, () => {});
        const data = result as { copies: CopyResult[]; gen_id?: string; processing_time?: number };
        setResults(
          data.copies.map((c: CopyResult) => ({
            ...c,
            showRefine: false,
            chatHistory: [{ role: "assistant", content: "무엇을 어떻게 수정할까요? (예: 더 재미있게 써줘)" }],
            refineInput: "",
            isRefining: false,
          }))
        );
        if (data.gen_id) setGenId(data.gen_id);
        showToast(`🔥 카피 완성!`);
      } else {
        // 동기 모드
        setResults(
          response.copies.map((c: CopyResult) => ({
            ...c,
            showRefine: false,
            chatHistory: [{ role: "assistant", content: "무엇을 어떻게 수정할까요?" }],
            refineInput: "",
            isRefining: false,
          }))
        );
        if (response.gen_id) setGenId(response.gen_id);
        showToast(`🔥 카피 완성! (${response.processing_time}초)`);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "알 수 없는 오류";
      showToast(`오류: ${msg}`, "error");
      reportBug("GenerateError", msg, { text, imageUrl, refUrl });
    } finally {
      clearInterval(interval);
      setIsGenerating(false);
    }
  };

  const handleMediaUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/media`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error("업로드 실패");

      const data = await response.json();
      setImageUrl(data.url);
      showToast("미디어가 첨부되었습니다.");
    } catch (error) {
      showToast("미디어 업로드에 실패했습니다.", "error");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const copyToClipboard = async (copyText: string) => {
    try {
      await navigator.clipboard.writeText(copyText);
      showToast("클립보드에 복사되었습니다! 📋");
      setShowPublishBanner(true);
    } catch {
      showToast("복사에 실패했습니다.", "error");
    }
  };

  const sendFeedback = async (rating: "good" | "bad", reasons: string[] = []) => {
    if (!genId) return;
    try {
      await apiPost("/feedback", { gen_id: genId, copy_rank: 1, rating, reasons });
      showToast(rating === "good" ? "👍 감사합니다!" : "피드백이 반영됩니다 🙏");
    } catch {}
  };

  const toggleRefine = (index: number) => {
    setResults((prev) =>
      prev.map((r, i) => (i === index ? { ...r, showRefine: !r.showRefine } : r))
    );
  };

  const sendRefine = async (index: number) => {
    const item = results[index];
    if (!item.refineInput.trim() || item.isRefining) return;

    const instruction = item.refineInput;
    setResults((prev) =>
      prev.map((r, i) =>
        i === index
          ? {
              ...r,
              refineInput: "",
              chatHistory: [...r.chatHistory, { role: "user", content: instruction }],
              isRefining: true,
            }
          : r
      )
    );

    try {
      const data = await apiPost("/refine", {
        original_copy: item.copy_text,
        user_instruction: instruction,
        conversation_history: item.chatHistory.map((h) => ({
          role: h.role === "assistant" ? "model" : "user",
          content: h.content,
        })),
      });

      setResults((prev) =>
        prev.map((r, i) =>
          i === index
            ? {
                ...r,
                copy_text: data.refined_copy,
                chatHistory: [...r.chatHistory, { role: "assistant", content: data.refined_copy }],
                isRefining: false,
              }
            : r
        )
      );
      showToast("✅ 카피가 수정되었습니다.");
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "수정 실패";
      setResults((prev) =>
        prev.map((r, i) =>
          i === index
            ? {
                ...r,
                chatHistory: [...r.chatHistory, { role: "assistant", content: `🚨 ${msg}` }],
                isRefining: false,
              }
            : r
        )
      );
    }
  };

  const submitPublishUrl = async () => {
    if (!publishUrl.trim() || !genId) return;
    try {
      await apiPost("/feedback", { gen_id: genId, copy_rank: 1, rating: null, reasons: [], published_url: publishUrl });
      showToast("✅ 게시물 URL이 등록되었습니다. 24시간 후 성과를 수집합니다!");
      setShowPublishBanner(false);
      setPublishUrl("");
    } catch {
      showToast("URL 등록 실패", "error");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      {/* ─── 좌측: 입력 패널 ─── */}
      <div className="lg:col-span-4">
        <div className="glass-panel p-6 rounded-2xl lg:sticky lg:top-8">
          <h3 className="text-lg font-bold mb-6">최고의 효율을 내는 카피 만들기</h3>

          {/* 통합 입력 필드 */}
          <div className="space-y-4 mb-6 relative">
            <div className="relative">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="input-field h-48 resize-none pb-14 text-base"
                placeholder="어떤 카피를 원하시나요? 제품의 핵심 소구점이나 요청사항을 적어주세요.&#13;&#10;(예: 똥손도 1초만에 샵퀄리티 자석 네일 완성)"
              />
              
              {/* 미디어 업로드 버튼 */}
              <div className="absolute bottom-4 left-4 flex items-center gap-3">
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center hover:scale-110 transition-transform group"
                  style={{ width: '28px', height: '28px' }}
                  title="미디어 업로드"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} style={{ width: '28px', height: '28px' }} className="stroke-gray-400 group-hover:stroke-[var(--accent)] transition-colors">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
                  </svg>
                </button>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  className="hidden" 
                  accept="image/*,video/*"
                  onChange={handleMediaUpload}
                />
                {imageUrl && (
                  <div className="text-xs font-semibold text-green-400 bg-green-400/10 px-3 py-1.5 rounded-lg max-w-[200px] truncate border border-green-400/20 flex items-center gap-2">
                    ✓ 첨부됨
                    <button onClick={() => setImageUrl("")} className="text-green-500 hover:text-green-300 ml-1">✕</button>
                  </div>
                )}
              </div>
            </div>

            {/* 하단 URL 입력 필드 */}
            <div className="relative mt-2">
              <div className="absolute inset-y-0 left-5 flex items-center pointer-events-none">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} className="w-5 h-5 stroke-gray-500">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
                </svg>
              </div>
              <input
                value={refUrl}
                onChange={(e) => setRefUrl(e.target.value)}
                className="input-field text-sm py-4"
                style={{ paddingLeft: '3rem' }}
                placeholder="가져올 게시물 URL 입력 (선택)"
              />
            </div>
          </div>

          <button
            onClick={generateCopy}
            disabled={isGenerating || isInputEmpty}
            className="btn-primary w-full py-4 rounded-xl flex items-center justify-center gap-2"
          >
            {isGenerating ? "⏳ 생성 중..." : "카피 생성하기 🚀"}
          </button>
        </div>
      </div>

      {/* ─── 우측: 결과 영역 ─── */}
      <div className="lg:col-span-8 min-h-[500px]">
        {/* 비어있을 때 */}
        {!isGenerating && results.length === 0 && (
          <div className="h-full border-2 border-dashed border-gray-800 rounded-2xl flex items-center justify-center text-gray-500 min-h-[400px]">
            좌측에서 입력을 완료하고 생성을 시작해보세요.
          </div>
        )}

        {/* 로딩 */}
        {isGenerating && (
          <div className="h-full glass-panel rounded-2xl flex flex-col items-center justify-center p-12 py-32 min-h-[400px]">
            <div className="spinner mb-6" />
            <h3 className="text-xl font-bold mb-2">{LOADING_PHASES[loadingPhase]}</h3>
            <p className="text-gray-400 text-sm">보통 15~25초 정도 소요됩니다.</p>
            <div className="flex gap-2 mt-6">
              {LOADING_PHASES.map((_, i) => (
                <div
                  key={i}
                  className={`h-2 w-12 rounded-full transition-colors ${i <= loadingPhase ? "bg-[var(--accent)]" : "bg-gray-700"}`}
                />
              ))}
            </div>
          </div>
        )}

        {/* 결과 카드 */}
        {!isGenerating && results.length > 0 && (
          <div className="space-y-6">
            <h3 className="text-2xl font-bold mb-4">🎉 생성된 카피 TOP 3</h3>

            {results.map((copy, index) => (
              <div key={index} className="glass-panel rounded-xl overflow-hidden">
                {/* 헤더 */}
                <div className="flex justify-between items-center p-4 bg-white/5 border-b border-gray-800">
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold">#{copy.rank}</span>
                    <span className="badge-strategy">🎯 {copy.strategy}</span>
                  </div>
                  <div className="text-xs text-gray-500">MSS 예상: {Math.round(copy.score)}</div>
                </div>

                {/* 카피 본문 */}
                <div className="p-6 text-lg leading-relaxed whitespace-pre-wrap text-gray-100">
                  {copy.copy_text}
                </div>

                {/* 액션 바 */}
                <div className="p-4 bg-[var(--bg-secondary)] border-t border-gray-800 flex justify-between items-center">
                  {/* 피드백 */}
                  <FeedbackButtons onFeedback={sendFeedback} />
                  <div className="flex gap-3">
                    <button onClick={() => toggleRefine(index)} className="btn-outline px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                      💬 {copy.showRefine ? "수정 닫기" : "AI 수정하기"}
                    </button>
                    <button onClick={() => copyToClipboard(copy.copy_text)} className="btn-primary px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                      📋 복사하기
                    </button>
                  </div>
                </div>

                {/* 수정 채팅 */}
                {copy.showRefine && (
                  <div className="bg-[var(--bg-secondary)] border-t border-gray-800 p-4">
                    <div className="max-h-60 overflow-y-auto mb-4 space-y-3 p-2">
                      {copy.chatHistory.map((msg, mi) => (
                        <div key={mi} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                          <div
                            className={`px-4 py-2 rounded-2xl max-w-[80%] whitespace-pre-wrap text-sm leading-relaxed ${
                              msg.role === "user" ? "bg-[var(--accent)] text-white rounded-br-none" : "glass-panel text-gray-200 rounded-bl-none"
                            }`}
                          >
                            {msg.content}
                          </div>
                        </div>
                      ))}
                      {copy.isRefining && (
                        <div className="flex justify-start">
                          <div className="glass-panel px-4 py-2 rounded-2xl rounded-bl-none text-sm text-gray-200 flex items-center gap-2">
                            ⏳ 수정 중...
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 relative">
                      <input
                        value={copy.refineInput}
                        onChange={(e) =>
                          setResults((prev) =>
                            prev.map((r, i) => (i === index ? { ...r, refineInput: e.target.value } : r))
                          )
                        }
                        onKeyDown={(e) => e.key === "Enter" && sendRefine(index)}
                        placeholder="더 짧게 해줘, 혹은 이모지 빼줘"
                        className="flex-1 bg-[var(--bg-primary)] border border-gray-700 rounded-full px-5 py-2.5 text-sm text-white focus:border-[var(--accent)] outline-none transition-colors"
                        disabled={copy.isRefining}
                      />
                      <button
                        onClick={() => sendRefine(index)}
                        disabled={copy.isRefining || !copy.refineInput.trim()}
                        className="btn-primary w-10 h-10 rounded-full flex items-center justify-center absolute right-1 top-0.5"
                      >
                        ➤
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* 게시물 URL 입력 배너 */}
            {showPublishBanner && (
              <div className="glass-panel p-6 rounded-xl border-l-4 border-[var(--accent)]">
                <p className="text-sm text-gray-300 mb-3">
                  💡 게시물을 올린 후 링크를 알려주세요! 24시간 뒤 자동으로 AI가 학습합니다.
                </p>
                <div className="flex gap-2">
                  <input
                    value={publishUrl}
                    onChange={(e) => setPublishUrl(e.target.value)}
                    placeholder="https://www.threads.net/..."
                    className="input-field flex-1 !py-2"
                  />
                  <button onClick={submitPublishUrl} className="btn-primary px-6 py-2 rounded-xl text-sm">
                    제출
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── 피드백 버튼 서브컴포넌트 ─── */
function FeedbackButtons({ onFeedback }: { onFeedback: (rating: "good" | "bad", reasons?: string[]) => void }) {
  const [showReasons, setShowReasons] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const REASONS = ["어색한 표현", "반복 느낌", "너무 길어요", "주제와 무관"];

  const toggleReason = (r: string) => {
    setSelectedReasons((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  };

  return (
    <div className="relative">
      <div className="flex gap-2">
        <button onClick={() => onFeedback("good")} className="btn-outline px-3 py-1.5 rounded-lg text-sm">
          👍
        </button>
        <button onClick={() => setShowReasons(!showReasons)} className="btn-outline px-3 py-1.5 rounded-lg text-sm">
          👎
        </button>
      </div>

      {showReasons && (
        <div className="absolute bottom-full left-0 mb-2 glass-panel p-4 rounded-xl w-56 z-10">
          <p className="text-xs text-gray-400 mb-2">이유를 선택해주세요</p>
          {REASONS.map((r) => (
            <label key={r} className="flex items-center gap-2 text-sm py-1 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={selectedReasons.includes(r)}
                onChange={() => toggleReason(r)}
                className="accent-[var(--accent)]"
              />
              {r}
            </label>
          ))}
          <button
            onClick={() => {
              onFeedback("bad", selectedReasons);
              setShowReasons(false);
              setSelectedReasons([]);
            }}
            className="btn-primary w-full py-1.5 rounded-lg text-sm mt-2"
          >
            전송
          </button>
        </div>
      )}
    </div>
  );
}

export default function GeneratePage() {
  return (
    <Suspense fallback={<div className="text-center py-20 text-gray-500">페이지 로딩 중...</div>}>
      <GenerateContent />
    </Suspense>
  );
}
