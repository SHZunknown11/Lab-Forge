/** Text shared by the pages, the prerendered HTML search engines see, and the structured data. */

export const AUTHOR = {
  name: (import.meta.env.VITE_AUTHOR_NAME as string | undefined)?.trim() || "Mohammad Taha",
  affiliation: (import.meta.env.VITE_AUTHOR_AFFILIATION as string | undefined)?.trim() || "Chandigarh University",
  // Comma-separated profile URLs (LinkedIn, GitHub, portfolio), set at build time.
  links: ((import.meta.env.VITE_AUTHOR_LINKS as string | undefined) || "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => /^https:\/\//.test(s)),
}

export const AUTHOR_PATH = "/mohammad-taha"

export const TAGLINE = "Lab reports from your experiment sheet, with working code and real output"

export interface QA {
  q: string
  a: string
}

/** `{daily}` is replaced with the daily limit. Plain text: it also feeds the FAQ structured data. */
export const FAQ: QA[] = [
  {
    q: "What is LabForge?",
    a: "LabForge is a free web app that turns a university lab experiment sheet into a finished lab report: aim, objectives, working code, the output the code really printed, and learning outcomes, as a Word or PDF file in your college's format.",
  },
  {
    q: "Who made LabForge?",
    a: `LabForge was created by ${AUTHOR.name}, a student at ${AUTHOR.affiliation}, to save students the hours spent formatting lab files and taking output screenshots.`,
  },
  {
    q: "Which languages can it run?",
    a: "Java (including Spring Boot), Python with NumPy, Matplotlib, OpenCV and scikit-image, C, C++, Node.js with Express and Mongoose, React, SQL (on SQLite), and HTML/CSS/JS pages. Other languages get the code and a space for your own screenshot.",
  },
  {
    q: "Is the output real?",
    a: "Yes. Every program is compiled and run, and the report shows exactly what it printed. You can't edit the output by hand; if you change the code or the input, run it again and the new output replaces the old one.",
  },
  {
    q: "Is LabForge free?",
    a: "Yes. It's free and supported by ads. Sign in with your college email and you get a few free reports every day. A report that fails to be written doesn't count. When you run out, you can choose to watch an ad for another report, or wait until the next day.",
  },
  {
    q: "Does my report match my classmates'?",
    a: "If you upload the same sheet, you start from the same code. That's fine for learning, but your college's rules decide what you may submit. Read the code, understand it, and change it to make it your own where your teacher expects that.",
  },
  {
    q: "Is this cheating?",
    a: "It depends on how you use it. LabForge is meant to save you formatting and screenshot work and to help you understand the programs. Submitting work you can't explain, or that your institution doesn't allow, is your responsibility. Use \"Explain this code\" and make sure you can answer viva questions about it.",
  },
  {
    q: "Do I need an account?",
    a: "Yes, to write a report. Type your college email address, we send it a 6-digit code, and you're signed in. There is no password. Your name, UID and your finished reports are saved in your browser only.",
  },
  {
    q: "Where are my old reports?",
    a: "Under \"Your reports\" on the device you made them on, locked to your account. LabForge doesn't keep your finished reports on its server, so they aren't on your other devices, and clearing the site's data in your browser removes them.",
  },
  {
    q: "How do I delete my data?",
    a: "Use \"Delete this report from the server\" in the download step. To clear what's saved in your browser, clear this site's data in your browser settings. To delete your account, or for anything else, use the contact address on the privacy page.",
  },
  {
    q: "Is LabForge made by my university?",
    a: `No. LabForge is an independent project by ${AUTHOR.name}. It isn't affiliated with, sponsored or endorsed by ${AUTHOR.affiliation} or any other university.`,
  },
]

export const faqFor = (daily: number) => FAQ.map((x) => ({ q: x.q, a: x.a.replace("{daily}", String(daily)) }))
