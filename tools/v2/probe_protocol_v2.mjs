#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";

const EX_USAGE = 64;
const EX_DATAERR = 65;
const EX_UNAVAILABLE = 69;
const EX_SOFTWARE = 70;
const EX_CONFIG = 78;

const ROOT_CHANNELS = Object.freeze([
  "values",
  "checkpoints",
  "lifecycle",
  "input",
  "messages",
  "tools",
]);
const ROOT_SUBSCRIPTION = Object.freeze({
  channels: ROOT_CHANNELS,
  namespaces: [[]],
  depth: 1,
});
const APPROVE_RESPONSE = Object.freeze({
  action: "approve",
  edits: null,
  comment: null,
});

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const rootDirectory = path.resolve(scriptDirectory, "../..");
const frontendDirectory = path.join(rootDirectory, "frontend");
const frontendRequire = createRequire(path.join(frontendDirectory, "package.json"));

class ProbeError extends Error {
  constructor(message, exitCode = EX_SOFTWARE, options = undefined) {
    super(message, options);
    this.name = "ProbeError";
    this.exitCode = exitCode;
  }
}

function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new ProbeError(`${name} is required`, EX_USAGE);
  }
  return value;
}

function positiveIntegerEnvironment(name, fallback) {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  if (!/^\d+$/.test(raw) || Number(raw) < 1) {
    throw new ProbeError(`${name} must be a positive integer`, EX_USAGE);
  }
  return Number(raw);
}

function validatedAgentUrl(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch (error) {
    throw new ProbeError("TASK8_AGENT_URL must be an absolute HTTP(S) URL", EX_USAGE, {
      cause: error,
    });
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new ProbeError(
      "TASK8_AGENT_URL must be an HTTP(S) URL without credentials, query, or fragment",
      EX_USAGE,
    );
  }
  return url.toString().replace(/\/$/, "");
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sanitizeError(value) {
  const rendered = value instanceof Error ? value.message : String(value);
  return rendered
    .replace(/(authorization\s*[:=]\s*bearer\s+)[^\s,;]+/gi, "$1[REDACTED]")
    .replace(/(bearer\s+)[A-Za-z0-9._~+\/-]+/gi, "$1[REDACTED]")
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, "[REDACTED]");
}

function errorChain(error) {
  const values = [];
  let current = error;
  for (let index = 0; index < 6 && current != null; index += 1) {
    values.push(current);
    current = isRecord(current) ? current.cause : undefined;
  }
  return values;
}

function endpointFailure(error) {
  return errorChain(error).some((item) => {
    const code = isRecord(item) && typeof item.code === "string" ? item.code : "";
    const message = sanitizeError(item);
    return (
      ["ECONNREFUSED", "ECONNRESET", "ENETUNREACH", "ENOTFOUND", "EAI_AGAIN"].includes(code) ||
      /fetch failed|connection refused|failed to connect|network is unreachable/i.test(message)
    );
  });
}

async function withDeadline(promise, label, timeoutMs) {
  let timeout;
  const deadline = new Promise((_, reject) => {
    timeout = setTimeout(() => {
      reject(new ProbeError(`${label} exceeded ${timeoutMs} ms`));
    }, timeoutMs);
  });
  try {
    return await Promise.race([promise, deadline]);
  } finally {
    clearTimeout(timeout);
  }
}

async function nextEvent(iterator, label, timeoutMs) {
  const result = await withDeadline(iterator.next(), label, timeoutMs);
  if (result.done) {
    throw new ProbeError(`${label} ended before the required event arrived`);
  }
  return result.value;
}

function validateEvent(event, previousSequence, label) {
  if (!isRecord(event) || event.type !== "event") {
    throw new ProbeError(`${label} returned a non-Protocol event`);
  }
  if (!Number.isSafeInteger(event.seq) || event.seq < 0) {
    throw new ProbeError(`${label} returned an event without a valid monotonic seq`);
  }
  if (previousSequence != null && event.seq <= previousSequence) {
    throw new ProbeError(
      `${label} ordering regressed from seq ${previousSequence} to ${event.seq}`,
    );
  }
  if (!isRecord(event.params) || !Array.isArray(event.params.namespace)) {
    throw new ProbeError(`${label} returned an event without a Protocol namespace`);
  }
  return event.seq;
}

