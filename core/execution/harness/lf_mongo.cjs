// Starts a throwaway in-memory MongoDB, runs the student's entry file with
// MONGO_URI pointing at it, then stops the database. Nothing is persisted.
// The -core package has no download step; scripts/setup_runtime.py supplies the mongod binary.
const { MongoMemoryServer } = (() => {
  try {
    return require("mongodb-memory-server-core");
  } catch {
    return require("mongodb-memory-server");
  }
})();
const { spawn } = require("child_process");

(async () => {
  // A small cache: several programs may run at once on a shared server.
  const mongod = await MongoMemoryServer.create({ instance: { args: ["--wiredTigerCacheSizeGB", "0.25"] } });
  const uri = mongod.getUri("labdb");
  const child = spawn(process.execPath, [process.argv[2]], {
    stdio: "inherit",
    env: { ...process.env, MONGO_URI: uri, MONGODB_URI: uri, DATABASE_URL: uri },
  });
  child.on("exit", async (code) => {
    await mongod.stop();
    process.exit(code ?? 1);
  });
})().catch((err) => {
  console.error("Could not start the test database: " + err.message);
  process.exit(3);
});
