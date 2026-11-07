import type { Route } from "../routes"
import type { Meta } from "../types"

const CONTACT = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined)?.trim() || ""
const UPDATED = "8 November 2026"

function Contact() {
  return CONTACT ? (
    <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
  ) : (
    <span>the contact address on this site's GitHub page</span>
  )
}

export function InfoPage({ route, meta }: { route: Exclude<Route, "">; meta: Meta | null }) {
  return (
    <article className="info">
      <a className="info__back" href="/">
        Back to your report
      </a>
      {route === "guide" && <Guide />}
      {route === "faq" && <Faq meta={meta} />}
      {route === "about" && <About />}
      {route === "privacy" && <Privacy meta={meta} />}
      {route === "terms" && <Terms />}
      <nav className="info__more" aria-label="More pages">
        <a href="/guide">Guide</a>
        <a href="/faq">FAQ</a>
        <a href="/about">How it works</a>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
      </nav>
    </article>
  )
}

function Guide() {
  return (
    <>
      <h1>How to use LabForge</h1>
      <p>
        LabForge turns the experiment sheet from your LMS into a lab report: aim, objectives, code, the output the
        code really printed, and learning outcomes. Here is the whole process, start to finish.
      </p>
      <h2>1. Fill in your details once</h2>
      <p>
        Type your name, UID, branch, section and semester in step 1. They stay in this browser, so next time they're
        already there. Choose a report format: a plain one, or a layout that follows your department's sample report.
      </p>
      <h2>2. Add the experiment sheet</h2>
      <p>
        Upload the sheet as a PDF, Word, PowerPoint or text file, or paste the text. If your project has several files,
        upload a .zip of the folder. Pick the programming language if the sheet doesn't say, then press "Write my
        report".
      </p>
      <h2>3. Wait while the programs run</h2>
      <p>
        LabForge writes the code and then actually compiles and runs every program on its server. Java and Spring
        programs can take a minute or two. You can leave the page: the report keeps being written, and when you come
        back it picks up where it was.
      </p>
      <h2>4. Check every task</h2>
      <p>
        Open each task in step 3. Read the code until you understand it, and use "Explain this code" to see how it
        works and practise likely viva questions. If you change the code or the input, run it again so the output
        matches. Programs that need a window, hardware or software we don't have are marked: run them on your machine
        and add a screenshot.
      </p>
      <h2>5. Download</h2>
      <p>
        Your Word file is made automatically. Make the PDF when you're happy with it. Check the page previews before
        you submit. When you're done, you can delete the report from our server.
      </p>
      <h2>Tips</h2>
      <ul>
        <li>Upload one experiment at a time. Very long sheets get cut off.</li>
        <li>If a program waits for input, put each value on its own line under "Input".</li>
        <li>Output can't be typed in by hand. It's always what the program printed.</li>
      </ul>
    </>
  )
}

function Faq({ meta }: { meta: Meta | null }) {
  const daily = meta?.limits.daily ?? 10
  return (
    <>
      <h1>Frequently asked questions</h1>
      <h2>Which languages can it run?</h2>
      <p>
        Java (including Spring Boot), Python with NumPy, Matplotlib, OpenCV and scikit-image, C, C++, Node.js with
        Express and Mongoose, React, SQL (on SQLite), and HTML/CSS/JS pages. Other languages get the code and a space for
        your own screenshot.
      </p>
      <h2>Is the output real?</h2>
      <p>
        Yes. Every program is compiled and run, and the report shows exactly what it printed. You can't edit the output
        by hand; if you change the code or the input, run it again and the new output replaces the old one.
      </p>
      <h2>Why is it limited to {daily} new sheets a day?</h2>
      <p>
        Writing a new sheet costs an AI call. A sheet someone has already uploaded is reused for free, so it doesn't
        count. The limit keeps LabForge free for everyone.
      </p>
      <h2>Does my report match my classmates'?</h2>
      <p>
        If you upload the same sheet, you start from the same code. That's fine for learning, but your college's rules
        decide what you may submit. Read the code, understand it, and change it to make it your own where your
        teacher expects that.
      </p>
      <h2>Is this cheating?</h2>
      <p>
        It depends on how you use it. LabForge is meant to save you formatting and screenshot work and to help you
        understand the programs. Submitting work you can't explain, or that your institution doesn't allow, is your
        responsibility. Use "Explain this code" and make sure you can answer viva questions about it.
      </p>
      <h2>Do I need an account?</h2>
      <p>No. Your details are saved in your browser only.</p>
      <h2>How do I delete my data?</h2>
      <p>
        Use "Delete this report from the server" in the download step. To clear what's saved in your browser, clear
        this site's data in your browser settings. For anything else, write to <Contact />.
      </p>
      <h2>Is LabForge made by my university?</h2>
      <p>No. LabForge is an independent project and isn't affiliated with or endorsed by any university.</p>
    </>
  )
}