async function collectUntil(iterator, predicate, label, timeoutMs, afterSequence = undefined) {
  const events = [];
  let previousSequence = afterSequence;
  for (let count = 0; count < 500; count += 1) {
    const event = await nextEvent(iterator, label, timeoutMs);
    previousSequence = validateEvent(event, previousSequence, label);
    events.push(event);
    if (predicate(event, events)) {
      return { events, lastSequence: previousSequence };
    }
  }
  throw new ProbeError(`${label} exceeded the 500-event safety bound`);
}

function isRootNamespace(event) {
  return Array.isArray(event.params?.namespace) && event.params.namespace.length === 0;
}

function isRootLifecycle(event, status) {
  const lifecycleNamespace = event.params?.data?.namespace;
  return (
    event.method === "lifecycle" &&
    isRootNamespace(event) &&
    isRecord(event.params?.data) &&
    event.params.data.event === status &&
    (!Array.isArray(lifecycleNamespace) || lifecycleNamespace.length === 0)
  );
}

function inputRequest(event) {
  if (event.method !== "input.requested" || !isRecord(event.params?.data)) {
    return null;
  }
  const interruptId = event.params.data.interrupt_id;
  if (typeof interruptId !== "string" || !interruptId) {
    throw new ProbeError("input.requested did not include an interrupt_id");
  }
  return {
    interruptId,
    namespace: [...event.params.namespace],
  };
}

function uniqueInterrupts(events) {
  const pending = new Map();
  for (const event of events) {
    const request = inputRequest(event);
    if (request == null) continue;
    const key = `${JSON.stringify(request.namespace)}\u0000${request.interruptId}`;
    pending.set(key, request);
  }
  return [...pending.values()];
}

function protocolCheckpointId(events) {
  const checkpoints = events.filter(
    (event) =>
      event.method === "checkpoints" &&
      isRootNamespace(event) &&
      isRecord(event.params?.data),
  );
  const value = checkpoints.at(-1)?.params.data.id;
  return typeof value === "string" && value ? value : undefined;
}

function stateCheckpointId(state) {
  const value = state?.checkpoint?.checkpoint_id;
  if (typeof value !== "string" || !value) {
    throw new ProbeError("official Thread state did not expose a root checkpoint_id");
  }
  return value;
}

function canonicalSeedState() {
  const analysis = {
    regime: "risk_on",
    horizon: "4h",
    risk_pct: "0.1",
    target_1: "66000",
    target_2: "67000",
    instrument: "BTC-USDT-SWAP",
    stop_price: "64500",
    main_action: "open_long",
    probability: 0.65,
    total_score: 2,
    invalidation: "Close below 64500.",
    max_leverage: 2,
    entry_trigger: "65100",
    factor_scores: { macro: 0, derivatives: 1, market_structure: 1 },
    reference_price: "65000.25",
    root_cause_chain: [
      "Price reclaimed resistance",
      "Liquidity supports continuation",
    ],
    unavailable_data: [],
    why_not_opposite: "The bearish invalidation has not triggered.",
    expires_in_seconds: 90,
    position_size_class: "light",
    manual_execution_required: true,
  };
  const evidenceVerdict = {
    warnings: [],
    sufficient: true,
    confidence_cap: 1,
    missing_optional: [],
    missing_required: [],
  };
  const riskVerdict = {
    allowed: true,
    warnings: [],
    confidence_cap: 1,
    blocked_reasons: [],
  };
  return {
    request: {
      symbol: "BTC-USDT-SWAP",
      horizon: "4h",
      query_text: "Validate the Task 8 official Protocol interrupt path.",
      notify: false,
    },
    analysis,
    evidence_verdict: evidenceVerdict,
    risk_verdict: riskVerdict,
    artifact: {
      status: "draft",
      analysis,
      risk_verdict: riskVerdict,
      artifact_type: "analysis_report",
      schema_version: "1.0",
      content_version: 1,
      evidence_verdict: evidenceVerdict,
      source_references: ["https://www.reuters.com/markets/currencies/"],
    },
    web_evidence: [],
    review_policy: "required",
    review_iteration: 0,
    terminal_status: "running",
    errors: [],
    lifecycle: "artifact_built",
  };
}

