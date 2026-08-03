/**
 * Phase 18d / 36a — CRA dev-server proxy for site-root paths owned by
 * the FastAPI backend.
 *
 * /ads.txt + /app-ads.txt          → backend (Phase 18d)
 * /podcasts/{slug}/rss.xml      → backend (Phase 36a)
 *
 * CRA picks up `src/setupProxy.js` automatically.  In production, the
 * ingress / nginx / CF config must mirror these forwards or these
 * specific root paths will be intercepted by the static-asset layer.
 */
const { createProxyMiddleware } = require("http-proxy-middleware");

module.exports = function (app) {
  const target = "http://localhost:8001";

  // /ads.txt + /app-ads.txt — fixed root paths.
  app.use(
    ["/ads.txt", "/app-ads.txt"],
    createProxyMiddleware({
      target,
      changeOrigin:  true,
      logLevel:        "warn",
    })
  );

  // /podcasts/{slug}/rss.xml — use app.get (not app.use) so path-to-regexp
  // matches the :slug segment exactly. Re-attach the original URL before
  // the proxy reads req.url (Express strips the mount on app.use; app.get
  // doesn't strip, but the proxy middleware still keys off req.url so we
  // explicitly set it).
  app.get("/podcasts/:slug/rss.xml", (req, _res, next) => {
    req.url = req.originalUrl;
    next();
  }, createProxyMiddleware({
    target,
    changeOrigin: true,
    logLevel:        "warn",
  }));
};
