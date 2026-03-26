'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'

export default function AuthCallbackPage() {
  const router = useRouter()

  useEffect(() => {
    const handleAuthCallback = async () => {
      // Supabase 클라이언트가 URL 해시(#)의 토큰을 자동으로 감지하여 세션을 설정함
      const { data: { session }, error } = await supabase.auth.getSession()
      
      if (error) {
        console.error('Auth callback error:', error.message)
        router.push('/login?error=' + encodeURIComponent(error.message))
        return
      }

      if (session) {
        // 세션이 성공적으로 설정되면 메인 페이지로 이동
        router.push('/generate')
      } else {
        // 세션이 없으면 로그인 페이지로 (아직 로딩 중이거나 토큰이 없는 경우)
        // 약간의 대기 후 다시 시도하거나 로그인으로 보냄
        const timeout = setTimeout(() => {
          router.push('/login')
        }, 2000)
        return () => clearTimeout(timeout)
      }
    }

    handleAuthCallback()
  }, [router])

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <div className="w-12 h-12 border-4 border-[var(--accent)] border-t-transparent rounded-full animate-spin"></div>
      <p className="text-gray-400 font-medium animate-pulse">로그인 정보를 확인 중입니다...</p>
    </div>
  )
}
