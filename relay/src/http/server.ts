import http from "node:http";
import { routeRequest, type RouterDependencies } from "./router.ts";

export interface RelayServer {
  server: http.Server;
  start(port?: number): Promise<number>;
  close(): Promise<void>;
}

export function createRelayServer(deps: RouterDependencies): RelayServer {
  const server = http.createServer(async (req, res) => {
    try {
      await routeRequest(req, res, deps);
    } catch {
      if (!res.headersSent) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "internal_error" }));
      }
    }
  });

  return {
    server,
    start(port = 8787): Promise<number> {
      return new Promise((resolve, reject) => {
        server.listen(port, () => {
          const addr = server.address();
          if (addr && typeof addr === "object") {
            resolve(addr.port);
          } else {
            resolve(port);
          }
        });
        server.on("error", reject);
      });
    },
    close(): Promise<void> {
      return new Promise((resolve) => {
        server.close(() => resolve());
      });
    },
  };
}
