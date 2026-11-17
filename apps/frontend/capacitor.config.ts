import type { CapacitorConfig } from "@capacitor/cli"

const config: CapacitorConfig = {
  appId: "in.labforge.app",
  appName: "LabForge",
  webDir: "dist",
  android: { allowMixedContent: false },
  // LF_TEST=1 builds a debug app that talks to a backend on the dev machine (http, emulator only).
  ...(process.env.LF_TEST ? { server: { androidScheme: "http", cleartext: true } } : {}),
}

export default config
