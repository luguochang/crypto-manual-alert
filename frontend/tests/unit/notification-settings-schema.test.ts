import { describe, expect, it } from "vitest";

import {
  notificationSettingsSchema,
  notificationSettingsUpdateSchema,
} from "../../src/lib/schemas/product-api";

describe("Notification settings schemas", () => {
  it("strictly parses the public Bark settings view without a credential", () => {
    expect(notificationSettingsSchema.parse({
      channel: "bark",
      enabled: true,
      configured: true,
      updated_at: "2026-07-16T08:30:00Z",
    })).toEqual({
      channel: "bark",
      enabled: true,
      configured: true,
      updated_at: "2026-07-16T08:30:00Z",
    });

    expect(() => notificationSettingsSchema.parse({
      channel: "bark",
      enabled: true,
      configured: true,
      updated_at: "2026-07-16T08:30:00Z",
      device_key: "must-never-be-returned",
    })).toThrow();
  });

  it("rejects an enabled but unconfigured destination", () => {
    expect(() => notificationSettingsSchema.parse({
      channel: "bark",
      enabled: true,
      configured: false,
      updated_at: null,
    })).toThrow();
  });

  it("accepts only enabled and an optional bounded replacement key", () => {
    expect(notificationSettingsUpdateSchema.parse({
      enabled: false,
      device_key: "  bark-device-key  ",
    })).toEqual({
      enabled: false,
      device_key: "bark-device-key",
    });
    expect(notificationSettingsUpdateSchema.parse({ enabled: true })).toEqual({
      enabled: true,
    });
    expect(() => notificationSettingsUpdateSchema.parse({
      enabled: true,
      device_key: "short",
    })).toThrow();
    expect(() => notificationSettingsUpdateSchema.parse({
      enabled: true,
      credential_ciphertext: "client-owned",
    })).toThrow();
  });
});
