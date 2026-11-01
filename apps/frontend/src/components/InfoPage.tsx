export type Route = "" | "about" | "privacy" | "terms"

export function InfoPage({ route, ttl }: { route: Exclude<Route, "">; ttl: number }) {
  return (
    <article className="info">
      <a className="info__back" href="#/">
        Back to your report
      </a>
      {route === "about" && <About />}
      {route === "privacy" && <Privacy ttl={ttl} />}
      {route === "terms" && <Terms />}
    </article>
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
        Java, Python (including NumPy, OpenCV, Matplotlib and scikit-image), Node.js with Express and Mongoose,
        React, and plain HTML/CSS/JS pages. Programs in other languages, or ones that need hardware or a desktop
        window, are left for you to run: add your own screenshot and it goes into the report.
      </p>
      <h2>Same sheet as your classmates?</h2>
      <p>
        When a sheet has been written before, LabForge reuses that work, which is why it's fast and free. Use
        "Write a different version" to get your own code and wording.
      </p>
      <h2>Use it honestly</h2>
      <p>
        LabForge saves you the formatting and the screenshots. Read the code before you submit it, run it yourself,
        and make sure you can explain it in your viva.
      </p>
    </>
  )
}

function Privacy({ ttl }: { ttl: number }) {
  return (
    <>
      <h1>Privacy</h1>
      <p>Last updated 1 November 2026.</p>
      <h2>What stays on your device</h2>
      <p>
        Your name, UID, branch, section, semester, subjects and your latest report are saved in this browser's local
        storage so you don't have to type them again. We don't have accounts and we don't receive this data until you
        make the Word or PDF file.
      </p>
      <h2>What we process</h2>
      <p>
        The experiment sheet you upload is sent to our server, trimmed, and passed to an AI provider (such as Google
        Gemini or Groq) to write the report. The programs, their output, your screenshots and the files we make are
        stored on our server for {ttl} hours and then deleted. Written sheets are kept in a cache, without any
        personal details, so the same sheet doesn't need writing twice.
      </p>
      <p>
        We keep a count of requests per IP address for a day to stop abuse. We don't sell data or build profiles.
      </p>
      <h2>Advertising</h2>
      <p>
        LabForge is free because of ads. We use Google AdSense, which uses cookies to show ads, including ads based on
        your earlier visits to this and other websites. You can turn off personalised ads in{" "}
        <a href="https://adssettings.google.com" rel="noopener noreferrer" target="_blank">
          Google's ad settings
        </a>
        . Read how{" "}
        <a href="https://policies.google.com/technologies/partner-sites" rel="noopener noreferrer" target="_blank">
          Google uses data from sites that use its services
        </a>
        .
      </p>
      <h2>Contact</h2>
      <p>For questions or deletion requests, open an issue on the project's GitHub page.</p>
    </>
  )
}

function Terms() {
  return (
    <>
      <h1>Terms</h1>
      <p>
        LabForge is provided as is, for free. Generated reports are a starting point: you are responsible for checking
        the content and for following your institution's academic integrity rules.
      </p>
      <p>
        Don't upload material you don't have the right to share, and don't use the service to run harmful code. We may
        limit or block use that puts the service or other users at risk.
      </p>
    </>
  )
}
