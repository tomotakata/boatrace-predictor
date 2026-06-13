const BASIC_USER = 'admin'
const BASIC_PASS = 'boatrace2026'

function unauthorized() {
  return new Response('Authentication required', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Protected", charset="UTF-8"',
      'Cache-Control': 'no-store',
    },
  })
}

export default function middleware(request: Request) {
  const auth = request.headers.get('authorization')
  if (!auth || !auth.startsWith('Basic ')) {
    return unauthorized()
  }

  try {
    const encoded = auth.slice(6)
    const decoded = atob(encoded)
    const separatorIndex = decoded.indexOf(':')
    if (separatorIndex === -1) {
      return unauthorized()
    }

    const username = decoded.slice(0, separatorIndex)
    const password = decoded.slice(separatorIndex + 1)

    if (username !== BASIC_USER || password !== BASIC_PASS) {
      return unauthorized()
    }
  } catch {
    return unauthorized()
  }

  return fetch(request)
}

export const config = {
  matcher: '/:path*',
}