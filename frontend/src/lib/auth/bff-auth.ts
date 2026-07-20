import "server-only";

import { getServerSession } from "next-auth/next";
import type { Session } from "next-auth";

import { authOptions } from "@/lib/auth/auth-options";
import {
  IDENTITY_DISCOVERY_AUDIENCE,
  internalTokenConfig,
  issueIdentityToken,
  issueScopedToken,
  type InternalIdentity,
  type ScopedInternalIdentity,
} from "@/lib/auth/internal-token";


type SessionResolver = () => Promise<Session | null>;

interface InternalAuthorizationOptions {
  audience?: string;
  allowDevelopmentBootstrap?: boolean;
}

export async function resolveInternalAuthorization(
  _request: Request,
  resolveSession: SessionResolver = () => getServerSession(authOptions),
  options: InternalAuthorizationOptions = {},
): Promise<string | null> {
  const identity = scopedSessionIdentity(await resolveSession());
  if (identity === null) return null;
  const audience = options.audience
    ?? process.env.INTERNAL_JWT_AUDIENCE
    ?? "crypto-alert-product-api";
  return `Bearer ${issueScopedToken(identity, internalTokenConfig(audience))}`;
}

export function developmentBootstrapAuthorization(
  audience: string,
): string | null {
  if (!isDevelopmentBootstrapRuntime()) return null;
  const subject = process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT?.trim();
  const identityIssuer = process.env.DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER?.trim();
  const contextId = process.env.DEVELOPMENT_BOOTSTRAP_CONTEXT_ID?.trim();
  if (
    !subject
    || !identityIssuer
    || !contextId
    || !uuidPattern.test(contextId)
  ) return null;
  try {
    return `Bearer ${issueScopedToken(
      { subject, identityIssuer, contextId },
      internalTokenConfig(audience),
    )}`;
  } catch {
    return null;
  }
}

export function developmentBootstrapIdentityAuthorization(): string | null {
  if (!isDevelopmentBootstrapRuntime()) return null;
  const subject = process.env.DEVELOPMENT_BOOTSTRAP_SUBJECT?.trim();
  const identityIssuer = process.env.DEVELOPMENT_BOOTSTRAP_IDENTITY_ISSUER?.trim();
  if (!subject || !identityIssuer) return null;
  try {
    return `Bearer ${issueIdentityToken(
      { subject, identityIssuer },
      internalTokenConfig(IDENTITY_DISCOVERY_AUDIENCE),
    )}`;
  } catch {
    return null;
  }
}

export async function resolveIdentityAuthorization(
  _request: Request,
  resolveSession: SessionResolver = () => getServerSession(authOptions),
): Promise<string | null> {
  const identity = sessionIdentity(await resolveSession());
  if (identity === null) return null;
  return `Bearer ${issueIdentityToken(
    identity,
    internalTokenConfig(IDENTITY_DISCOVERY_AUDIENCE),
  )}`;
}

function sessionIdentity(session: Session | null): InternalIdentity | null {
  if (!session?.user?.id || !session.identityIssuer) return null;
  return {
    subject: session.user.id,
    identityIssuer: session.identityIssuer,
  };
}

function scopedSessionIdentity(session: Session | null): ScopedInternalIdentity | null {
  const identity = sessionIdentity(session);
  if (identity === null || !session?.contextId) return null;
  return { ...identity, contextId: session.contextId };
}

export function isDevelopmentBootstrapRuntime(): boolean {
  return process.env.APP_ENVIRONMENT === "development"
    && process.env.DEVELOPMENT_BOOTSTRAP_ENABLED === "true"
    && process.env.DEVELOPMENT_BOOTSTRAP_PROFILE === "local-proof";
}

const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