async function waitForCommittedState(client, threadId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = "missing";
  while (Date.now() < deadline) {
    const state = await client.threads.getState(threadId, undefined, {
      signal: AbortSignal.timeout(Math.min(timeoutMs, 5_000)),
    });
    const values = isRecord(state.values) ? state.values : {};
    lastStatus = typeof values.terminal_status === "string" ? values.terminal_status : "missing";
    if (lastStatus === "succeeded") {
      if (!isRecord(values.artifact) || values.artifact.status !== "committed") {
        throw new ProbeError("completed probe state did not contain a committed Artifact");
      }
      return;
    }
    if (["blocked", "failed", "cancelled"].includes(lastStatus)) {
      throw new ProbeError(`probe Run reached unexpected terminal status ${lastStatus}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new ProbeError(
    `probe Run did not persist succeeded state before the deadline (last=${lastStatus})`,
  );
}

async function createPausedCanonicalThread({
  client,
  graphId,
  assistantId,
  label,
  timeoutMs,
  createdThreads,
  openStreams,
  seedMode,
  expectedInterrupts,
  capabilityGaps,
}) {
  const requestedThreadId = randomUUID();
  createdThreads.add(requestedThreadId);
  const supersteps = seedMode === "canonical"
    ? [
        {
          updates: [
            {
              values: canonicalSeedState(),
              asNode: "build_artifact",
            },
          ],
        },
      ]
    : undefined;
  const createdThread = await client.threads.create({
    threadId: requestedThreadId,
    graphId,
    metadata: { probe: "task8-protocol-v2", probe_case: label },
    supersteps,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const threadId = createdThread?.thread_id;
  if (typeof threadId !== "string" || !threadId) {
    const shape = isRecord(createdThread)
      ? `object keys=${Object.keys(createdThread).sort().join(",") || "none"}` +
        (typeof createdThread.detail === "string"
          ? ` detail=${sanitizeError(createdThread.detail)}`
          : "")
      : typeof createdThread;
    throw new ProbeError(
      `${label} thread create returned no official thread_id (${shape})`,
    );
  }
  createdThreads.add(threadId);
  try {
    await withDeadline(
      client.threads.get(threadId, {
        signal: AbortSignal.timeout(timeoutMs),
      }),
      `${label} Thread read-after-create`,
      timeoutMs,
    );
  } catch (error) {
    throw new ProbeError(
      `${label} Thread ${threadId} was created but is not readable: ${sanitizeError(error)}`,
      EX_SOFTWARE,
      { cause: error },
    );
  }

  const stream = client.threads.stream(threadId, {
    assistantId,
    transport: "sse",
    maxReconnectAttempts: 0,
  });
  openStreams.add(stream);
  const subscription = await withDeadline(
    stream.subscribe(ROOT_SUBSCRIPTION),
    `${label} root-channel subscription`,
    timeoutMs,
  );
  const iterator = subscription[Symbol.asyncIterator]();

  await withDeadline(
    stream.run.start({
      input: seedMode === "canonical" ? null : {},
      metadata: { probe: "task8-protocol-v2", probe_case: label },
    }),
    `${label} run.start`,
    timeoutMs,
  );

  const paused = await collectUntil(
    iterator,
    (_event, events) =>
      uniqueInterrupts(events).length >= expectedInterrupts &&
      events.some((candidate) => isRootLifecycle(candidate, "interrupted")),
    `${label} interrupt stream`,
    timeoutMs,
  );
  const pending = uniqueInterrupts(paused.events);
  if (pending.length !== expectedInterrupts) {
    throw new ProbeError(
      `${label} expected exactly ${expectedInterrupts} interrupt(s), got ${pending.length}`,
    );
  }
  let checkpoint = protocolCheckpointId(paused.events);
  let checkpointSource = "protocol-channel";
  if (checkpoint == null) {
    const state = await client.threads.getState(threadId, undefined, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    checkpoint = stateCheckpointId(state);
    checkpointSource = "official-state-fallback";
    capabilityGaps.add(
      "root checkpoints channel emitted no lightweight Protocol checkpoint envelope",
    );
  }
  return {
    threadId,
    stream,
    subscription,
    iterator,
    events: paused.events,
    lastSequence: paused.lastSequence,
    pending,
    checkpoint,
    checkpointSource,
  };
}

async function closeStream(openStreams, stream) {
  if (!openStreams.delete(stream)) return;
  await stream.close();
}

async function verifyForkBoundary(stream, checkpoint, createdThreads) {
  try {
    const result = await stream.state.fork({
      checkpoint_id: checkpoint,
      input: { probe: "must-not-run" },
    });
    if (typeof result?.thread_id === "string" && result.thread_id) {
      createdThreads.add(result.thread_id);
    }
  } catch (error) {
    if (error?.name === "ProtocolError" && error?.code === "unknown_command") {
      return;
    }
    throw new ProbeError(
      `state.fork returned ${sanitizeError(error)} instead of locked unknown_command`,
      EX_SOFTWARE,
      { cause: error },
    );
  }
  throw new ProbeError(
    "state.fork unexpectedly succeeded; the locked compatibility boundary changed",
  );
}

async function verifyReplayAndSingleResponse(context) {
  const {
    client,
    graphId,
    assistantId,
    timeoutMs,
    createdThreads,
    openStreams,
    openTransports,
    ProtocolSseTransportAdapter,
    apiUrl,
    authorizationHeader,
    seedMode,
    capabilityGaps,
  } = context;
  const paused = await createPausedCanonicalThread({
    client,
    graphId,
    assistantId,
    label: "single-response",
    timeoutMs,
    createdThreads,
    openStreams,
    seedMode,
    expectedInterrupts: 1,
    capabilityGaps,
  });
  const sequences = paused.events.map((event) => event.seq);
  const since = sequences[0];
  const replayTarget = sequences.at(-1);
  if (since >= replayTarget) {
    throw new ProbeError("interrupt stream did not contain enough ordered events for replay");
  }
  const checkpoint = paused.checkpoint;

  await paused.subscription.unsubscribe();
  await closeStream(openStreams, paused.stream);

  const replayTransport = new ProtocolSseTransportAdapter({
    apiUrl,
    threadId: paused.threadId,
    defaultHeaders: { authorization: authorizationHeader },
    maxReconnectAttempts: 0,
  });
  openTransports.add(replayTransport);
  const replayHandle = replayTransport.openEventStream({
    ...ROOT_SUBSCRIPTION,
    since,
  });
  await withDeadline(
    replayHandle.ready,
    "official transport since replay connection",
    timeoutMs,
  );
  const replayIterator = replayHandle.events[Symbol.asyncIterator]();
  const replay = await collectUntil(
    replayIterator,
    (event) => event.seq >= replayTarget,
    "since replay",
    timeoutMs,
    since,
  );
  if (replay.events.some((event) => event.seq <= since)) {
    throw new ProbeError("since replay returned an event at or before the requested sequence");
  }
  const expectedReplay = paused.events.filter(
    (event) => event.seq > since && event.seq <= replayTarget,
  );
  if (replay.events.length !== expectedReplay.length) {
    throw new ProbeError(
      `since replay returned ${replay.events.length} events; expected ${expectedReplay.length}`,
    );
  }
  for (let index = 0; index < expectedReplay.length; index += 1) {
    const expected = expectedReplay[index];
    const actual = replay.events[index];
    if (
      typeof expected.event_id !== "string" ||
      typeof actual.event_id !== "string" ||
      actual.event_id !== expected.event_id ||
      actual.seq !== expected.seq ||
      actual.method !== expected.method ||
      JSON.stringify(actual.params.namespace) !== JSON.stringify(expected.params.namespace)
    ) {
      throw new ProbeError(
        `since replay identity diverged at index ${index} (seq=${actual.seq ?? "missing"})`,
      );
    }
  }

  const commandStream = client.threads.stream(paused.threadId, {
    assistantId,
    transport: "sse",
    maxReconnectAttempts: 0,
  });
  openStreams.add(commandStream);
  await verifyForkBoundary(commandStream, checkpoint, createdThreads);
  const pending = paused.pending[0];
  await withDeadline(
    commandStream.input.respond({
      namespace: pending.namespace,
      interrupt_id: pending.interruptId,
      response: APPROVE_RESPONSE,
    }),
    "single input.respond",
    timeoutMs,
  );
  const completed = await collectUntil(
    replayIterator,
    (event) => isRootLifecycle(event, "completed"),
    "single response completion stream",
    timeoutMs,
    replay.lastSequence,
  );
  await waitForCommittedState(client, paused.threadId, timeoutMs);
  replayHandle.close();
  openTransports.delete(replayTransport);
  await replayTransport.close();
  await closeStream(openStreams, commandStream);
  return {
    initialEventCount: paused.events.length,
    replayEventCount: replay.events.length,
    completionEventCount: completed.events.length,
    checkpointSource: paused.checkpointSource,
  };
}

async function verifyBatchResponse(context) {
  const {
    client,
    graphId,
    assistantId,
    timeoutMs,
    expectedBatchInterrupts,
    createdThreads,
    openStreams,
    seedMode,
    capabilityGaps,
  } = context;
  const paused = await createPausedCanonicalThread({
    client,
    graphId,
    assistantId,
    label: "batch-response",
    timeoutMs,
    createdThreads,
    openStreams,
    seedMode,
    expectedInterrupts: expectedBatchInterrupts,
    capabilityGaps,
  });
  await withDeadline(
    paused.stream.input.respond({
      responses: paused.pending.map((pending) => ({
        namespace: pending.namespace,
        interrupt_id: pending.interruptId,
        response: APPROVE_RESPONSE,
      })),
    }),
    "batch input.respond",
    timeoutMs,
  );
  const completed = await collectUntil(
    paused.iterator,
    (event) => isRootLifecycle(event, "completed"),
    "batch response completion stream",
    timeoutMs,
    paused.lastSequence,
  );
  await waitForCommittedState(client, paused.threadId, timeoutMs);
  await paused.subscription.unsubscribe();
  await closeStream(openStreams, paused.stream);
  return {
    responseCount: paused.pending.length,
    completionEventCount: completed.events.length,
    checkpointSource: paused.checkpointSource,
  };
}

async function loadSdk(expectedSdkVersion, expectedProtocolVersion) {
  let packageJson;
  let protocolPackageJson;
  let sdk;
  try {
    packageJson = JSON.parse(
      await readFile(
        path.join(
          frontendDirectory,
          "node_modules/@langchain/langgraph-sdk/package.json",
        ),
        "utf8",
      ),
    );
    protocolPackageJson = JSON.parse(
      await readFile(
        path.join(
          frontendDirectory,
          "node_modules/@langchain/protocol/package.json",
        ),
        "utf8",
      ),
    );
    sdk = frontendRequire("@langchain/langgraph-sdk");
  } catch (error) {
    throw new ProbeError(
      "@langchain/langgraph-sdk is unavailable; run npm ci in frontend first",
      EX_UNAVAILABLE,
      { cause: error },
    );
  }
  if (packageJson.version !== expectedSdkVersion) {
    throw new ProbeError(
      `expected @langchain/langgraph-sdk ${expectedSdkVersion}, found ${packageJson.version ?? "unknown"}`,
      EX_CONFIG,
    );
  }
  if (protocolPackageJson.version !== expectedProtocolVersion) {
    throw new ProbeError(
      `expected @langchain/protocol ${expectedProtocolVersion}, found ${protocolPackageJson.version ?? "unknown"}`,
      EX_CONFIG,
    );
  }
  if (
    typeof sdk.Client !== "function" ||
    typeof sdk.ProtocolError !== "function" ||
    typeof sdk.ProtocolSseTransportAdapter !== "function"
  ) {
    throw new ProbeError(
      "installed @langchain/langgraph-sdk lacks the locked Client/Protocol transport API",
      EX_CONFIG,
    );
  }
  return sdk;
}

function resolveAssistant(assistants, graphId, label) {
  const assistant = assistants.find((item) => item.graph_id === graphId);
  if (
    !assistant ||
    typeof assistant.assistant_id !== "string" ||
    !assistant.assistant_id
  ) {
    throw new ProbeError(
      `${label} graph ${graphId} is not registered on the explicit Agent Server endpoint`,
      EX_CONFIG,
    );
  }
  return { graphId, assistantId: assistant.assistant_id };
}

async function main() {
  if (process.argv.length !== 2) {
    throw new ProbeError("Usage: probe_protocol_v2.mjs", EX_USAGE);
  }
  if (typeof globalThis.fetch !== "function" || typeof AbortSignal.timeout !== "function") {
    throw new ProbeError("Node.js with fetch and AbortSignal.timeout is required", EX_UNAVAILABLE);
  }

  const apiUrl = validatedAgentUrl(requiredEnvironment("TASK8_AGENT_URL"));
  const token = requiredEnvironment("TASK8_AGENT_TOKEN");
  const singleGraphId = requiredEnvironment("TASK8_SINGLE_GRAPH_ID");
  const batchGraphId = requiredEnvironment("TASK8_BATCH_GRAPH_ID");
  const timeoutMs = positiveIntegerEnvironment("TASK8_PROBE_TIMEOUT_MS", 30_000);
  const expectedBatchInterrupts = positiveIntegerEnvironment(
    "TASK8_EXPECTED_BATCH_INTERRUPTS",
    1,
  );
  const expectedSdkVersion = process.env.TASK8_EXPECTED_SDK_VERSION?.trim() || "1.9.25";
  const expectedProtocolVersion =
    process.env.TASK8_EXPECTED_PROTOCOL_VERSION?.trim() || "0.0.18";
  const { Client, ProtocolSseTransportAdapter } = await loadSdk(
    expectedSdkVersion,
    expectedProtocolVersion,
  );
  const authorizationHeader = `Bearer ${token}`;
  const client = new Client({
    apiUrl,
    apiKey: null,
    defaultHeaders: { authorization: authorizationHeader },
    streamProtocol: "v2",
    timeoutMs,
    callerOptions: { maxRetries: 0 },
  });
  const createdThreads = new Set();
  const openStreams = new Set();
  const openTransports = new Set();
  const capabilityGaps = new Set();

  try {
    const assistants = await client.assistants.search({
      limit: 100,
      signal: AbortSignal.timeout(timeoutMs),
    });
    const singleAssistant = resolveAssistant(assistants, singleGraphId, "single-response");
    const batchAssistant = resolveAssistant(assistants, batchGraphId, "batch-response");

    const replay = await verifyReplayAndSingleResponse({
      client,
      ...singleAssistant,
      timeoutMs,
      createdThreads,
      openStreams,
      openTransports,
      ProtocolSseTransportAdapter,
      apiUrl,
      authorizationHeader,
      seedMode: "canonical",
      capabilityGaps,
    });
    const batch = await verifyBatchResponse({
      client,
      ...batchAssistant,
      timeoutMs,
      expectedBatchInterrupts,
      createdThreads,
      openStreams,
      seedMode: "none",
      capabilityGaps,
    });

    const summary = [
      `sdk=${expectedSdkVersion}`,
      `protocol=${expectedProtocolVersion}`,
      `root_channels=${ROOT_CHANNELS.join(",")}`,
      `initial_events=${replay.initialEventCount}`,
      `replay_events=${replay.replayEventCount}`,
      `single_completion_events=${replay.completionEventCount}`,
      `single_checkpoint=${replay.checkpointSource}`,
      `batch_responses=${batch.responseCount}`,
      `batch_completion_events=${batch.completionEventCount}`,
      `batch_checkpoint=${batch.checkpointSource}`,
      "state_fork=unknown_command_compatibility_exception",
    ].join(" ");
    if (capabilityGaps.size > 0) {
      process.stdout.write(`Protocol v2 downstream diagnostic completed ${summary}\n`);
      throw new ProbeError(
        `CAPABILITY GAP: ${[...capabilityGaps].join("; ")}`,
        EX_DATAERR,
      );
    }
    process.stdout.write(`Protocol v2 capability probe passed ${summary}\n`);
  } finally {
    for (const stream of [...openStreams]) {
      try {
        await closeStream(openStreams, stream);
      } catch (error) {
        process.stderr.write(`Protocol stream cleanup warning: ${sanitizeError(error)}\n`);
      }
    }
    for (const transport of [...openTransports]) {
      try {
        openTransports.delete(transport);
        await transport.close();
      } catch (error) {
        process.stderr.write(`Protocol transport cleanup warning: ${sanitizeError(error)}\n`);
      }
    }
    for (const threadId of createdThreads) {
      try {
        await client.threads.delete(threadId, {
          signal: AbortSignal.timeout(Math.min(timeoutMs, 5_000)),
        });
      } catch (error) {
        process.stderr.write(`Protocol Thread cleanup warning: ${sanitizeError(error)}\n`);
      }
    }
  }
}

try {
  await main();
} catch (error) {
  const exitCode =
    error instanceof ProbeError
      ? error.exitCode
      : endpointFailure(error)
        ? EX_UNAVAILABLE
        : EX_SOFTWARE;
  process.stderr.write(`Task 8 Protocol probe failed: ${sanitizeError(error)}\n`);
  process.exitCode = exitCode;
}
