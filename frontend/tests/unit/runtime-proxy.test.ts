import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next-auth/jwt", () => ({
  getToken: vi.fn(async () => null),
}));

import { config, proxy } from "../../src/proxy";


describe("authenticated runtime proxy", () => {
  afterEach(() => {
    delete process.env.APP_ENVIRONMENT;
    delete process.env.NEXTAUTH_SECRET;
    delete process.env.NEXTAUTH_URL;
  });

  it("builds sign-in redirects only from the configured canonical origin", async () => {
    process.env.APP_ENVIRONMENT = "production";
    process.env.NEXTAUTH_SECRET = "test-only-nextauth-secret";
    process.env.NEXTAUTH_URL = "https://product.example.com";
    const request = new NextRequest(
      "https://attacker-controlled.example/work?task=task-1",
    );

    const response = await proxy(request);

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.origin).toBe("https://product.example.com");
    expect(location.pathname).toBe("/api/auth/signin");
    expect(location.searchParams.get("callbackUrl")).toBe(
      "https://product.example.com/work?task=task-1",
    );
  });

  it("fails closed when a strict runtime has no canonical frontend URL", async () => {
    process.env.APP_ENVIRONMENT = "production";
    process.env.NEXTAUTH_SECRET = "test-only-nextauth-secret";

    const response = await proxy(new NextRequest("https://attacker.example/work"));

    expect(response.status).toBe(503);
    expect(response.headers.get("location")).toBeNull();
  });

  it("covers every authenticated product page", () => {
    expect(config.matcher).toEqual([
      "/work/:path*",
      "/runs/:path*",
      "/inbox/:path*",
      "/library/:path*",
      "/settings/:path*",
    ]);
  });
});
