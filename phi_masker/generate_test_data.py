"""Generate a realistic test parquet file with PHI/PII content for PHI_MASKER."""

import random
import uuid
from datetime import date, timedelta

import pandas as pd

# ── Seed for reproducibility ────────────────────────────────────────────────
random.seed(42)

# ── Realistic data pools ────────────────────────────────────────────────────
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "William", "Barbara", "David", "Susan", "Richard", "Jessica",
    "Joseph", "Sarah", "Thomas", "Karen", "Charles", "Lisa", "Christopher",
    "Nancy", "Daniel", "Betty", "Matthew", "Margaret", "Anthony", "Sandra",
    "Mark", "Ashley", "Donald", "Emily", "Steven", "Dorothy", "Paul",
    "Kimberly", "Andrew", "Carol", "Kenneth", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
    "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
    "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
    "Indianapolis", "San Francisco", "Seattle", "Denver", "Nashville",
]

STATES = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "GA", "WA"]

STREET_NAMES = [
    "Oak St", "Maple Ave", "Cedar Blvd", "Elm Dr", "Pine Rd",
    "Washington Blvd", "Lincoln Ave", "Park Lane", "River Rd", "Lake Dr",
]

INSURANCE_PREFIXES = ["BCBS", "AETNA", "UHC", "CIGNA", "HUMANA", "KAISER"]
DIAGNOSES = [
    "hypertension", "type 2 diabetes mellitus", "chronic kidney disease stage 3",
    "atrial fibrillation", "major depressive disorder", "anxiety disorder",
    "hyperlipidemia", "obstructive sleep apnea", "GERD", "hypothyroidism",
    "osteoarthritis", "asthma", "COPD", "coronary artery disease", "anemia",
]

MEDICATIONS = [
    "Metformin 500mg", "Lisinopril 10mg", "Atorvastatin 20mg", "Omeprazole 20mg",
    "Levothyroxine 50mcg", "Amlodipine 5mg", "Metoprolol 25mg", "Sertraline 50mg",
    "Gabapentin 300mg", "Hydrochlorothiazide 25mg",
]

DOCUMENT_TYPES = [
    "Discharge_Summary", "Progress_Note", "Lab_Report",
    "Radiology_Report", "Referral_Letter", "Prescription",
    "Insurance_Claim", "Consent_Form", "Intake_Assessment", "Follow_Up_Note",
]

# ── Helper generators ────────────────────────────────────────────────────────

def full_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def phone() -> str:
    area = random.randint(200, 999)
    mid  = random.randint(200, 999)
    end  = random.randint(1000, 9999)
    fmt  = random.choice(["{}-{}-{}", "({}) {}-{}", "{}.{}.{}"])
    return fmt.format(area, mid, end)

def email(name: str) -> str:
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hospital.org", "clinic.net"]
    parts = name.lower().split()
    return f"{parts[0]}.{parts[-1]}{random.randint(1,99)}@{random.choice(domains)}"

def ssn() -> str:
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"

def dob() -> str:
    start = date(1940, 1, 1)
    end   = date(2005, 12, 31)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days))).strftime("%m/%d/%Y")

def address() -> str:
    return (
        f"{random.randint(100, 9999)} {random.choice(STREET_NAMES)}, "
        f"{random.choice(CITIES)}, {random.choice(STATES)} "
        f"{random.randint(10000, 99999)}"
    )

def mrn() -> str:
    return f"MRN{random.randint(1000000, 9999999)}"

def insurance_id() -> str:
    prefix = random.choice(INSURANCE_PREFIXES)
    return f"{prefix}{random.randint(100000000, 999999999)}"

def ip_addr() -> str:
    return ".".join(str(random.randint(1, 254)) for _ in range(4))

def credit_card() -> str:
    groups = [str(random.randint(1000, 9999)) for _ in range(4)]
    return "-".join(groups)

# ── Content templates ────────────────────────────────────────────────────────

def make_discharge_summary(name, dob_str, addr, ph, em, ssn_str, mrn_str, ins) -> str:
    return (
        f"DISCHARGE SUMMARY\n\n"
        f"Patient Name: {name}\n"
        f"Date of Birth: {dob_str}\n"
        f"Address: {addr}\n"
        f"Phone: {ph}\n"
        f"Email: {em}\n"
        f"SSN: {ssn_str}\n"
        f"Medical Record Number: {mrn_str}\n"
        f"Insurance ID: {ins}\n\n"
        f"Diagnosis: {random.choice(DIAGNOSES).capitalize()}\n"
        f"The patient {name} was admitted on {dob_str} and discharged after "
        f"successful treatment. Follow-up scheduled in 2 weeks.\n"
        f"Medications prescribed: {random.choice(MEDICATIONS)}, {random.choice(MEDICATIONS)}.\n"
        f"Contact {name} at {ph} or {em} for any concerns."
    )

