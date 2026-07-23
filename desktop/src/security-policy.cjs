function parseUrl(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }

  try {
    return new URL(value);
  } catch {
    return null;
  }
}

function isAllowedAppNavigation(targetUrl, rendererOrigin) {
  const parsedTarget = parseUrl(targetUrl);
  const parsedRendererOrigin = parseUrl(rendererOrigin);
  return Boolean(
    parsedTarget &&
      parsedRendererOrigin &&
      parsedTarget.origin === parsedRendererOrigin.origin,
  );
}

function isAllowedExternalUrl(targetUrl) {
  const parsedTarget = parseUrl(targetUrl);
  return Boolean(parsedTarget && parsedTarget.protocol === "https:");
}

function isLocalApiPath(pathname) {
  return pathname === "/api" || pathname.startsWith("/api/");
}

function shouldAttachLocalApiToken(targetUrl, rendererOrigin) {
  const parsedTarget = parseUrl(targetUrl);
  const parsedRendererOrigin = parseUrl(rendererOrigin);
  return Boolean(
    parsedTarget &&
      parsedRendererOrigin &&
      parsedTarget.origin === parsedRendererOrigin.origin &&
      isLocalApiPath(parsedTarget.pathname),
  );
}

module.exports = {
  isAllowedAppNavigation,
  isAllowedExternalUrl,
  isLocalApiPath,
  shouldAttachLocalApiToken,
};
