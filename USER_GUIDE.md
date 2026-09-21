# LabForge User Guide

Welcome to **LabForge**, your automated companion for generating Java programming lab reports! LabForge takes your rough notes and code, compiles the code to verify it works, uses AI to write theoretical sections and explanations, and produces a perfectly formatted DOCX lab report.

This guide will walk you through how to use the new Web Interface to generate your reports quickly and easily.

## Prerequisites

Before using the Web Interface, you need to ensure your profile is set up. If you haven't done this yet, open your terminal and run:

```bash
python labforge.py setup
```

This CLI command will prompt you for your name, roll number, and subject configurations, saving them to `.config/profile.yaml`.

## Starting the Web Interface

1. Open your terminal or command prompt.
2. Navigate to the LabForge project directory.
3. Start the web server using Uvicorn:
   ```bash
   uvicorn apps.api.main:app --reload
   ```
4. Open your web browser and go to: [http://localhost:8000](http://localhost:8000)

## Using the Dashboard

When you open the web interface, you'll see a sleek dashboard with three main sections.

### 1. Current Profile & Subject Setup
- **Current Profile:** Displays your configured name, roll number, and batch.
- **Subject Setup:** Use the dropdown menu to select the subject for which you want to generate a report.

### 2. Generate Report
This is where the magic happens!
- **Upload Notes:** Click the dashed upload area to select your `source-notes.md` file, or simply drag and drop the file directly into the box.
  *(Note: Your source file should contain your Java code block and any notes you want the AI to incorporate).*
- **Force Refresh (Optional):** Check this box if you want to bypass the AI cache and force LabForge to generate a brand new response from the AI provider.
- **Generate:** Once a subject is selected and a file is uploaded, click the **Generate Report** button.

### 3. Generation Complete
While generating, a loading screen will appear. Once finished, the Results Panel will display:
- **Experiment Number:** The detected experiment number.
- **Compilation Status:** Indicates if your Java code compiled and executed successfully.
- **AI Generation Status:** Indicates if the AI successfully generated the theoretical content.
- **Download Buttons:** Click "Download DOCX" to save your generated lab report!

## Troubleshooting

- **"Failed to load configuration"**: Ensure you have run the CLI setup first.
- **"Compilation Failed"**: The AI attempts to fix minor syntax errors, but if your code has major issues, LabForge might fail to compile it. Check your `source-notes.md` code blocks.
- **Missing API Keys**: LabForge uses AI to write the reports. Make sure your `.env` file is properly configured with your chosen provider's API key.

Happy forging!
