import { getToken } from "next-auth/jwt";
import { NextRequest, NextResponse } from "next/server";

import { requiresAuthenticatedRuntime } from "@/lib/runtime/app-environment";


export async function proxy(request: NextRequest) {
  if (!requiresAuthenticatedRuntime()) {
    return NextResponse.next();
  }
  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET });
  if (token) return NextResponse.next();

  const canonicalOrigin = canonicalFrontendOrigin();
  if (canonicalOrigin === null) {
    return NextResponse.json(
      { detail: "Authenticated runtime is not configured." },
      { status: 503 },
    );
  }
  const callback = new URL(
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
    canonicalOrigin,
  );
  const signIn = new URL("/api/auth/signin", canonicalOrigin);
  signIn.searchParams.set("callbackUrl", callback.toString());
  return NextResponse.redirect(signIn);
}

function canonicalFrontendOrigin(): URL | null {
  const configured = process.env.NEXTAUTH_URL;
  if (!configured) return null;
  try {
    const url = new URL(configured);
    if (
      url.protocol !== "https:"
      || url.username
      || url.password
      || url.search
      || url.hash
    ) return null;
    return new URL(url.origin);
  } catch {
    return null;
  }
}

export const config = {
  matcher: [
    "/home/:path*",
    "/work/:path*",
    "/runs/:path*",
    "/inbox/:path*",
    "/library/:path*",
    "/artifacts/:path*",
    "/monitors/:path*",
    "/settings/:path*",
  ],
};
