import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export default async function globalTeardown() {
  if (process.env.PLAYWRIGHT_REUSE_EXISTING_STACK === "true") {
    return;
  }
  const repoRoot = path.resolve(__dirname, "../../..");
  await waitForPidFile(path.join(repoRoot, "data", "dev-server", "pids.json"), 15_000);
  execFileSync("python3", ["tools/local_stack/stop_local_stack.py", "--force-ports", "--kill-any-listener"], {
    cwd: repoRoot,
    stdio: "inherit"
  });
}

async function waitForPidFile(pidFile: string, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(pidFile)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}
