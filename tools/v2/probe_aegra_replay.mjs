#!/usr/bin/env node

import { createRequire } from "node:module";
import path from "node:path";


function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}


async function nextWithDeadline(iterator, timeoutMs) {
  let timer;
  try {
    return await Promise.race([
      iterator.next(),
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("SSE replay event deadline exceeded")),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}


async function main() {
  const root = path.resolve(import.meta.dirname, "../..");
  const frontendRequire = createRequire(path.join(root, "frontend/package.json"));
  const { ProtocolSseTransportAdapter } = frontendRequire(
    "@langchain/langgraph-sdk",
  );
  if (typeof ProtocolSseTransportAdapter !== "function") {
    throw new Error("official ProtocolSseTransportAdapter is unavailable");
  }
  const apiUrl = requiredEnvironment("AEGRA_PROBE_URL");
  const threadId = requiredEnvironment("AEGRA_PROBE_THREAD_ID");
  const token = requiredEnvironment("AEGRA_PROBE_TOKEN");

  async function collect(since) {
    const transport = new ProtocolSseTransportAdapter({
      apiUrl,
      threadId,
      defaultHeaders: { authorization: `Bearer ${token}` },
      maxReconnectAttempts: 0,
    });
    const handle = transport.openEventStream({
      channels: ["values", "custom", "lifecycle"],
      namespaces: [[]],
      depth: 1,
      since,
    });
    await handle.ready;
    const iterator = handle.events[Symbol.asyncIterator]();
    const events = [];
    for (let index = 0; index < 100; index += 1) {
      const item = await nextWithDeadline(iterator, 10_000);
      if (item.done) break;
      const event = item.value;
      events.push(event);
      if (
        event.method === "lifecycle" &&
        event.params?.data?.event === "completed"
      ) {
        break;
      }
    }
    handle.close();
    await transport.close();
    return events;
  }

  const first = await collect(0);
  if (first.length < 3) {
    throw new Error(`expected replay events, received ${first.length}`);
  }
  for (let index = 1; index < first.length; index += 1) {
    if (first[index].seq <= first[index - 1].seq) {
      throw new Error("SSE replay sequence is not monotonic");
    }
  }
  const since = first[0].seq;
  const replay = await collect(since);
  const expected = first.filter((event) => event.seq > since);
  if (replay.length !== expected.length) {
    throw new Error(
      `since replay returned ${replay.length} events; expected ${expected.length}`,
    );
  }
  for (let index = 0; index < expected.length; index += 1) {
    const left = expected[index];
    const right = replay[index];
    if (
      left.seq !== right.seq ||
      left.event_id !== right.event_id ||
      left.method !== right.method
    ) {
      throw new Error(`since replay identity diverged at index ${index}`);
    }
  }
  process.stdout.write(
    `${JSON.stringify({
      schema_version: "1.0",
      first_event_count: first.length,
      replay_event_count: replay.length,
      since,
      first_seq: first[0].seq,
      last_seq: first.at(-1).seq,
      identity_match: true,
    })}\n`,
  );
}


main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
