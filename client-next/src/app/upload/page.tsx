"use client";
import { useState, useRef, useEffect } from "react";
import { apiUpload } from "@/lib/api";
import { showToast } from "@/components/layout/Toast";

export default function UploadPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && (dropped.name.endsWith(".xlsx") || dropped.name.endsWith(".csv"))) {
      setFile(dropped);
    } else {
      showToast("엑셀(.xlsx) 또는 CSV 파일만 가능합니다.", "error");
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const [jobId, setJobId] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);

  // Resume polling on refresh if job info exists
  useEffect(() => {
    const savedJobId = localStorage.getItem("last_bulk_job_id");
    if (savedJobId) {
      setJobId(savedJobId);
      startPolling(savedJobId);
    }
  }, []);

  const startPolling = async (bulkId: string) => {
    const { apiGet } = await import("@/lib/api");
    const interval = setInterval(async () => {
      try {
        const statusResult = await apiGet(`/upload/bulk-status/${bulkId}`);
        setTotalCount(statusResult.total_count);
        setProgress(`${statusResult.completed_count} / ${statusResult.total_count}건 생성 완료...`);
        
        if (statusResult.is_finished) {
           setProgress(`🎉 총 ${statusResult.total_count}건 생성 완료!`);
           clearInterval(interval);
           localStorage.removeItem("last_bulk_job_id");
        }
      } catch (e) {
          console.error(e);
      }
    }, 4000);

    // Stop after 30 mins
    setTimeout(() => clearInterval(interval), 1000 * 60 * 30);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress("파일 임시 저장 중...");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { apiUpload } = await import("@/lib/api");
      const result = await apiUpload("/upload/excel", formData);
      
      const bulkId = result.task_id;
      setJobId(bulkId);
      localStorage.setItem("last_bulk_job_id", bulkId);
      setProgress("데이터 분석 시작 중...");
      showToast("업로드가 완료되었습니다. 카피 대량 생성 작업이 백그라운드에서 시작되었습니다.");
      
      startPolling(bulkId);
      setFile(null);
    } catch (error: any) {
      setProgress("");
      showToast(`업로드 실패: ${error.message || "알 수 없는 오류"}`, "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-3xl font-bold mb-2">대량 카피 자동 생성 (Excel/CSV)</h2>
      <p className="text-gray-400 mb-8">
        스레드 등 소셜 미디어 게시물 URL 목록이 담긴 엑셀을 업로드하세요.<br/>
        문구와 성과를 <strong>자동으로 긁어와 학습</strong>한 뒤, 모든 URL에 대해 <strong>최적화된 카피를 대량으로 생성</strong>합니다.
      </p>

      {/* 드래그 & 드롭 영역 */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInput.current?.click()}
        className={`glass-panel rounded-2xl p-16 text-center cursor-pointer transition-all ${
          isDragging ? "border-2 border-[var(--accent)] bg-[var(--accent)]/5" : "border-2 border-dashed border-gray-700 hover:border-gray-500"
        }`}
      >
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,.csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="text-4xl mb-4">📤</div>
        {file ? (
          <div>
            <p className="text-lg font-bold text-[var(--accent)]">{file.name}</p>
            <p className="text-gray-400 text-sm mt-1">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        ) : (
          <div>
            <p className="text-lg font-semibold mb-2">여기에 파일을 드래그하세요</p>
            <p className="text-gray-500 text-sm">또는 클릭하여 파일 선택 (.xlsx, .csv)</p>
          </div>
        )}
      </div>

      {/* 업로드 버튼 */}
      {file && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="btn-primary w-full py-4 rounded-xl mt-6 text-lg"
        >
          {uploading ? "⏳ 처리 중..." : "🚀 업로드 시작"}
        </button>
      )}

      {/* 진행 상태 */}
      {(progress || jobId) && (
        <div className={`glass-panel p-6 rounded-xl mt-6 text-center ${jobId ? 'border border-[var(--accent)]/50 bg-[var(--accent)]/5' : ''}`}>
          <p className="text-sm font-bold text-white mb-2">
            {jobId && totalCount === 0 ? "⏳ 데이터 분석 중..." : progress}
          </p>
          {jobId && (
            <p className="text-xs text-gray-400">
              이 페이지를 벗어나도 백그라운드에서 계속 진행됩니다. 완성된 카피는 
              <a href="/mypage" className="text-[var(--accent)] underline ml-1">마이페이지 내 카피 보관함</a>
              에서 확인하세요.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
