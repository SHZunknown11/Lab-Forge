import { AUTHOR, AUTHOR_PATH, TAGLINE, faqFor } from "../content"
import type { Route } from "../routes"
import type { Meta } from "../types"

const CONTACT = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined)?.trim() || ""
const UPDATED = "14 November 2026"

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
      {route === "mohammad-taha" && <Maker />}
      <nav className="info__more" aria-label="More pages">
        <a href="/guide">Guide</a>
        <a href="/faq">FAQ</a>
        <a href="/about">How it works</a>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href={AUTHOR_PATH}>About the maker</a>
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
      <h2>Sign in with your college email</h2>
      <p>
        Type your college email address and we send it a 6-digit code. Type the code in and you're signed in on this
        device for a month. There's no password to remember. Signing in gives you a few free reports every day.
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
      <h2>6. Find it again later</h2>
      <p>
        Every report you make is also saved under "Your reports" on the device you made it on, locked to your account.
        We don't keep your finished reports on our server, so they aren't on your other devices, and clearing this
        site's data in your browser removes them.
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
  return (
    <>
      <h1>Frequently asked questions</h1>
      {faqFor(meta?.limits.daily ?? 10).map((x) => (
        <section key={x.q}>
          <h2>{x.q}</h2>
          <p>{x.a}</p>
        </section>
      ))}
      <p>
        Still stuck? Write to <Contact />.
      </p>
    </>
  )
}

