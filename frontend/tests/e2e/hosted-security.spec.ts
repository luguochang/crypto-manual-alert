import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";


requireFlag("HOSTED_SECURITY_E2E");
const matrixPath = requiredEnvironment("HOSTED_SECURITY_MATRIX_FILE");
const evidenceDirectory = requiredEnvironment("PLAYWRIGHT_EVIDENCE_DIR");
if (!path.isAbsolute(matrixPath) || !path.isAbsolute(evidenceDirectory)) {
  throw new Error("hosted security matrix and evidence paths must be absolute");
}
const matrix = parseMatrix(matrixPath);

test("hosted OIDC actor matrix enforces every declared Product boundary", async ({ browser }, testInfo) => {
  const baseURL = String(testInfo.project.use.baseURL ?? "");
  assertPublicHttps(baseURL);
  const observed: Array<{actor: string; operation: string; status: number}> = [];

  for (const actor of matrix.actors) {
    const context = await browser.newContext({baseURL, storageState: actor.storageState});
    const page = await context.newPage();
    try {
      for (const candidate of actor.cases) {
        const result = await productFetch(page, candidate);
        expect(result.status, `${actor.name}:${candidate.operation}`).toBe(candidate.expectedStatus);
        if (candidate.nonDisclosure) expect([403, 404]).toContain(result.status);
        observed.push({actor: actor.name, operation: candidate.operation, status: result.status});
      }
    } finally {
      await context.close();
    }
  }

  expect(new Set(matrix.actors.map((actor) => actor.role))).toEqual(new Set([
    "owner", "peer", "cross_tenant", "revoked", "operator",
  ]));
  expect(new Set(matrix.actors.flatMap((actor) => actor.cases.map((candidate) => candidate.operation))))
    .toEqual(new Set([
      "list", "read", "write", "resume", "respond", "cancel", "retry", "fork",
      "feedback", "export", "delete",
    ]));
  await testInfo.attach("hosted-security-observed-matrix", {
    body: JSON.stringify(observed),
    contentType: "application/json",
  });
});

interface MatrixCase {
  operation: string;
  method: "GET" | "POST";
  path: string;
  expectedStatus: number;
  nonDisclosure?: boolean;
  body?: unknown;
}

interface MatrixActor {
  name: string;
  role: "owner" | "peer" | "cross_tenant" | "revoked" | "operator";
  storageState: string;
  cases: MatrixCase[];
}

function parseMatrix(filePath: string): {actors: MatrixActor[]} {
  const value = JSON.parse(fs.readFileSync(filePath, "utf8")) as {actors?: MatrixActor[]};
  if (!Array.isArray(value.actors) || value.actors.length !== 5) throw new Error("security matrix requires five actors");
  for (const actor of value.actors) {
    if (!path.isAbsolute(actor.storageState) || !Array.isArray(actor.cases) || actor.cases.length === 0) {
      throw new Error("each security actor requires an absolute storageState and cases");
    }
  }
  return {actors: value.actors};
}

async function productFetch(page: Page, candidate: MatrixCase) {
  return page.evaluate(async (entry) => {
    const response = await fetch(`/api/product${entry.path}`, {
      method: entry.method,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        accept: "application/json",
        ...(entry.body === undefined ? {} : {"content-type": "application/json"}),
        ...(entry.method === "POST" ? {"idempotency-key": crypto.randomUUID()} : {}),
      },
      body: entry.body === undefined ? undefined : JSON.stringify(entry.body),
    });
    return {status: response.status};
  }, candidate);
}

function assertPublicHttps(value: string) {
  const url = new URL(value);
  if (url.protocol !== "https:" || ["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error("hosted security requires a public https:// origin, never localhost or 127.0.0.1");
  }
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function requireFlag(name: string) {
  if (process.env[name] !== "1") throw new Error(`${name}=1 is required`);
}
