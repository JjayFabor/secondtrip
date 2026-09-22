import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE_NAME = "st_session";

function applyAppSecurityHeaders(response: NextResponse): NextResponse {
  response.headers.set("Cache-Control", "private, no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-Robots-Tag", "noindex, nofollow");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  return response;
}

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE_NAME)) {
    return applyAppSecurityHeaders(NextResponse.next());
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.search = "";
  loginUrl.searchParams.set(
    "next",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );

  return applyAppSecurityHeaders(NextResponse.redirect(loginUrl));
}

export const config = {
  matcher: ["/app/:path*"],
};
