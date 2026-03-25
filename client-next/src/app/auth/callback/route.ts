import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const requestUrl = new URL(request.url)
  const code = requestUrl.searchParams.get('code')

  if (code) {
    // Supabase OAuth callback: code는 클라이언트에서 자동으로 처리됨
    // auth-context.tsx의 onAuthStateChange가 세션을 감지하여 로그인 처리
    // 여기서는 프론트엔드로 리다이렉트만 수행
    return NextResponse.redirect(new URL(`/generate?code=${code}`, requestUrl.origin))
  }

  // code가 없으면 로그인 페이지로
  return NextResponse.redirect(new URL('/login', requestUrl.origin))
}
