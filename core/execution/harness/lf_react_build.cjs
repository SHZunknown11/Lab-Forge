// Bundles a small React project with esbuild into dist/ so it can be opened
// in headless Chrome and screenshotted. Usage: node lf_react_build.cjs <entry>
const esbuild = require("esbuild");
const fs = require("fs");

esbuild
  .build({
    entryPoints: [process.argv[2]],
    bundle: true,
    outfile: "dist/app.js",
    jsx: "automatic",
    loader: { ".js": "jsx", ".png": "dataurl", ".jpg": "dataurl", ".jpeg": "dataurl", ".svg": "dataurl", ".gif": "dataurl" },
    define: { "process.env.NODE_ENV": '"production"' },
    nodePaths: [process.env.LF_NODE_MODULES],
    logLevel: "error",
    minify: true,
  })
  .then(() => {
    const css = fs.existsSync("dist/app.css") ? '<link rel="stylesheet" href="/app.css">' : "";
    fs.writeFileSync(
      "dist/index.html",
      `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>App</title>${css}</head><body><div id="root"></div><script src="/app.js"></script></body></html>`
    );
  })
  .catch(() => process.exit(1));