function Maker() {
  return (
    <>
      <h1>{AUTHOR.name}, creator of LabForge</h1>
      <p>
        <b>{AUTHOR.name}</b> is a student at {AUTHOR.affiliation} and the developer of LabForge, a
        free web app that turns lab experiment sheets into finished lab reports with working code and the output it
        really printed.
      </p>
      <h2>Why LabForge exists</h2>
      <p>
        Every practical subject asks for the same lab file: aim, objectives, code, an output screenshot and learning
        outcomes. Students spend hours formatting these by hand. {AUTHOR.name} built LabForge so that time goes into
        understanding the programs instead: it writes the code, actually runs it, captures the real output, and lays
        the report out the way the college asks for it.
      </p>
      <h2>What went into it</h2>
      <ul>
        <li>A Python (FastAPI) backend that compiles and runs Java, Python, C, C++, Node.js, React, SQL and web pages in isolation.</li>
        <li>AI models from several providers with automatic failover, and a cache so a whole class uploading the same sheet costs one call.</li>
        <li>A React frontend where the live page preview is the editor, and Word and PDF output that follows a university layout.</li>
        <li>Safeguards so a report can only show output a program really printed.</li>
      </ul>
      {AUTHOR.links.length > 0 && (
        <>
          <h2>Find {AUTHOR.name} online</h2>
          <ul>
            {AUTHOR.links.map((url) => (
              <li key={url}>
                <a href={url} rel="me noopener" target="_blank">{url.replace(/^https:\/\/(www\.)?/, "")}</a>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="hint">
        LabForge is an independent project. It isn't affiliated with, sponsored or endorsed by {AUTHOR.affiliation}.
      </p>
    </>
  )
}

/** The short description under the page preview on the home page: visible to everyone, and to search engines. */
export function HomeIntro() {
  return (
    <section className="intro" aria-labelledby="intro-title">
      <h1 id="intro-title">LabForge: {TAGLINE.toLowerCase()}</h1>
      <p>
        Upload the experiment sheet from your LMS and LabForge writes the lab report for you: the aim, objectives,
        working code for every Easy, Medium and Hard problem, the output each program really printed, and learning
        outcomes. Download it as a Word file or PDF, laid out the way your college asks for it. Free: sign in with your
        college email.
      </p>
      <ul className="intro__points">
        <li><b>Real output.</b> Every program is compiled and run; Matplotlib plots and web pages are captured as images.</li>
        <li><b>Any practical subject.</b> Java, Python, C, C++, Node.js, React, SQL, HTML/CSS/JS.</li>
        <li><b>Understand it.</b> "Explain this code" walks through each program and lets you practise viva questions.</li>
        <li><b>Your format.</b> A university CSE layout or a plain one, with your name, UID and subject filled in.</li>
      </ul>
      <p className="intro__by">
        Made by <a href={AUTHOR_PATH}>{AUTHOR.name}</a>, a student at {AUTHOR.affiliation}.{" "}
        <a href="/guide">How to use it</a> · <a href="/faq">FAQ</a>
      </p>
    </section>
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
      <h2>Who made it</h2>
      <p>
        LabForge was designed and built by <a href={AUTHOR_PATH}>{AUTHOR.name}</a>, a student at{" "}
        {AUTHOR.affiliation}.
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
  const flagDays = meta?.auth.flag_days ?? 30
  return (
    <>
      <h1>Privacy policy</h1>
      <p>Last updated {UPDATED}.</p>
      <p>
        This policy explains what LabForge collects when you use the website, why, how long it is kept, who else
        receives it, and how to have it deleted. Questions and requests: <Contact />.
      </p>

      <h2>Your account</h2>
      <p>
        To write reports you sign in with your college email address. We send it a 6-digit code; there is no password.
        For your account we keep: your email address, when you created the account and last signed in, a one-way code
        of the IP address you last signed in from, and a record of each report you wrote (the time, and whether it used
        a free report or an extra one). We use this to give every student a fair share of free reports and to stop
        abuse. Signing in puts one cookie in your browser that keeps you signed in for 30 days. It isn't used for
        advertising.
      </p>

      <h2>What stays on your device</h2>
      <p>
        Your name, UID, branch, section, semester, subjects, your report format and your latest report are saved in
        this browser's local storage so you don't have to type them again. So is a random id for this browser, which we
        use only to count your limits.
      </p>
      <p>
        Your finished reports (the Word and PDF files) are saved in this browser too, under "Your reports", locked with
        a key that only your account gets. We don't keep a history of your reports on our server. They exist only on
        the device you made them on, and clearing this site's data deletes them.
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
          <b>A copy of sessions that went wrong.</b> When a program fails, can't be run here, or the report can't be
          written, we keep a copy of that session so we can find out why and fix it: the sheet text (without your
          details from its header), the code, including code you changed yourself, its input, its output and the error
          messages, together with your account's email address. It is kept for {flagDays} days and is seen only by the
          person who runs LabForge. This copy stays for those {flagDays} days even if you delete the report.
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
          <b>Our email provider</b> receives your email address so the sign-in code can be delivered.
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
        <li>
          Remove a saved report from your device under "Your reports", or clear everything saved on your device by
          clearing this site's data in your browser.
        </li>
        <li>Sign out at any time. To delete your account and everything linked to it, write to us.</li>
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
      <h2>Your account</h2>
      <ul>
        <li>
          You need an account to write reports. You sign in with a code sent to your own college email address. Use
          only an address that was issued to you.
        </li>
        <li>One account per student. Don't share your account or your sign-in codes, and don't make extra accounts.</li>
        <li>You are responsible for what is done with your account.</li>
        <li>
          We may suspend or close an account that breaks these terms, and we may stop offering accounts to an email
          domain.
        </li>
      </ul>
      <h2>Free reports and limits</h2>
      <p>
        Each account gets a number of free reports per day or per month; the number is shown when you sign in and may
        change. A report that fails to be written doesn't count. We may later offer extra reports, for example in
        return for watching an advertisement. Free and extra reports have no cash value, can't be transferred or
        refunded, and unused free reports don't carry over. Trying to get around the limits, for example with several
        accounts or automated requests, isn't allowed.
      </p>
      <h2>Your reports are kept on your device</h2>
      <p>
        We delete a report's files from our server after a few hours, and we don't keep a history of your reports.
        Finished reports are saved only in the browser you made them in. If you clear your browser's data, change
        device or lose it, they are gone and we can't restore them. Keep your own copy of anything you need.
      </p>
      <h2>Sessions that go wrong</h2>
      <p>
        When a program fails or can't be run, or a report can't be written, we keep a copy of that session (the sheet
        text, the code including your changes, its input, output and errors, and your account's email address) for a
        limited time so we can fix the problem and add support for what was missing. By using LabForge you agree to
        this. The privacy policy says how long it is kept.
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
        <li>Don't try to access other people's reports or accounts.</li>
      </ul>
      <p>We may limit or block use that puts the service or other users at risk.</p>
      <h2>Age</h2>
      <p>You must be 18 or older, or have permission from a parent or guardian.</p>
      <h2>Changes</h2>
      <p>
        If these terms change, the date at the top changes too. If you keep using LabForge after a change, you accept
        the new terms.
      </p>
      <h2>Contact</h2>
      <p>
        Questions about these terms: <Contact />.
      </p>
    </>
  )
}
