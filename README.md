# STI Predictive Model

A Django-based clinical decision-support prototype that combines patient data management, data ingestion, machine-learning prediction workflows, geospatial functionality and reporting.

> **Important:** This project is a software/ML portfolio prototype and must not be used as a substitute for qualified medical diagnosis or clinical decision-making.

## Overview

The project explores how a healthcare application can combine structured patient records with an ML prediction pipeline and operational reporting. The codebase is organised into separate components for patients, clinicians, data ingestion, prediction, reporting, compliance and geospatial functionality.

## Core Components

- Patient management
- Clinician workflows
- Data ingestion
- Machine-learning pipeline
- Prediction engine
- Geospatial services
- Reporting workflows
- Compliance-oriented application structure

## Technology Stack

- Python
- Django
- Machine learning / data processing
- HTML/CSS/JavaScript
- SQLite/PostgreSQL depending on environment

## Architecture

```text
Patient / Clinician
        |
        v
     Django App
   /     |       \
Patients Clinicians Reporting
        |
        v
   Data Ingestion
        |
        v
  ML Pipeline
        |
        v
Prediction Engine
        |
        v
 Reports / Decision Support
```

## Project Structure

```text
clinicians/          Clinician-facing functionality
data_ingestion/      Data ingestion workflows
ml_pipeline/         ML processing and training components
prediction_engine/   Prediction and inference logic
patients/            Patient management
moh_reporting/       Reporting functionality
geospatial/          Location-aware functionality
compliance/          Compliance-related functionality
config/              Django configuration
manage.py            Django management entry point
```

## Getting Started

### Clone the repository

```bash
git clone https://github.com/Eunice-ctrlz/STI-PREDICTIVE-MODEL.git
cd STI-PREDICTIVE-MODEL
```

### Create an environment

```bash
python -m venv .venv
```

Activate the environment and install the project's dependency file if present in the checkout.

### Configure environment variables

Copy the example configuration into a local environment file and provide the required values. Never commit real secrets.

### Database setup

```bash
python manage.py migrate
```

### Run the application

```bash
python manage.py runserver
```

## Data and Privacy

Healthcare-related data is sensitive. Do not commit real patient information, credentials or private datasets. Use synthetic or anonymised data for development and demonstrations.

## Model Evaluation

A production ML system should document its dataset provenance, preprocessing steps, train/validation/test split, evaluation metrics, baseline comparison, model version and limitations. Predictions should be independently validated before any clinical use.

## Security

The repository contains an environment configuration file intended for local configuration. Keep secrets outside version control and rotate credentials immediately if they are ever exposed.

## Roadmap

- Automated ML evaluation reports
- Model versioning and reproducible training
- Comprehensive automated tests
- API documentation
- Containerised deployment
- CI/CD quality gates
- Improved privacy and audit logging

## Author

**Eunice Muturi**

GitHub: https://github.com/Eunice-ctrlz