function About() {
  return (
    <>
      <h1>How LabForge works</h1>
      <p>
        Every practical subject asks for the same report: aim, objectives, the code, a screenshot of the output and
        what you learned. LabForge writes that report from the experiment sheet you already have.
      </p>
      <h2>What happens when you upload a sheet</h2>
      <ol>
        <li>The sheet is read and trimmed to the parts that matter: the aim, the problems and any code it gives you.</li>
        <li>Your own details at the top of the sheet (name, UID and so on) are removed before anything goes to the AI.</li>
        <li>An AI model writes the aim, objectives, programs and learning outcomes.</li>
        <li>
          Every program is compiled and run on our server. The output in your report is what the program actually
          printed, not something a model made up. Python plots and web pages are captured as images.
        </li>
        <li>If a program fails, the error goes back to the model once to fix it, and it runs again.</li>
        <li>You check everything, change what you like, and download it as a Word file or PDF.</li>
      </ol>
      <h2>What runs here</h2>
      <p>
        Java, Python (including NumPy, OpenCV, Matplotlib and scikit-image), C and C++, Node.js with Express and
        Mongoose, React, SQL and plain HTML/CSS/JS pages. Programs in other languages, or ones that need hardware or a
        desktop window, are left for you to run: add your own screenshot and it goes into the report.
      </p>
      <h2>Same sheet as your classmates?</h2>
      <p>
        When a sheet has been written before, LabForge reuses that work, which is why it's fast and free. If something
        in it is wrong, you can have it written again from scratch.
      </p>
      <h2>Use it honestly</h2>
      <p>
        LabForge saves you the formatting and the screenshots, and helps you understand the code. Read the code before
        you submit it, run it yourself, and make sure you can explain it in your viva. Follow your institution's rules on
        what you may submit.
      </p>
      <h2>Independent</h2>
      <p>
        LabForge is an independent project. It isn't affiliated with, sponsored or endorsed by any university. Report
        layouts that follow a department's sample report are offered for convenience only.
      </p>
    </>
  )
}

