# PHI Masker

A production-grade CLI and API pipeline that reads parquet files containing medical/document data, detects PHI/PII entities using the `nvidia/gliner-PII` model from HuggingFace, masks them with entity-type tags, and outputs the cleaned file.

## Features

- Detects 17+ PHI/PII entity types (names, SSNs, phone numbers, emails, dates, medical record numbers, and more)
- Configurable confidence threshold and entity-type filtering
- Batch processing for large datasets
- Post-masking residual PHI validation with regex patterns
- Quality grading (A/B/C/D) based on confidence and coverage
- Output in parquet, CSV, or JSON format
- REST API with synchronous and asynchronous processing modes
- In-memory job manager with status tracking and result download

## Project Structure

```
phi_masker/
├── input/                      # Drop parquet files here
├── output/                     # Masked results written here
├── labels/
│   └── default_labels.md       # Entity label definitions
├── src/
│   ├── config.py               # PipelineConfig dataclass
│   ├── label_parser.py         # Markdown label parser
│   ├── preprocessor.py         # Data cleaning
│   ├── masker.py               # GLiNER inference + masking
│   ├── postprocessor.py        # Validation, stats, grading
│   └── pipeline.py             # 6-step orchestrator
├── api/
│   ├── app.py                  # FastAPI factory
│   ├── routes.py               # All endpoints
│   ├── schemas.py              # Pydantic models
│   └── tasks.py                # Async job manager
├── cli.py                      # Click entry point
└── requirements.txt
```

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────┐
│                     PHI Masking Pipeline                │
│                                                         │
│  Step 1: Load Labels (Markdown → list of entity types)  │
│      ↓                                                  │
│  Step 2: Load Input (parquet → DataFrame, validate cols) │
│      ↓                                                  │
│  Step 3: Preprocess (drop nulls/dupes, strip whitespace) │
│      ↓                                                  │
│  Step 4: Detect & Mask (GLiNER → [ENTITY_TYPE] tags)    │
│      ↓                                                  │
│  Step 5: Post-process (residual check, stats, grade)    │
│      ↓                                                  │
│  Step 6: Save Output (parquet / csv / json)             │
└─────────────────────────────────────────────────────────┘
```

## Setup

```bash
cd phi_masker
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## CLI Usage

### Mask a file

```bash
# Basic usage — mask with defaults
python cli.py mask -i input/records.parquet

# Specify output format and confidence threshold
python cli.py mask \
  -i input/records.parquet \
  -o output/ \
  -a 0.8 \
  -f csv

# Restrict to specific entity types
python cli.py mask \
  -i input/records.parquet \
  -e person \
  -e "email address" \
  -e "social security number"

# Full options
python cli.py mask \
  --input input/records.parquet \
  --output-dir output/ \
  --labels labels/default_labels.md \
  --batch-size 64 \
  --min-accuracy 0.75 \
  --entities person \
  --entities "phone number" \
  --output-format json \
  --log-level DEBUG
```

### Start the API server

```bash
# Default (0.0.0.0:8000)
python cli.py serve

# Custom host and port with auto-reload
python cli.py serve --host 127.0.0.1 --port 9000 --reload
```

## API Usage

Interactive docs available at `http://localhost:8000/docs` once the server is running.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Service health and version |
| POST | `/api/v1/upload` | Upload a `.parquet` file to `input/` |
| POST | `/api/v1/process` | Run the pipeline (sync or async) |
| GET | `/api/v1/status/{job_id}` | Check job status |
| GET | `/api/v1/results/{job_id}` | Download the masked output file |
| GET | `/api/v1/report/{job_id}` | Get statistics and quality report |
| GET | `/api/v1/jobs` | List all jobs |

### Sample curl commands

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Upload a file
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@input/records.parquet"

# Run synchronously
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "input/records.parquet",
    "min_accuracy": 0.75,
    "output_format": "csv"
  }'

# Run asynchronously
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "input/records.parquet",
    "async_mode": true
  }'

# Check job status
curl http://localhost:8000/api/v1/status/<job_id>

# Download masked output
curl -O http://localhost:8000/api/v1/results/<job_id>

# Get full report
curl http://localhost:8000/api/v1/report/<job_id>

# List all jobs
curl http://localhost:8000/api/v1/jobs
```

## Labels File Format

Entity labels are defined in a Markdown file. Lines starting with `-`, `*`, or `+` are parsed as labels. Headings and plain text are ignored.

```markdown
# PHI/PII Entity Labels

- person
- phone number
- email address
- social security number
- date of birth
```

Custom labels file:

```bash
python cli.py mask -i input/file.parquet -l labels/custom_labels.md
```

## Input File Schema

The input parquet file must contain exactly these four columns:

| Column | Type | Description |
|--------|------|-------------|
| auditId | string | Unique audit identifier |
| fileName | string | Source document filename |
| pageNo | int | Page number within the document |
| Content | string | Raw text to scan for PHI |

## Output

The masked output file is written to `output/` with the naming pattern:

```
{original_stem}_masked_{YYYYMMDD_HHMMSS}.{format}
```

Example: `records_masked_20240115_143022.parquet`

The `Content` column has PHI spans replaced with tags, e.g.:
- `John Smith` → `[PERSON]`
- `555-867-5309` → `[PHONE_NUMBER]`
- `john@example.com` → `[EMAIL_ADDRESS]`
