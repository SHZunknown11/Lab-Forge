// Preloaded (NODE_OPTIONS=--require) when EXEC_ALLOW_NETWORK=0: TCP connections
// may only go to this machine, so a lab program can't reach the internet while
// Express self-tests and the in-memory MongoDB keep working.
const net = require("net");

const LOOPBACK = /^(localhost|127(\.\d{1,3}){3}|::1|::ffff:127(\.\d{1,3}){3})$/i;
const connect = net.Socket.prototype.connect;

net.Socket.prototype.connect = function (...args) {
  let opts = args[0];
  if (Array.isArray(opts)) opts = opts[0]; // already-normalised arguments from net.connect()
  let host = "localhost";
  if (opts && typeof opts === "object") {
    if (opts.path) return connect.apply(this, args); // unix socket / named pipe
    host = opts.host || "localhost";
  } else if (typeof opts === "string" && !/^\d+$/.test(opts)) {
    return connect.apply(this, args); // socket path
  } else if (typeof args[1] === "string") {
    host = args[1];
  }
  host = String(host).replace(/^\[|\]$/g, "");
  if (!LOOPBACK.test(host)) {
    const err = new Error(`connect ENETUNREACH ${host} (lab programs can't reach the internet here)`);
    err.code = "ENETUNREACH";
    process.nextTick(() => this.destroy(err));
    return this;
  }
  return connect.apply(this, args);
};
