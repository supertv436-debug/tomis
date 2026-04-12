# T.O.M.i.S. CORE v4.3

AI-powered assistant for the Department of Technological Equipment, Machine Building, and Standardization at Karaganda Technical University (KTU). Helps faculty automate creation of educational documentation (syllabuses, calendar plans, exam tickets) using AI.

## Tech Stack

- **Backend:** Python 3.12, Flask
- **AI:** Groq API (Llama 3.3-70b model)
- **Database:** SQLite (`tomis_memory.db`) for storing API key
- **Document processing:** PyMuPDF (PDF), python-docx (DOCX)
- **Frontend:** Vanilla HTML/CSS/JS served by Flask (index.html)

## Project Structure

```
app.py              - Main Flask backend (all API routes and document logic)
index.html          - Frontend interface (served as raw HTML to avoid Jinja2 conflicts)
requirements.txt    - Python dependencies
tomis_memory.db     - SQLite database for config (API key)
templates.json      - Metadata for document templates
TEMPLATES/          - DOCX template files for document generation
EXPORTS/            - Generated documents output directory
uploads/            - Temporary file storage for uploads
```

## Key API Routes

- `GET /` — Serves the frontend
- `POST /api/set_key` — Store Groq API key (must start with `gsk_`)
- `POST /api/upload` — Upload PDF/DOCX syllabus file
- `POST /api/ask` — Ask AI a question about uploaded document
- `POST /api/generate` — Generate calendar plan or exam tickets
- `GET /api/templates` — List available DOCX templates
- `GET /download/<filename>` — Download generated document

## Running the App

The app runs on port 5000 via the "Start application" workflow using `python app.py`.

## Notes

- `index.html` uses `{{...}}` JS template syntax, so it must NOT be rendered through Jinja2. It is served as raw HTML via `open()`.
- Groq API key is stored in SQLite and required for AI features.
- Place DOCX templates in the `TEMPLATES/` folder for document generation.
