"use client";
import { useState, useEffect } from "react";

interface ToastData {
  message: string;
  type: "success" | "error";
}

let showToastFn: ((msg: string, type?: "success" | "error") => void) | null = null;

export function showToast(message: string, type: "success" | "error" = "success") {
  if (showToastFn) showToastFn(message, type);
}

export default function Toast() {
  const [toast, setToast] = useState<ToastData | null>(null);

  useEffect(() => {
    showToastFn = (message: string, type: "success" | "error" = "success") => {
      setToast({ message, type });
      setTimeout(() => setToast(null), 3000);
    };
    return () => { showToastFn = null; };
  }, []);

  if (!toast) return null;
  return (
    <div className={`toast ${toast.type}`}>
      <span>{toast.type === "error" ? "❌" : "✅"}</span>
      <span>{toast.message}</span>
    </div>
  );
}
