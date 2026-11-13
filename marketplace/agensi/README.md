# Agensi Marketplace Skill — Creator Release Guide
**Skill Package:** `anshora-business-intelligence-analyst`  
**Current Release Version:** `1.0.1` (Preserving `1.0.0`)

This directory contains the complete packaging, testing, and release toolchain for publishing the **ANSHora — Business Intelligence Analyst** skill on the Agensi Marketplace.

---

## 1. Directory Structure

```text
marketplace/agensi/
├── anshora-business-intelligence-analyst/   # Unbundled skill source directory
│   ├── SKILL.md                            # Primary skill specification with Agensi YAML frontmatter (v1.0.1)
│   ├── README.md                           # Buyer-facing quickstart & documentation
│   ├── requirements.txt                    # Python stdlib confirmation (zero pip packages)
│   ├── references/                         # Modular reference documentation suite (6 files)
│   │   ├── analytical-methodology.md       # 6-stage lifecycle, driver decomposition, epistemic separation
│   │   ├── financial-formulas.md           # Weighted margin, derived cost, paired rows, dual reporting
│   │   ├── data-quality-rules.md           # 4-pillar health score, zero-IQR guardrails, duplicate audits
│   │   ├── evidence-and-reporting.md       # Numerical traceability, 7-section report format, decision log
│   │   ├── optional-agensi-tools.md        # Agensi tool discovery protocol, pricing quotes, privacy rules
│   │   └── privacy-and-safety.md           # Local-first execution, sandbox safety, prompt injection defense
│   ├── scripts/
│   │   └── analyze_csv.py                  # Standalone deterministic analysis helper (stdlib only, <20 KB)
│   └── examples/
│       ├── sample-business-data.csv        # Synthetic 25-row retail test dataset
│       └── expected-analysis.md            # Complete reference output demonstrating standard of quality
├── releases/                               # Release build directory
│   ├── build_package.py                    # Multi-version packager (flat root layout, excludes caches/git)
│   ├── anshora-business-intelligence-analyst-v1.0.0.zip          # Preserved v1.0.0 release archive (25.8 KB)
│   ├── anshora-business-intelligence-analyst-v1.0.0.zip.sha256   # SHA-256 for v1.0.0
│   ├── anshora-business-intelligence-analyst-v1.0.1.zip          # Production v1.0.1 release archive (29.4 KB)
│   └── anshora-business-intelligence-analyst-v1.0.1.zip.sha256   # SHA-256 for v1.0.1
├── tests/                                  # Test and validation suite
│   ├── test_analyze_csv.py                 # 25 unit and regression test scenarios
│   └── validate_package.py                 # Source and ZIP integrity validator (48 checks)
├── reports/
│   ├── package-validation.md               # v1.0.0 validation and compliance audit sign-off
│   ├── FINAL_QA_REPORT.md                  # Independent product QA report
│   └── v1.0.1-validation-report.md         # v1.0.1 targeted quality fixes validation report
├── LISTING.md                              # Complete marketplace listing copy and product description
└── README.md                               # This creator release guide
```

---

## 2. Testing and Validation Commands

Run these commands from the root of the ANSHora repository to verify package integrity before submission:

### 2.1 Run Analytical Helper Test Suite (25 Test Cases)
```powershell
python marketplace/agensi/tests/test_analyze_csv.py
```
*Expected Output:* `All 25/25 tests passed successfully!`

### 2.2 Run Full Package & Security Validator (48 Checks)
```powershell
python marketplace/agensi/tests/validate_package.py --version v1.0.1
```
*Expected Output:* `RESULT: VALIDATION PASSED (0 errors)`

### 2.3 Rebuild Release ZIP Archive
To rebuild the v1.0.1 archive (or any specific version):
```powershell
python marketplace/agensi/releases/build_package.py --version v1.0.1
```
*Result:* Automatically packages the archive with `SKILL.md` at root, cleans up transient files, updates the ZIP, and outputs the new SHA-256 digest into `anshora-business-intelligence-analyst-v1.0.1.zip.sha256`.

---

## 3. Agensi Marketplace Submission Walkthrough

Follow these steps when you are ready to publish the skill:

### Step 1: Sign in to Agensi Creator Portal
1. Navigate to the **Agensi Creator Dashboard** (`https://agensi.app/creator` or equivalent portal).
2. Connect your verified creator profile and payout account (Stripe Connect).

### Step 2: Create a New Skill Listing
1. Click **Create New Skill / Add Listing**.
2. **Title:** Copy exactly from `marketplace/agensi/LISTING.md` (`ANSHora — Business Intelligence Analyst`).
3. **Slug:** Set to `anshora-business-intelligence-analyst`.
4. **Category:** Select `Business Intelligence & Data Analytics`.
5. **Pricing:** Select **One-Time Purchase**, set price to **\$9.00 USD**.

### Step 3: Upload Package Archive
1. In the **Skill Package Upload** section, select:
   `marketplace/agensi/releases/anshora-business-intelligence-analyst-v1.0.1.zip`
2. Confirm the uploaded checksum matches:
   `a1a7c7c37ca73e6fd581b628b4741e7fac52b4a3d2a85be91a1aef3d1add6302`
3. Agensi's automated intake linter will verify that `SKILL.md` is at the root and that no banned files exist.

### Step 4: Populate Listing Metadata & Copy
Open `marketplace/agensi/LISTING.md` and copy the respective sections into the Agensi web form:
- **Short Summary:** Copy the 1-paragraph summary.
- **Full Description:** Copy the markdown description, deliverables, supported inputs, and sample output.
- **FAQ:** Copy the 5 Q&A entries.
- **Tags:** `business-intelligence`, `decision-intelligence`, `data-analytics`, `profit-analysis`, `executive-reporting`, `kpi-engine`, `data-health`.

### Step 5: Submit for Marketplace Review
1. Review the submission preview.
2. Confirm compliance with Agensi Marketplace guidelines (zero malware, zero telemetry, local execution, clear pricing).
3. Click **Submit for Review**.
4. Typical marketplace review latency is 24–48 hours.

---

## 4. Key Architectural Guarantees for Reviewers

- **Zero-Dependency Architecture:** Requires only standard Python 3.8+ library (`csv`, `json`, `math`, `datetime`, `collections`, `re`).
- **Mathematical Determinism:** Weighted gross margins are strictly computed as $(\sum \text{Profit} / \sum \text{Revenue}) \times 100$ to prevent hallucinated row-level percentage averages.
- **Consistently Paired Rows:** Gross profit and margin are derived strictly over valid paired rows; unpaired revenue is explicitly noted.
- **Dual Reporting:** Headline KPIs are provided both across all rows and with exact duplicates isolated.
- **Data Safety:** Purely read-only; never alters, truncates, or overwrites user data.
- **Zero Secret Exposure:** Verified 100% clean of API keys, `.env` files, internal credentials, or personal tokens.