def make_progress_note(name, dob_str, ph, mrn_str) -> str:
    diag = random.choice(DIAGNOSES)
    med  = random.choice(MEDICATIONS)
    return (
        f"PROGRESS NOTE\n\n"
        f"Patient: {name} | DOB: {dob_str} | MRN: {mrn_str}\n"
        f"Today {name} presents with complaints related to {diag}. "
        f"Current medication regimen includes {med}. "
        f"Vital signs stable. Patient reachable at {ph}.\n"
        f"Plan: Continue current therapy. Lab work ordered. "
        f"Referral to specialist considered."
    )

def make_lab_report(name, mrn_str, dob_str) -> str:
    return (
        f"LABORATORY REPORT\n\n"
        f"Patient: {name}\n"
        f"MRN: {mrn_str}\n"
        f"DOB: {dob_str}\n\n"
        f"Test: Comprehensive Metabolic Panel\n"
        f"Glucose: {random.randint(70, 200)} mg/dL\n"
        f"BUN: {random.randint(7, 25)} mg/dL\n"
        f"Creatinine: {round(random.uniform(0.6, 1.4), 1)} mg/dL\n"
        f"HbA1c: {round(random.uniform(4.5, 10.0), 1)}%\n"
        f"Results reviewed and signed by attending physician for patient {name}."
    )

def make_radiology_report(name, dob_str, mrn_str) -> str:
    regions = ["chest", "abdomen", "pelvis", "spine", "knee", "skull"]
    modalities = ["CT", "MRI", "X-Ray", "Ultrasound", "PET scan"]
    return (
        f"RADIOLOGY REPORT\n\n"
        f"Patient: {name} | DOB: {dob_str} | MRN: {mrn_str}\n"
        f"Study: {random.choice(modalities)} {random.choice(regions)}\n\n"
        f"Findings: No acute abnormality detected for {name}. "
        f"Mild degenerative changes noted. No fractures. No masses identified.\n"
        f"Impression: Routine study within normal limits."
    )

def make_referral_letter(name, dob_str, ph, em, addr, ins) -> str:
    specialties = ["Cardiology", "Endocrinology", "Nephrology", "Oncology", "Neurology"]
    return (
        f"REFERRAL LETTER\n\n"
        f"Dear Specialist,\n\n"
        f"I am referring my patient {name}, DOB {dob_str}, for evaluation of "
        f"{random.choice(DIAGNOSES)}.\n\n"
        f"Patient contact: {ph}, {em}\n"
        f"Address: {addr}\n"
        f"Insurance: {ins}\n\n"
        f"Please see {name} at your earliest convenience. "
        f"I believe a {random.choice(specialties)} consultation is warranted.\n\n"
        f"Sincerely,\nDr. {random.choice(LAST_NAMES)}"
    )

def make_prescription(name, dob_str, ph, addr) -> str:
    return (
        f"PRESCRIPTION\n\n"
        f"Patient: {name}\n"
        f"DOB: {dob_str}\n"
        f"Address: {addr}\n"
        f"Phone: {ph}\n\n"
        f"Rx: {random.choice(MEDICATIONS)}\n"
        f"Dispense: {random.choice([30, 60, 90])} tablets\n"
        f"Refills: {random.randint(0, 5)}\n"
        f"Instructions: Take as directed. Do not share with others.\n"
        f"Prescriber: Dr. {random.choice(LAST_NAMES)}, NPI {random.randint(1000000000, 9999999999)}"
    )

def make_insurance_claim(name, dob_str, ssn_str, ins, cc) -> str:
    return (
        f"INSURANCE CLAIM FORM\n\n"
        f"Insured Name: {name}\n"
        f"Date of Birth: {dob_str}\n"
        f"SSN: {ssn_str}\n"
        f"Policy Number: {ins}\n"
        f"Credit Card on File: {cc}\n\n"
        f"Diagnosis Code: {random.choice(['Z00.00', 'E11.9', 'I10', 'J45.909', 'F32.1'])}\n"
        f"Procedure: Office visit\n"
        f"Amount Billed: ${random.randint(100, 5000)}.00\n"
        f"Claim submitted on behalf of {name}."
    )