function Privacy({ meta }: { meta: Meta | null }) {
  const ttl = meta?.job_ttl_hours ?? 24
  const logDays = meta?.log_days ?? 14
  const personal = meta?.log_personal ?? false
  return (
    <>
      <h1>Privacy policy</h1>
      <p>Last updated {UPDATED}.</p>
      <p>
        This policy explains what LabForge collects when you use the website, why, how long it is kept, who else
        receives it, and how to have it deleted. Questions and requests: <Contact />.
      </p>

      <h2>What stays on your device</h2>
      <p>
        Your name, UID, branch, section, semester, subjects, your report format and your latest report are saved in
        this browser's local storage so you don't have to type them again. So is a random id for this browser, which we
        use only to count your daily limits. It isn't linked to your name. We don't have accounts.
      </p>

      <h2>What reaches our server, and for how long</h2>
      <ul>
        <li>
          <b>The experiment sheet</b> you upload or paste. Your own details at the top of the sheet are removed before
          it is stored or sent to an AI service.
        </li>
        <li>
          <b>The programs, their input and output, your screenshots and the Word and PDF files</b> we make. When you make
          the files, the details you typed (name, UID and so on) are sent so they can be printed in the report. All of
          this is deleted after {ttl} hours, or straight away when you press "Delete this report from the server".
        </li>
        <li>
          <b>A cache of written sheets</b>, without any personal details, so the same sheet doesn't have to be written
          twice.
        </li>
        <li>
          <b>An activity log</b>, kept for {logDays} days so we can fix reports that come out wrong: which experiment was
          written, whether each program ran, error messages, your feedback and reports, and the start of the sheet.
          Your IP address is stored only as a one-way code.
          {personal
            ? " The name and UID on the report are also stored, so we can help you if you contact us about it."
            : " Names and UIDs are not stored."}
        </li>
        <li>
          <b>Usage counts</b> per browser id and per IP address, for one day, to enforce the daily limits and stop abuse.
        </li>
      </ul>

      <h2>Who else receives data</h2>
      <ul>
        <li>
          <b>AI services</b> write and explain the reports: for example Google Gemini, Groq, Cerebras, OpenRouter,
          Mistral, GitHub Models and Cloudflare Workers AI. They receive the trimmed sheet text and the code, never your
          details from the form. Some free AI plans allow the provider to use what they receive to improve their
          services, so don't paste personal information into the sheet text.
        </li>
        <li>
          <b>Our hosting and database providers</b> store the data above on our behalf.
        </li>
        <li>
          <b>Google AdSense</b> shows ads and uses cookies to do it, including ads based on your earlier visits to this
          and other websites. You can turn off personalised ads in{" "}
          <a href="https://adssettings.google.com" rel="noopener noreferrer" target="_blank">Google's ad settings</a>.
          Read how{" "}
          <a href="https://policies.google.com/technologies/partner-sites" rel="noopener noreferrer" target="_blank">
            Google uses data from sites that use its services
          </a>
          . Visitors from the EEA, the UK and Switzerland are asked for consent first.
        </li>
        <li>
          <b>Analytics and error reports</b>, if enabled, count page visits without cookies and record technical details
          of errors. Neither receives your report contents or form details.
        </li>
      </ul>
      <p>We don't sell personal data and we don't build profiles of students.</p>

      <h2>Your choices and rights</h2>
      <ul>
        <li>Delete any report from our server at any time from the download step.</li>
        <li>Clear what's saved on your device by clearing this site's data in your browser.</li>
        <li>
          Ask us what we hold about you, to correct it or to delete it, or raise a complaint, by writing to <Contact />.
          We aim to answer within 7 days.
        </li>
      </ul>

      <h2>Children</h2>
      <p>
        LabForge is meant for university students aged 18 or over. If you're younger, use it only with your parent's or
        guardian's permission.
      </p>

      <h2>Changes</h2>
      <p>If this policy changes, the date at the top changes too. Big changes will be announced on the site.</p>
    </>
  )
}

function Terms() {
  return (
    <>
      <h1>Terms of use</h1>
      <p>Last updated {UPDATED}.</p>
      <h2>The service</h2>
      <p>
        LabForge is provided free of charge and as is, without any guarantee. AI-written content can be wrong.
        Generated reports are a starting point: you are responsible for checking them before you use them.
      </p>
      <h2>Academic honesty</h2>
      <p>
        You are responsible for following your institution's academic integrity rules. Don't submit work you can't
        explain, and don't use LabForge where your institution forbids it. LabForge isn't affiliated with any university.
      </p>
      <h2>Acceptable use</h2>
      <ul>
        <li>Don't upload material you don't have the right to share.</li>
        <li>Don't use the service to run harmful code, attack other systems, or get around its limits.</li>
        <li>Don't try to access other people's reports.</li>
      </ul>
      <p>We may limit or block use that puts the service or other users at risk.</p>
      <h2>Age</h2>
      <p>You must be 18 or older, or have permission from a parent or guardian.</p>
      <h2>Contact</h2>
      <p>
        Questions about these terms: <Contact />.
      </p>
    </>
  )
}
