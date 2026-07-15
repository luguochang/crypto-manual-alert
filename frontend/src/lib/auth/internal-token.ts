import "server-only";

import { randomUUID, sign } from "node:crypto";
import { readFileSync } from "node:fs";


export const IDENTITY_DISCOVERY_AUDIENCE = "crypto-alert-identity-discovery";

export interface InternalIdentity {
  subject: string;
  identityIssuer: string;
}

export interface ScopedInternalIdentity extends InternalIdentity {
  contextId: string;
}

export interface InternalTokenConfig {
  privateKey: string;
  keyId: string;
  issuer: string;
  audience: string;
  ttlSeconds: number;
}

export function issueIdentityToken(
  identity: InternalIdentity,
  config: InternalTokenConfig,
  now: Date = new Date(),
  createTokenId: () => string = randomUUID,
): string {
  if (config.audience !== IDENTITY_DISCOVERY_AUDIENCE) {
    throw new Error("Identity discovery tokens require the discovery audience");
  }
  return issueToken(
    identity,
    { token_use: "identity_discovery" },
    config,
    now,
    createTokenId,
  );
}

export function issueScopedToken(
  identity: ScopedInternalIdentity,
  config: InternalTokenConfig,
  now: Date = new Date(),
  createTokenId: () => string = randomUUID,
): string {
  if (!uuidPattern.test(identity.contextId)) {
    throw new Error("A valid server-owned authorization context is required");
  }
  return issueToken(
    identity,
    { token_use: "user", context_id: identity.contextId },
    config,
    now,
    createTokenId,
  );
}

export function internalTokenConfig(audience: string): InternalTokenConfig {
  const privateKeyFile = process.env.INTERNAL_JWT_PRIVATE_KEY_FILE;
  const privateKey = process.env.INTERNAL_JWT_PRIVATE_KEY?.replace(/\\n/g, "\n")
    ?? (privateKeyFile ? readFileSync(privateKeyFile, "utf8") : "");
  return {
    privateKey,
    keyId: process.env.INTERNAL_JWT_KID ?? "",
    issuer: process.env.INTERNAL_JWT_ISSUER ?? "",
    audience,
    ttlSeconds: 60,
  };
}

function issueToken(
  identity: InternalIdentity,
  claims: Record<string, unknown>,
  config: InternalTokenConfig,
  now: Date,
  createTokenId: () => string,
): string {
  validateIdentity(identity);
  validateConfig(config);
  const issuedAt = Math.floor(now.getTime() / 1000);
  const header = encodeJson({ alg: "RS256", kid: config.keyId, typ: "JWT" });
  const payload = encodeJson({
    iss: config.issuer,
    aud: config.audience,
    sub: identity.subject,
    identity_issuer: identity.identityIssuer,
    ...claims,
    jti: createTokenId(),
    iat: issuedAt,
    exp: issuedAt + config.ttlSeconds,
  });
  const signingInput = `${header}.${payload}`;
  const signature = sign(
    "RSA-SHA256",
    Buffer.from(signingInput),
    config.privateKey,
  ).toString("base64url");
  return `${signingInput}.${signature}`;
}

function validateIdentity(identity: InternalIdentity) {
  if (!identity.subject.trim() || !identity.identityIssuer.trim()) {
    throw new Error("Complete server-owned identity claims are required");
  }
}

function validateConfig(config: InternalTokenConfig) {
  if (
    !Number.isInteger(config.ttlSeconds)
    || config.ttlSeconds < 1
    || config.ttlSeconds > 60
  ) {
    throw new Error("Internal token TTL must be between 1 and 60 seconds");
  }
  if (
    !config.privateKey.trim()
    || !config.keyId.trim()
    || !config.issuer.trim()
    || !config.audience.trim()
  ) {
    throw new Error("Valid internal token configuration is required");
  }
}

function encodeJson(value: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