def make_consent_form(name, dob_str, addr, ph, em, ssn_str) -> str:
    return (
        f"CONSENT FORM\n\n"
        f"I, {name}, born {dob_str}, residing at {addr}, "
        f"hereby consent to the proposed medical procedure.\n\n"
        f"Contact: {ph} | {em}\n"
        f"SSN (last 4): {ssn_str[-4:]}\n\n"
        f"I acknowledge that I have been informed of the risks and benefits. "
        f"Signed: {name}   Date: {dob_str}"
    )

def make_intake_assessment(name, dob_str, ph, em, addr, mrn_str, ins) -> str:
    return (
        f"INTAKE ASSESSMENT\n\n"
        f"Patient: {name}\n"
        f"DOB: {dob_str} | MRN: {mrn_str}\n"
        f"Address: {addr}\n"
        f"Phone: {ph}\n"
        f"Email: {em}\n"
        f"Insurance: {ins}\n\n"
        f"Chief Complaint: {random.choice(DIAGNOSES).capitalize()}\n"
        f"Allergies: {random.choice(['NKDA', 'Penicillin', 'Sulfa drugs', 'Aspirin'])}\n"
        f"Emergency Contact: {full_name()}, {phone()}"
    )

def make_follow_up(name, dob_str, ph, mrn_str, ip) -> str:
    return (
        f"FOLLOW-UP NOTE\n\n"
        f"Patient {name} (DOB: {dob_str}, MRN: {mrn_str}) attended follow-up today.\n"
        f"Patient reported improvement in {random.choice(DIAGNOSES)}.\n"
        f"Medication compliance confirmed. No adverse effects noted.\n"
        f"Patient portal IP logged: {ip}\n"
        f"Next appointment scheduled. Reach patient at {ph}."
    )

CONTENT_BUILDERS = [
    make_discharge_summary,
    make_progress_note,
    make_lab_report,
    make_radiology_report,
    make_referral_letter,
    make_prescription,
    make_insurance_claim,
    make_consent_form,
    make_intake_assessment,
    make_follow_up,
]

# ── Generate filenames (fewer than rows so many rows share a file) ───────────
NUM_FILES = 80
NUM_ROWS  = 1000

file_names = [
    f"{random.choice(DOCUMENT_TYPES)}_{str(uuid.uuid4())[:8].upper()}.pdf"
    for _ in range(NUM_FILES)
]

# ── Build rows ───────────────────────────────────────────────────────────────
rows = []
for _ in range(NUM_ROWS):
    name    = full_name()
    dob_str = dob()
    addr    = address()
    ph      = phone()
    em      = email(name)
    ssn_str = ssn()
    mrn_str = mrn()
    ins     = insurance_id()
    cc      = credit_card()
    ip      = ip_addr()

    fname = random.choice(file_names)
    # Pages within a document can go up to 20
    page_no = random.randint(1, 20)

    builder = random.choice(CONTENT_BUILDERS)
    # Each builder takes different args — map by function name
    fn_name = builder.__name__
    if fn_name == "make_discharge_summary":
        content = builder(name, dob_str, addr, ph, em, ssn_str, mrn_str, ins)
    elif fn_name == "make_progress_note":
        content = builder(name, dob_str, ph, mrn_str)
    elif fn_name == "make_lab_report":
        content = builder(name, mrn_str, dob_str)
    elif fn_name == "make_radiology_report":
        content = builder(name, dob_str, mrn_str)
    elif fn_name == "make_referral_letter":
        content = builder(name, dob_str, ph, em, addr, ins)
    elif fn_name == "make_prescription":
        content = builder(name, dob_str, ph, addr)
    elif fn_name == "make_insurance_claim":
        content = builder(name, dob_str, ssn_str, ins, cc)
    elif fn_name == "make_consent_form":
        content = builder(name, dob_str, addr, ph, em, ssn_str)
    elif fn_name == "make_intake_assessment":
        content = builder(name, dob_str, ph, em, addr, mrn_str, ins)
    elif fn_name == "make_follow_up":
        content = builder(name, dob_str, ph, mrn_str, ip)
    else:
        content = f"Generic note for {name}, DOB {dob_str}, phone {ph}."

    rows.append({
        "auditId": str(uuid.uuid4()),
        "fileName": fname,
        "pageNo": page_no,
        "Content": content,
    })

df = pd.DataFrame(rows, columns=["auditId", "fileName", "pageNo", "Content"])
df.to_parquet("input/medical_records.parquet", index=False)

print(f"Generated {len(df)} rows across {df['fileName'].nunique()} unique files")
print(f"Pages per file (sample):")
print(df.groupby("fileName").size().describe().to_string())
print(f"\nSaved to: input/medical_records.parquet")
print(f"File size: {__import__('os').path.getsize('input/medical_records.parquet') / 1024:.1f} KB")
