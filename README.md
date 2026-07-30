# FindIt Campus

A Geo-Temporal Fusion Framework for Intelligent Lost and Found Matching

## Overview

FindIt Campus is an intelligent, multi-modal lost and found system designed for college campuses. It replaces informal recovery methods such as WhatsApp groups, notice boards, and manual desks with a structured, AI-driven platform that improves the chances of reuniting lost items with their rightful owners.

The system leverages text and image understanding, geo-temporal signals, and confidence-calibrated matching to identify potential matches between lost and found reports.

---

## Key Features

### Multi-Modal Matching

* Combines text descriptions and images for accurate matching
* Uses Sentence Transformers for text similarity and CLIP for image similarity
* Handles variations in descriptions (e.g., "black wallet" vs "dark brown leather wallet")

---

### Confidence-Calibrated Scoring

* Generates interpretable match probability scores
* Uses calibration layers, reliability diagrams, and Expected Calibration Error (ECE)

---

### Geo-Temporal Fusion

* Incorporates location proximity and time decay
* Ensures relevance based on where and when items were lost or found

---

### Smart Disambiguation

* If top matches are too close, the system asks targeted follow-up questions
* Improves match accuracy using attribute-level clarification

---

### Attribute Extraction Layer

* Extracts structured attributes such as color, brand, and category
* Helps detect mismatches not captured by embeddings

---

### Asymmetric Verification System

* Lost report owner proves ownership via detailed description
* Claimant must answer hidden verification questions before access is granted
* Contact details are revealed only after successful validation

---

### Custody Ledger and Audit Trail

* Records every handover with item details, claimant, verifier, and date
* Ensures transparency and accountability

---

### High-Risk Item Handling

* Special handling for IDs, phones, and academic documents
* Includes priority matching, escalation if unclaimed, and redaction of sensitive information

---

### QR Tag Pre-Registration

* Allows users to pre-register valuables
* Generates QR tags for identification
* Sends alerts when items are scanned

---

### Real-Time Notifications

* Instant updates via WebSockets and email alerts

---

## Tech Stack

### Frontend

* React (Progressive Web App)

### Backend

* FastAPI (Python)

### Database

* PostgreSQL (stores report metadata, embeddings, and custody records)

### AI/ML Components

* Sentence Transformers
* CLIP

### Communication

* WebSockets
* Email notifications

---

## Evaluation

The system is evaluated using curated lost and found datasets based on:

* Precision and recall
* Comparison with text-only and image-only baselines
* Calibration quality metrics
* Impact of missing modalities and disambiguation

---

## Project Structure

```
FindIt-Campus/
│
├── frontend/          # React PWA
├── backend/           # FastAPI server
├── models/            # ML models & embeddings
├── database/          # PostgreSQL schemas
├── utils/             # Helper functions
├── docs/              # Documentation
└── README.md
```

---

## Setup Instructions

### Clone the Repository

```
git clone https://github.com/your-username/findit-campus.git
cd findit-campus
```

### Backend Setup

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Setup

```
cd frontend
npm install
npm start
```

---

## Future Enhancements

* Mobile application support
* Campus-wide deployment dashboard
* Advanced fraud detection
* Integration with campus security systems

---

## Team

* Mehwish
* Mansi Sharma
* Aarushi Chaudhary

---

## Impact

FindIt Campus transforms the lost-and-found process from an informal and inefficient system into a structured, intelligent, and reliable platform, significantly improving recovery rates and reducing manual effort.

---

## License

This project is for academic and research purposes.
