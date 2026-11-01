// Starts a throwaway in-memory MongoDB, runs the student's entry file with
// MONGO_URI pointing at it, then stops the database. Nothing is persisted.
const { MongoMemoryServer } = require("mongodb-memory-server");
const { spawn } = require("child_process");

(async () => {
  const mongod = await MongoMemoryServer.create();
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
