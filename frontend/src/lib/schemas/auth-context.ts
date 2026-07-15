import { z } from "zod";


export const authContextSchema = z.object({
  context_id: z.string().uuid(),
  tenant_id: z.string().min(1).max(255),
  tenant_name: z.string().min(1).max(255),
  workspace_id: z.string().min(1).max(255),
  workspace_name: z.string().min(1).max(255),
  role: z.string().min(1).max(64),
  permissions: z.array(z.string().min(1)),
  version: z.string().min(1).max(64),
}).strict();

export const authContextListSchema = z.object({
  items: z.array(authContextSchema),
}).strict();

export type AuthContext = z.infer<typeof authContextSchema>;
