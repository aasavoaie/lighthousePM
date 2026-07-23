function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function desktopStatusDocument({ title, heading, message, detail }) {
  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="color-scheme" content="light" />
    <title>${escapeHtml(title)}</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f4f7fb;
        color: #101733;
        font-family: Inter, Segoe UI, Arial, sans-serif;
      }
      main {
        width: min(560px, calc(100vw - 48px));
        display: grid;
        gap: 14px;
      }
      h1 {
        margin: 0;
        font-size: 1.45rem;
      }
      p {
        margin: 0;
        color: #52617f;
        line-height: 1.5;
      }
      code {
        display: block;
        padding: 12px;
        border: 1px solid #d9deec;
        border-radius: 8px;
        background: #ffffff;
        color: #344468;
        overflow-wrap: anywhere;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>${escapeHtml(heading)}</h1>
      <p>${escapeHtml(message)}</p>
      ${detail ? `<code>${escapeHtml(detail)}</code>` : ""}
    </main>
  </body>
</html>`;
}

function desktopStatusUrl(options) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(desktopStatusDocument(options))}`;
}

function startupScreenUrl() {
  return desktopStatusUrl({
    title: "LighthousePM Starting",
    heading: "Starting LighthousePM",
    message: "Preparing the local backend and loading your dashboard.",
  });
}

function backendErrorScreenUrl(message, detail) {
  return desktopStatusUrl({
    title: "LighthousePM Backend Error",
    heading: "The local backend stopped",
    message,
    detail,
  });
}

module.exports = {
  backendErrorScreenUrl,
  desktopStatusDocument,
  desktopStatusUrl,
  escapeHtml,
  startupScreenUrl,
};
