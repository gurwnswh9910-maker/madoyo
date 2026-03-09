"use client";
import { useState, useRef } from "react";
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

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress("파일 업로드 중...");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await apiUpload("/upload/excel", formData);
      setProgress("✅ 처리 완료!");
      showToast(`데이터가 성공적으로 업로드되었습니다! (task: ${result.task_id || "완료"})`);
      setFile(null);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "업로드 실패";
      setProgress("");
      showToast(`업로드 실패: ${msg}`, "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-3xl font-bold mb-2">데이터 업로드</h2>
      <p className="text-gray-400 mb-8">엑셀 파일을 업로드하면 AI 학습 데이터에 추가됩니다.</p>

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
      {progress && (
        <div className="glass-panel p-4 rounded-xl mt-4 text-center text-sm">
          {progress}
        </div>
      )}
    </div>
  );
}
