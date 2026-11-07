# LabForge user guide

LabForge turns an experiment sheet into a lab report: aim, objectives, code, the output the code
really printed, and learning outcomes, laid out the way your college asks for it. The same guide
is on the website at `/guide`, with answers to common questions at `/faq`.

## On the website

1. **Your details.** Fill in your name, UID, branch, section and semester once. They're saved in
   your browser. Pick a report format: plain, or the CSE layout that follows the department's
   sample report.
2. **The sheet.** Upload the experiment sheet (PDF, Word, PowerPoint, text, or a .zip of your
   project) or paste its text, choose the language if the sheet doesn't say, and press
   **Write my report**.
3. **Wait for the programs.** Every program is compiled and run on the server. Java and Spring can
   take a minute or two. You can leave the page; the report keeps being written and comes back when
   you return.
4. **Check each task.** Read the code. Use **Explain this code** for a walkthrough and practice viva
   questions. If you change the code or the input, press **Run the changed code**: the output can't
   be typed in, it's always what the program printed. Programs that need a window, hardware or
   software the server doesn't have ask for your own screenshot.
5. **Download.** The Word file is made automatically; press **Make the PDF** for a PDF and page
   previews. When you're done you can **Delete this report from the server**.

Something wrong with a report? Use the thumbs down, or **Report a problem with this content**.

## On the command line

Set your details once, then write reports from sheets on disk:

```powershell
labforge profile set --name "Your Name" --uid 24BCS00000 --branch BE-CSE --section 719-A --semester 5th --university "Chandigarh University"
labforge generate --source "EXP-2.1.pdf" --subject "Competitive Coding - II" --code 24CSP-305
labforge batch --dir "C:\Users\me\Desktop\cc sem5" --subject "Competitive Coding - II" --skip-existing
labforge doctor
```

## Use it honestly

LabForge saves you formatting and screenshot work. Read and run the code yourself, make sure you
can explain it in your viva, and follow your institution's rules on what you may submit.
LabForge isn't affiliated with any university.
