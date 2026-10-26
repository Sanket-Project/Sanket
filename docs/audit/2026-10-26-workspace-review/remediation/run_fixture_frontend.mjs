// Serve the frontend on :5174 with /api proxied ONLY to the isolated fixture
// backend on :8010. Sets the proxy target in-process (shell `set` chains were
// silently dropped by the preview launcher, which then proxied to :8000).
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../frontend");
process.env.VITE_PROXY_TARGET = "http://127.0.0.1:8010";
process.chdir(frontend);

const require = createRequire(path.join(frontend, "package.json"));
// ESM entry (the CJS one only has a default export).
const viteEntry = path.join(path.dirname(require.resolve("vite/package.json")), "dist/node/index.js");
const { createServer } = await import(pathToFileURL(viteEntry).href);
const server = await createServer({
  configFile: path.join(frontend, "vite.config.ts"),
  server: { port: 5174, strictPort: true, host: "127.0.0.1" },
});
const target = server.config.server.proxy?.["/api"]?.target;
if (target !== "http://127.0.0.1:8010") {
  await server.close();
  throw new Error(`Refusing to start: /api proxies to ${target}`);
}
await server.listen();
server.printUrls();
