import { generateKeyPairSync, verify } from "node:crypto";
import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { issueInternalToken } from "../../src/lib/auth/internal-token";


describe("BFF internal token", () => {
  it("issues a 60-second RS256 token with only server-owned identity claims", () => {
    const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const privatePem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
    const now = new Date("2026-07-13T08:00:00Z");

    const token = issueInternalToken(
      {
        subject: "oidc|user-1",
        tenantId: "tenant-1",
        workspaceId: "workspace-1",
        roles: ["member"],
        permissions: ["analysis:read", "analysis:write"],
      },
      {
        privateKey: privatePem,
        keyId: "key-1",
        issuer: "https://product.example.com",
        audience: "crypto-alert-product-api",
        ttlSeconds: 60,
      },
      now,
      () => "request-1",
    );

    const [encodedHeader, encodedPayload, encodedSignature] = token.split(".");
    const header = decodePart(encodedHeader);
    const payload = decodePart(encodedPayload);
    const signature = Buffer.from(encodedSignature, "base64url");
    const valid = verify(
      "RSA-SHA256",
      Buffer.from(`${encodedHeader}.${encodedPayload}`),
      publicKey,
      signature,
    );

    expect(valid).toBe(true);
    expect(header).toEqual({ alg: "RS256", kid: "key-1", typ: "JWT" });
    expect(payload).toEqual({
      iss: "https://product.example.com",
      aud: "crypto-alert-product-api",
      sub: "oidc|user-1",
      tenant_id: "tenant-1",
      workspace_id: "workspace-1",
      roles: ["member"],
      permissions: ["analysis:read", "analysis:write"],
      jti: "request-1",
      iat: 1783929600,
      exp: 1783929660,
    });
  });

  it("rejects incomplete identities before signing", () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

    expect(() => issueInternalToken(
      {
        subject: "",
        tenantId: "tenant-1",
        workspaceId: "workspace-1",
        roles: ["member"],
        permissions: ["analysis:read"],
      },
      {
        privateKey: privateKey.export({ type: "pkcs8", format: "pem" }).toString(),
        keyId: "key-1",
        issuer: "https://product.example.com",
        audience: "crypto-alert-product-api",
        ttlSeconds: 60,
      },
    )).toThrow("identity");
  });

  it("rejects token lifetimes above 60 seconds", () => {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

    expect(() => issueInternalToken(
      {
        subject: "oidc|user-1",
        tenantId: "tenant-1",
        workspaceId: "workspace-1",
        roles: ["member"],
        permissions: ["analysis:read"],
      },
      {
        privateKey: privateKey.export({ type: "pkcs8", format: "pem" }).toString(),
        keyId: "key-1",
        issuer: "https://product.example.com",
        audience: "crypto-alert-product-api",
        ttlSeconds: 61,
      },
    )).toThrow("Internal token TTL must be between 1 and 60 seconds");
  });
});


function decodePart(value: string | undefined): Record<string, unknown> {
  if (!value) throw new Error("Missing JWT part");
  return JSON.parse(Buffer.from(value, "base64url").toString("utf8")) as Record<string, unknown>;
}
