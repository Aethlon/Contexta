import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../out");
const publicDir = path.resolve(__dirname, "../public");

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// Copy public assets if available
if (fs.existsSync(publicDir)) {
  fs.cpSync(publicDir, outDir, { recursive: true });
}

// Create standalone desktop shell launcher
const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Contexta — Sovereign Memory Console</title>
  <style>
    body {
      margin: 0;
      padding: 0;
      background: #09090b;
      color: #fafafa;
      font-family: monospace;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      text-align: center;
    }
    .logo {
      width: 48px;
      height: 48px;
      margin-bottom: 16px;
      color: #6366f1;
    }
    .pulse {
      animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: .5; }
    }
  </style>
  <script>
    const target = "http://localhost:3000";
    window.location.href = target;
  </script>
</head>
<body>
  <svg class="logo pulse" viewBox="0 0 100 100" fill="currentColor">
    <path d="M16 30.5C16 27.5 18 25.5 21 23.8L38.5 13.5C41.5 11.8 44 13.2 44 16.5L44 42C44 45 42 48 39.5 50.5L33 57C31 59 30 61.5 30 64.5L30 67C30 70 27.5 71.5 24.5 69.8L18.5 66.2C16.5 65 16 63 16 60.5Z"/>
    <path d="M84 69.5C84 72.5 82 74.5 79 76.2L61.5 86.5C58.5 88.2 56 86.8 56 83.5L56 58C56 55 58 52 60.5 49.5L67 43C69 41 70 38.5 70 35.5L70 33C70 30 72.5 28.5 75.5 30.2L81.5 33.8C83.5 35 84 37 84 39.5Z"/>
  </svg>
  <div style="font-size: 13px; letter-spacing: 0.05em;">Connecting to Contexta Sovereign Console...</div>
  <div style="font-size: 10px; color: #71717a; margin-top: 8px;">Connecting to local console at http://localhost:3000</div>
</body>
</html>`;

fs.writeFileSync(path.join(outDir, "index.html"), html, "utf-8");
console.log("✓ Prepared static shell launcher in dashboard/out/index.html");
