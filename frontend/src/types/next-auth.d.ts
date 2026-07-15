import type { DefaultSession } from "next-auth";


declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & { id: string };
    identityIssuer: string;
    contextId: string;
    contextVersion: string;
    tenantId: string;
    tenantName: string;
    workspaceId: string;
    workspaceName: string;
    roles: string[];
    permissions: string[];
    authContextError: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    subject?: string;
    identityIssuer?: string;
    contextId?: string;
    contextVersion?: string;
    tenantId?: string;
    tenantName?: string;
    workspaceId?: string;
    workspaceName?: string;
    roles?: string[];
    permissions?: string[];
    authContextError?: string;
  }
}
