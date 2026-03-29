"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiGet, apiPost, pollTask } from "@/lib/api";
import { showToast } from "@/components/layout/Toast";
import { useAuth } from "@/lib/auth-context";

interface ChatMessage {
  role: string;
  content: string;
}

interface CopyResult {
  rank: number;
  copy_text: string;
  original_copy_text: string;
  version_history: string[];
  strategy: string;
  score: number;
  showRefine: boolean;
  chatHistory: ChatMessage[];
  refineInput: string;
  isRefining: boolean;
}

interface GenerationDetail {
  id: string;
  created_at: string;
  input_config?: {
    reference_copy?: string;
    reference_url?: string;
    url?: string;
    image_urls?: string[];
    appeal_point?: string;
  };
  results?: {
    copies?: Array<Record<string, unknown>>;
    error?: string;
  };
  status?: string;
}

function mapCopies(copies: Array<Record<string, unknown>> = []): CopyResult[] {
  return copies.map((copy, index) => ({
    rank: Number(copy.rank ?? index + 1),
    copy_text: String(copy.copy_text ?? copy.copy ?? copy.text ?? ""),
    original_copy_text: String(copy.copy_text ?? copy.copy ?? copy.text ?? ""),
    version_history: [String(copy.copy_text ?? copy.copy ?? copy.text ?? "")],
    strategy: String(copy.strategy ?? "전략"),
    score: Number(copy.score ?? ((copy.score_data as { mss_score_estimate?: number } | undefined)?.mss_score_estimate ?? 0)),
    showRefine: false,
    chatHistory: [{ role: "assistant", content: "무엇을 어떻게 수정할까요? (예: 더 재미있게 써줘)" }],
    refineInput: "",
    isRefining: false,
  }));
}

