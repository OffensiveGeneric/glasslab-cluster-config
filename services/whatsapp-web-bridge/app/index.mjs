import express from "express";
import pino from "pino";
import makeWASocket, {
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const logger = pino({ level: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_LOG_LEVEL || "info" });

const settings = {
  port: Number(process.env.PORT || "8098"),
  stateDir: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_STATE_DIR || "/var/lib/glasslab-whatsapp-web",
  authDir: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_AUTH_DIR || "/var/lib/glasslab-whatsapp-web/default",
  gatewayUrl: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_GATEWAY_URL || "http://glasslab-whatsapp-gateway.glasslab-v2.svc.cluster.local:8097",
  baseUrl: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_BASE_URL || "http://glasslab-whatsapp-web-bridge.glasslab-v2.svc.cluster.local:8098",
  startupMode: process.env.GLASSLAB_WHATSAPP_WEB_BRIDGE_STARTUP_MODE || "require-auth",
};

fs.mkdirSync(settings.stateDir, { recursive: true });
fs.mkdirSync(settings.authDir, { recursive: true });
fs.mkdirSync(path.join(settings.stateDir, "attachments"), { recursive: true });

let sock = null;
let latestQr = null;
let connectionState = {
  connected: false,
  lastError: null,
  selfJid: null,
  qrRequired: false,
};

const app = express();
app.use(express.json({ limit: "10mb" }));

function attachmentPath(id) {
  return path.join(settings.stateDir, "attachments", id);
}

function providerMessageId(message) {
  return message?.key?.id || null;
}

function senderFromJid(jid) {
  if (!jid) return null;
  return jid.split("@")[0];
}

function preferredSenderId(key) {
  return (
    key?.participantAlt ||
    key?.remoteJidAlt ||
    key?.participant ||
    key?.remoteJid ||
    null
  );
}

function isGroupJid(jid) {
  return typeof jid === "string" && jid.endsWith("@g.us");
}

function extractText(message) {
  const payload = message?.message || {};
  return (
    payload.conversation ||
    payload.extendedTextMessage?.text ||
    payload.imageMessage?.caption ||
    payload.videoMessage?.caption ||
    payload.documentMessage?.caption ||
    ""
  ).trim();
}

async function maybePersistPdf(message) {
  const payload = message?.message || {};
  const doc = payload.documentMessage;
  if (!doc) {
    return [];
  }
  const mime = String(doc.mimetype || "").toLowerCase();
  const fileName = String(doc.fileName || "");
  if (mime !== "application/pdf" && !fileName.toLowerCase().endsWith(".pdf")) {
    return [];
  }

  const buf = await downloadMediaMessage(
    message,
    "buffer",
    {},
    {}
  );
  if (!buf || !Buffer.isBuffer(buf)) {
    return [];
  }

  const digest = crypto.createHash("sha256").update(buf).digest("hex");
  const ext = fileName.toLowerCase().endsWith(".pdf") ? ".pdf" : ".bin";
  const filename = `${digest}${ext}`;
  const fullPath = attachmentPath(filename);
  if (!fs.existsSync(fullPath)) {
    fs.writeFileSync(fullPath, buf);
  }
  return [
    {
      url: `${settings.baseUrl.replace(/\/$/, "")}/attachments/${filename}`,
      mime_type: mime || "application/pdf",
      filename: fileName || filename,
    },
  ];
}

async function postGatewayInbound(payload) {
  const response = await fetch(`${settings.gatewayUrl.replace(/\/$/, "")}/webhooks/whatsapp/inbound`, {
    method: "POST",
    headers: { "content-type": "application/json", "accept": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.text();
  let parsed = null;
  try {
    parsed = JSON.parse(body);
  } catch {
    parsed = { raw: body };
  }
  if (!response.ok) {
    throw new Error(`gateway inbound failed: ${response.status} ${body}`);
  }
  return parsed;
}

async function handleInbound(message) {
  const remoteJid = message?.key?.remoteJid;
  if (!remoteJid || message?.key?.fromMe) {
    return;
  }

  const sender = preferredSenderId(message?.key) || remoteJid;
  const text = extractText(message);
  const attachments = await maybePersistPdf(message);
  const payload = {
    sender,
    channel: "whatsapp",
    message: text,
    provider_message_id: providerMessageId(message),
    conversation_id: remoteJid,
    is_group: isGroupJid(remoteJid),
    attachments,
  };
  logger.info({ sender, conversationId: remoteJid, hasText: Boolean(text), attachments: attachments.length }, "forwarding inbound whatsapp turn");
  const gateway = await postGatewayInbound(payload);
  const reply = String(gateway?.response_text || "").trim();
  if (reply) {
    await sock.sendMessage(remoteJid, { text: reply });
  }
}

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(settings.authDir);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger,
    syncFullHistory: false,
    markOnlineOnConnect: false,
    browser: ["Glasslab", "Chrome", "1.0"],
  });

  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") {
      return;
    }
    for (const message of messages) {
      try {
        await handleInbound(message);
      } catch (error) {
        logger.error({ err: error }, "failed to handle inbound whatsapp message");
      }
    }
  });
  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      latestQr = qr;
      connectionState.qrRequired = true;
      logger.warn("qr required for whatsapp web bridge");
    }
    if (connection === "open") {
      latestQr = null;
      connectionState.connected = true;
      connectionState.qrRequired = false;
      connectionState.lastError = null;
      connectionState.selfJid = sock?.user?.id || null;
      logger.info({ selfJid: connectionState.selfJid }, "whatsapp web bridge connected");
    } else if (connection === "close") {
      connectionState.connected = false;
      connectionState.lastError = lastDisconnect?.error?.message || "connection closed";
      logger.warn({ err: connectionState.lastError }, "whatsapp web bridge disconnected");
      setTimeout(() => {
        connect().catch((error) => logger.error({ err: error }, "reconnect failed"));
      }, 5000);
    }
  });
}

app.get("/healthz", (_req, res) => {
  res.json({
    status: "ok",
    connected: connectionState.connected,
    qr_required: connectionState.qrRequired,
    self_jid: connectionState.selfJid,
    gateway_url: settings.gatewayUrl,
    startup_mode: settings.startupMode,
  });
});

app.get("/qr", (_req, res) => {
  if (!latestQr) {
    res.status(404).json({ detail: "no qr pending" });
    return;
  }
  res.json({ qr: latestQr });
});

app.get("/attachments/:name", (req, res) => {
  const name = path.basename(req.params.name);
  const fullPath = attachmentPath(name);
  if (!fs.existsSync(fullPath)) {
    res.status(404).json({ detail: "attachment not found" });
    return;
  }
  res.sendFile(fullPath);
});

app.listen(settings.port, "0.0.0.0", () => {
  logger.info({ port: settings.port }, "whatsapp web bridge listening");
});

connect().catch((error) => {
  logger.error({ err: error }, "initial connect failed");
  if (settings.startupMode === "require-auth") {
    process.exit(1);
  }
});
