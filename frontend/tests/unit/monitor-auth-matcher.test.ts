import { describe, expect, it, vi } from "vitest";

vi.mock("next-auth/jwt", () => ({ getToken: vi.fn(async () => null) }));

import { config } from "../../src/proxy";

describe("Monitor authenticated routes", () => {
  it("covers Home, Artifacts, and Monitors in the product auth matcher", () => {
    expect(config.matcher).toEqual(expect.arrayContaining([
      "/home/:path*",
      "/artifacts/:path*",
      "/monitors/:path*",
    ]));
  });
});
