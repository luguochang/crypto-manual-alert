import "server-only";

import {
  IDENTITY_DISCOVERY_AUDIENCE,
  internalTokenConfig,
  issueIdentityToken,
  type InternalIdentity,
} from "@/lib/auth/internal-token";
import {
  authContextListSchema,
  authContextSchema,
  type AuthContext,
} from "@/lib/schemas/auth-context";


type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export async function listMembershipContexts(
  identity: InternalIdentity,
  fetcher: Fetcher = fetch,
): Promise<AuthContext[]> {
  const response = await fetcher(productUrl("api/v2/auth/contexts"), {
    method: "GET",
    headers: identityHeaders(identity),
    cache: "no-store",
    redirect: "manual",
  });
  if (!response.ok) throw new Error("Membership context discovery failed");
  return authContextListSchema.parse(await response.json()).items;
}

export async function selectMembershipContext(
  identity: InternalIdentity,
  contextId: string,
  fetcher: Fetcher = fetch,
): Promise<AuthContext> {
  const response = await fetcher(productUrl("api/v2/auth/context/select"), {
    method: "POST",
    headers: {
      ...identityHeaders(identity),
      "content-type": "application/json",
    },
    body: JSON.stringify({ context_id: contextId }),
    cache: "no-store",
    redirect: "manual",
  });
  if (!response.ok) throw new Error("Membership context selection failed");
  return authContextSchema.parse(await response.json());
}

function identityHeaders(identity: InternalIdentity): Record<string, string> {
  const token = issueIdentityToken(
    identity,
    internalTokenConfig(IDENTITY_DISCOVERY_AUDIENCE),
  );
  return {
    accept: "application/json",
    authorization: `Bearer ${token}`,
  };
}

function productUrl(path: string): string {
  const configured = process.env.PRODUCT_API_BASE_URL ?? "http://127.0.0.1:8123/app";
  const base = new URL(configured.endsWith("/") ? configured : `${configured}/`);
  if (
    !["http:", "https:"].includes(base.protocol)
    || base.username
    || base.password
    || base.search
    || base.hash
  ) {
    throw new Error("Invalid Product API URL");
  }
  return new URL(path, base).toString();
}
