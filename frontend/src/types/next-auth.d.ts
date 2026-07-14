import type { DefaultSession } from "next-auth";


declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & { id: string };
    tenantId: string;
    workspaceId: string;
    roles: string[];
    permissions: string[];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    subject?: string;
    tenantId?: string;
    workspaceId?: string;
    roles?: string[];
    permissions?: string[];
  }
}