function FeedbackButtons({ onFeedback }: { onFeedback: (rating: "good" | "bad", reasons?: string[]) => void }) {
  const [showReasons, setShowReasons] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const reasons = ["어색한 표현", "반복 느낌", "너무 길어요", "주제와 무관"];

  const toggleReason = (reason: string) => {
    setSelectedReasons((prev) => (prev.includes(reason) ? prev.filter((item) => item !== reason) : [...prev, reason]));
  };

  return (
    <div className="relative">
      <div className="flex gap-2">
        <button onClick={() => onFeedback("good")} className="btn-outline px-3 py-1.5 rounded-lg text-sm">
          👍
        </button>
        <button onClick={() => setShowReasons((prev) => !prev)} className="btn-outline px-3 py-1.5 rounded-lg text-sm">
          👎
        </button>
      </div>

      {showReasons && (
        <div className="absolute bottom-full left-0 mb-2 glass-panel p-4 rounded-xl w-56 z-10">
          <p className="text-xs text-gray-400 mb-2">이유를 선택해주세요</p>
          {reasons.map((reason) => (
            <label key={reason} className="flex items-center gap-2 text-sm py-1 cursor-pointer text-gray-300 hover:text-white">
              <input
                type="checkbox"
                checked={selectedReasons.includes(reason)}
                onChange={() => toggleReason(reason)}
                className="accent-[var(--accent)]"
              />
              {reason}
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

export default function ResultDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user, loading, refreshUser } = useAuth();
  const generationId = params.id;

  const [generation, setGeneration] = useState<GenerationDetail | null>(null);
  const [results, setResults] = useState<CopyResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [publishUrl, setPublishUrl] = useState("");
  const [showPublishBanner, setShowPublishBanner] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, router, user]);

  useEffect(() => {
    if (!generationId) return;

    let cancelled = false;

    const loadGeneration = async () => {
      try {
        const data = (await apiGet(`/generations/${generationId}`)) as GenerationDetail;
        if (cancelled) return;

        setGeneration(data);

        if (data.results?.copies) {
          setResults(mapCopies(data.results.copies));
        }

        if (data.status === "pending" || data.status === "processing") {
          await pollTask(generationId, () => {});
          const refreshed = (await apiGet(`/generations/${generationId}`)) as GenerationDetail;
          if (cancelled) return;

          setGeneration(refreshed);
          setResults(mapCopies(refreshed.results?.copies));
        }
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "결과를 불러오지 못했습니다.";
        showToast(message, "error");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadGeneration();

    return () => {
      cancelled = true;
    };
  }, [generationId]);

  const createdAtText = useMemo(() => {
    if (!generation?.created_at) return "";
    return new Date(generation.created_at).toLocaleString("ko-KR");
  }, [generation?.created_at]);

  const sendFeedback = async (rating: "good" | "bad", reasons: string[] = []) => {
    if (!generationId) return;
    try {
      await apiPost("/feedback", { gen_id: generationId, copy_rank: 1, rating, reasons });
      showToast(rating === "good" ? "👍 감사합니다!" : "피드백이 반영됩니다 🙏");
    } catch {}
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

  const toggleRefine = (index: number) => {
    setResults((prev) => prev.map((result, currentIndex) => (currentIndex === index ? { ...result, showRefine: !result.showRefine } : result)));
  };

  const sendRefine = async (index: number) => {
    const item = results[index];
    if (!item?.refineInput.trim() || item.isRefining) return;

    const instruction = item.refineInput;
    setResults((prev) =>
      prev.map((result, currentIndex) =>
        currentIndex === index
          ? {
              ...result,
              refineInput: "",
              chatHistory: [...result.chatHistory, { role: "user", content: instruction }],
              isRefining: true,
            }
          : result
      )
    );

    try {
      const data = await apiPost("/refine", {
        gen_id: generationId,
        original_copy: item.copy_text,
        user_instruction: instruction,
        conversation_history: item.chatHistory.map((history) => ({
          role: history.role === "assistant" ? "model" : "user",
          content: history.content,
        })),
      });

      setResults((prev) =>
        prev.map((result, currentIndex) =>
          currentIndex === index
            ? {
                ...result,
                copy_text: data.refined_copy,
                version_history:
                  result.version_history[result.version_history.length - 1] === data.refined_copy
                    ? result.version_history
                    : [...result.version_history, data.refined_copy],
                chatHistory: [...result.chatHistory, { role: "assistant", content: data.refined_copy }],
                isRefining: false,
              }
            : result
        )
      );
      showToast("✅ 카피가 수정되었습니다.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "수정 실패";
      setResults((prev) =>
        prev.map((result, currentIndex) =>
          currentIndex === index
            ? {
                ...result,
                chatHistory: [...result.chatHistory, { role: "assistant", content: `🚨 ${message}` }],
                isRefining: false,
              }
            : result
        )
      );
    }
  };

  const submitPublishUrl = async () => {
    if (!publishUrl.trim() || !generationId) return;
    try {
      await apiPost("/feedback", { gen_id: generationId, copy_rank: 1, rating: null, reasons: [], published_url: publishUrl });
      showToast("✅ 게시물 URL이 등록되었습니다. 24시간 후 성과를 수집합니다!");
      setShowPublishBanner(false);
      setPublishUrl("");
      refreshUser();
    } catch {
      showToast("URL 등록 실패", "error");
    }
  };

  if (loading || !user) {
    return <div className="text-center py-20 text-gray-500">로딩 중...</div>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      <div className="lg:col-span-4">
        <div className="glass-panel p-6 rounded-2xl lg:sticky lg:top-8 space-y-5">
          <div>
            <p className="text-sm text-gray-400 mb-1">결과 기록</p>
            <h2 className="text-2xl font-bold">생성 결과</h2>
            {createdAtText && <p className="text-xs text-gray-500 mt-2">{createdAtText}</p>}
          </div>

          <div className="space-y-4 text-sm">
            <div>
              <p className="text-gray-400 mb-1">참고 카피</p>
              <div className="bg-[var(--bg-secondary)] rounded-xl p-4 whitespace-pre-wrap text-gray-200 min-h-20">
                {generation?.input_config?.reference_copy || "입력 없음"}
              </div>
            </div>

            <div>
              <p className="text-gray-400 mb-1">소구점</p>
              <div className="bg-[var(--bg-secondary)] rounded-xl p-4 text-gray-200">
                {generation?.input_config?.appeal_point || "입력 없음"}
              </div>
            </div>

            <div>
              <p className="text-gray-400 mb-1">참고 URL</p>
              <div className="bg-[var(--bg-secondary)] rounded-xl p-4 break-all text-gray-200">
                {generation?.input_config?.reference_url || generation?.input_config?.url || "입력 없음"}
              </div>
            </div>

            <button onClick={() => router.push("/generate")} className="btn-outline w-full py-3 rounded-xl">
              새로 생성하러 가기
            </button>
          </div>
        </div>
      </div>

      <div className="lg:col-span-8 min-h-[500px]">
        {isLoading && (
          <div className="h-full glass-panel rounded-2xl flex flex-col items-center justify-center p-12 py-32 min-h-[400px]">
            <div className="spinner mb-6" />
            <h3 className="text-xl font-bold mb-2">결과를 불러오는 중...</h3>
            <p className="text-gray-400 text-sm">생성이 끝나면 자동으로 결과를 보여드립니다.</p>
          </div>
        )}

        {!isLoading && results.length === 0 && (
          <div className="h-full border-2 border-dashed border-gray-800 rounded-2xl flex items-center justify-center text-gray-500 min-h-[400px]">
            아직 표시할 결과가 없습니다.
          </div>
        )}

        {!isLoading && results.length > 0 && (
          <div className="space-y-6">
            <h3 className="text-2xl font-bold mb-4">🎉 생성된 카피 TOP 3</h3>

            {results.map((copy, index) => (
              <div key={index} className="glass-panel rounded-xl overflow-hidden">
                <div className="flex justify-between items-center p-4 bg-white/5 border-b border-gray-800">
                  <div className="flex items-center gap-3">
                    <span className="text-xl font-bold">#{copy.rank}</span>
                    <span className="badge-strategy">🎯 {copy.strategy}</span>
                  </div>
                  <div className="text-xs text-gray-500">MSS 예상: {Math.round(copy.score)}</div>
                </div>

                <div className="p-6 text-lg leading-relaxed whitespace-pre-wrap text-gray-100">
                  {copy.copy_text}
                </div>

                <div className="p-4 bg-[var(--bg-secondary)] border-t border-gray-800 flex justify-between items-center">
                  <FeedbackButtons onFeedback={sendFeedback} />
                  <div className="flex gap-3">
                    {copy.original_copy_text !== copy.copy_text && (
                      <button onClick={() => copyToClipboard(copy.original_copy_text)} className="btn-outline px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                        원본 복사
                      </button>
                    )}
                    <button onClick={() => toggleRefine(index)} className="btn-outline px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                      💬 {copy.showRefine ? "수정 닫기" : "AI 수정하기"}
                    </button>
                    <button onClick={() => copyToClipboard(copy.copy_text)} className="btn-primary px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                      📋 복사하기
                    </button>
                  </div>
                </div>

                {copy.showRefine && (
                  <div className="bg-[var(--bg-secondary)] border-t border-gray-800 p-4">
                    <div className="mb-4 space-y-3">
                      {copy.version_history.map((versionText, versionIndex) => {
                        const isOriginal = versionIndex === 0;
                        const isCurrent = versionIndex === copy.version_history.length - 1;
                        return (
                          <div key={versionIndex} className="rounded-xl border border-gray-700 bg-[var(--bg-primary)] p-4">
                            <div className="mb-2 flex items-center justify-between gap-3">
                              <span className="text-xs font-semibold text-gray-400">
                                {isOriginal ? "원본 카피" : `수정본 ${versionIndex}`}
                                {isCurrent ? " · 현재 사용 중" : ""}
                              </span>
                              <button
                                onClick={() => copyToClipboard(versionText)}
                                className="text-xs text-[var(--accent)] hover:opacity-80 transition-opacity"
                              >
                                복사
                              </button>
                            </div>
                            <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-200">
                              {versionText}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="max-h-60 overflow-y-auto mb-4 space-y-3 p-2">
                      {copy.chatHistory.map((message, messageIndex) => (
                        <div key={messageIndex} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                          <div
                            className={`px-4 py-2 rounded-2xl max-w-[80%] whitespace-pre-wrap text-sm leading-relaxed ${
                              message.role === "user"
                                ? "bg-[var(--accent)] text-white rounded-br-none"
                                : "glass-panel text-gray-200 rounded-bl-none"
                            }`}
                          >
                            {message.content}
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
                        onChange={(event) =>
                          setResults((prev) =>
                            prev.map((result, currentIndex) =>
                              currentIndex === index ? { ...result, refineInput: event.target.value } : result
                            )
                          )
                        }
                        onKeyDown={(event) => event.key === "Enter" && sendRefine(index)}
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

            {showPublishBanner && (
              <div className="glass-panel p-6 rounded-xl border-l-4 border-[var(--accent)]">
                <p className="text-sm text-gray-300 mb-3">
                  💡 게시물을 올린 후 링크를 알려주세요! 24시간 뒤 자동으로 AI가 학습합니다.
                </p>
                <div className="flex gap-2">
                  <input
                    value={publishUrl}
                    onChange={(event) => setPublishUrl(event.target.value)}
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
