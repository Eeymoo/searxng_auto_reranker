import { Pool, type PoolClient } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var __autoRerankerPool: Pool | undefined;
}

/**
 * Returns a process-wide pg Pool. Re-used across hot reloads in dev.
 * The connection string is read from DATABASE_URL.
 */
export function getPool(): Pool {
  if (!globalThis.__autoRerankerPool) {
    const connectionString =
      process.env.DATABASE_URL ||
      "postgresql://auto_reranker:auto_reranker@localhost:5432/auto_reranker";
    globalThis.__autoRerankerPool = new Pool({ connectionString });
  }
  return globalThis.__autoRerankerPool;
}

/** Run `fn` within a pooled client. Releases the client on success or error. */
export async function withClient<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}
