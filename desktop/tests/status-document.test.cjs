const assert = require("node:assert/strict");
const test = require("node:test");

const {
  backendErrorScreenUrl,
  desktopStatusDocument,
  escapeHtml,
  startupScreenUrl,
} = require("../src/status-document.cjs");

function decodeStatusUrl(url) {
  const prefix = "data:text/html;charset=utf-8,";
  assert.equal(url.startsWith(prefix), true);
  return decodeURIComponent(url.slice(prefix.length));
}

test("status-document escaping covers markup, quotes, and ampersands", () => {
  assert.equal(
    escapeHtml(`<script title="unsafe">'run' & stop</script>`),
    "&lt;script title=&quot;unsafe&quot;&gt;&#39;run&#39; &amp; stop&lt;/script&gt;",
  );
});

test("startup and backend-error documents encode static data URLs", () => {
  const startupDocument = decodeStatusUrl(startupScreenUrl());
  assert.match(startupDocument, /<title>LighthousePM Starting<\/title>/);
  assert.match(startupDocument, /<h1>Starting LighthousePM<\/h1>/);
  assert.doesNotMatch(startupDocument, /<code>/);

  const errorDocument = decodeStatusUrl(
    backendErrorScreenUrl(
      `Backend <img src=x onerror="run()"> failed`,
      `Log: C:/unsafe/<script>alert('x')</script> & details`,
    ),
  );
  assert.match(errorDocument, /Backend &lt;img src=x onerror=&quot;run\(\)&quot;&gt; failed/);
  assert.match(
    errorDocument,
    /Log: C:\/unsafe\/&lt;script&gt;alert\(&#39;x&#39;\)&lt;\/script&gt; &amp; details/,
  );
  assert.doesNotMatch(errorDocument, /<img|<script>|onerror="/);
});

test("every dynamic status field is escaped before document publication", () => {
  const document = desktopStatusDocument({
    title: "<title attack>",
    heading: "<heading attack>",
    message: "<message attack>",
    detail: "<detail attack>",
  });

  for (const escaped of [
    "&lt;title attack&gt;",
    "&lt;heading attack&gt;",
    "&lt;message attack&gt;",
    "&lt;detail attack&gt;",
  ]) {
    assert.match(document, new RegExp(escaped));
  }
  assert.doesNotMatch(document, /<(?:title|heading|message|detail) attack>/);
});
