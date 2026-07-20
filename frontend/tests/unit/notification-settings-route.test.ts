import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import {
  GET,
  PATCH,
  POST,
} from "../../src/app/api/product/[...path]/route";

describe("Product catch-all route methods", () => {
  it("exports PATCH through the same guarded BFF handler", () => {
    expect(PATCH).toBe(GET);
    expect(PATCH).toBe(POST);
  });
});
