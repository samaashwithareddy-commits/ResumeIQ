"""Fictional demonstration data for ResumeIQ.

Everything here is invented for the hackathon demo and is clearly labelled in
the UI. The sample job description is a realistic software-engineering
internship posting for a fictional company.
"""

from __future__ import annotations

from database import repo
from services.matcher import parse_job_description, score_match

DEMO_PROFILE = {
    "full_name": "Aarav Sharma",
    "headline": "Final-year B.Tech CSE student · backend & full-stack developer",
    "email": "aarav.sharma@example.com",
    "phone": "+91 90000 12345",
    "location": "Bengaluru, India",
    "linkedin": "https://www.linkedin.com/in/aarav-sharma-demo",
    "github": "https://github.com/aarav-sharma-demo",
    "summary": (
        "Final-year Computer Science student who enjoys building reliable backend services and "
        "shipping small full-stack products. Comfortable with Python, Flask and SQL, and currently "
        "exploring cloud deployment with Docker."
    ),
    "skills": [
        "Python",
        "Java",
        "JavaScript",
        "React",
        "Node.js",
        "Flask",
        "SQL",
        "MongoDB",
        "Git",
        "GitHub",
        "Docker",
        "REST APIs",
        "Pandas",
        "NumPy",
        "HTML",
        "CSS",
        "Data Structures",
        "Algorithms",
        "Problem Solving",
        "Communication",
    ],
    "education": [
        {
            "institution": "Vellore Institute of Technology",
            "degree": "B.Tech",
            "field": "Computer Science and Engineering",
            "start_date": "2021",
            "end_date": "2025",
            "score": "CGPA 8.7/10",
            "location": "Vellore, India",
        },
        {
            "institution": "Delhi Public School",
            "degree": "Higher Secondary",
            "field": "Science (PCM + Computer Science)",
            "start_date": "2019",
            "end_date": "2021",
            "score": "92.4%",
            "location": "Bengaluru, India",
        },
    ],
    "projects": [
        {
            "name": "CampusConnect — student collaboration app",
            "tech": "React, Node.js, Express.js, MongoDB",
            "link": "https://github.com/aarav-sharma-demo/campusconnect",
            "description": (
                "Built a MERN application where students form study groups, share notes and RSVP to campus events.\n"
                "Designed REST APIs with Node.js and Express for group, note and event management.\n"
                "Added role-based access control and server-side input validation to protect student data."
            ),
        },
        {
            "name": "SignalSpeak — sign language translator",
            "tech": "Python, TensorFlow, OpenCV, Flask",
            "link": "https://github.com/aarav-sharma-demo/signalspeak",
            "description": (
                "Trained a convolutional neural network on 2,000 labelled hand-sign images and reached 91% test accuracy.\n"
                "Served the model through a Flask REST API and a lightweight browser demo.\n"
                "Wrote unit tests for the preprocessing pipeline with pytest."
            ),
        },
        {
            "name": "ExpenseIQ — personal finance dashboard",
            "tech": "Flask, SQLite, Pandas, Chart.js",
            "link": "https://github.com/aarav-sharma-demo/expenseiq",
            "description": (
                "Built a Flask and SQLite dashboard that categorises monthly expenses and highlights overspending.\n"
                "Automated monthly CSV imports with Pandas and generated category-wise spending charts."
            ),
        },
    ],
    "experience": [
        {
            "role": "Backend Developer Intern",
            "company": "Zeta Innovations",
            "start_date": "May 2024",
            "end_date": "Jul 2024",
            "location": "Bengaluru, India",
            "description": (
                "Built three Flask endpoints for an internal reporting tool and documented them for the analytics team.\n"
                "Optimised a slow SQL report query, cutting its runtime from 8 seconds to 2 seconds.\n"
                "Participated in code reviews and fixed bugs reported by the QA team."
            ),
        }
    ],
    "certifications": [
        {
            "name": "AWS Certified Cloud Practitioner",
            "issuer": "Amazon Web Services",
            "year": "2024",
        },
        {
            "name": "Meta Front-End Developer Professional Certificate",
            "issuer": "Coursera",
            "year": "2023",
        },
    ],
    "achievements": [
        "Finalist, Smart India Hackathon 2024 (national level)",
        "Winner, VIT Internal Hackathon 2024",
        "Solved 350+ data-structure problems on LeetCode",
    ],
}

SAMPLE_JOB = {
    "title": "Software Engineer Intern — Backend Platform",
    "company": "Northwind Labs",
    "url": "",
    "description": """Software Engineer Intern — Backend Platform
Northwind Labs · Bengaluru, India (Hybrid)

About the role
We build the data platform behind Northwind's shipping products. As a backend engineering intern you will work with senior engineers on services that power real-time shipment tracking for thousands of merchants.

What you'll do
- Build and maintain REST APIs in Python using Flask for the shipment tracking service
- Work with PostgreSQL and Redis to model and cache high-volume tracking events
- Containerise services with Docker and ship them through our CI/CD pipeline
- Write unit tests and participate in code reviews with the platform team
- Collaborate with product and design to turn requirements into small, reliable features

Requirements
- Currently pursuing a bachelor's degree in Computer Science or a related field
- Strong programming skills in Python and familiarity with SQL
- Experience building web services with Flask or a similar framework
- Working knowledge of Git and collaborative development workflows
- Understanding of REST API design and unit testing
- Good communication and problem-solving skills
- 0-1 years of hands-on experience with Python (internships and projects count)

Preferred
- Exposure to AWS or another cloud platform
- Familiarity with Kubernetes or container orchestration
- Experience with TypeScript or JavaScript on a frontend
- Interest in distributed systems and performance optimisation

What we offer
- Mentorship from senior backend engineers, flexible hours, and a monthly stipend
""",
}


def load_demo(db_path: str, template: str = "classic") -> dict:
    """Replace the master profile with demo data and create sample artifacts."""
    profile = repo.save_profile(db_path, DEMO_PROFILE)
    analysis = parse_job_description(
        SAMPLE_JOB["description"],
        title=SAMPLE_JOB["title"],
        company=SAMPLE_JOB["company"],
        url=SAMPLE_JOB["url"],
    )
    stored_analysis = {key: value for key, value in analysis.items() if key != "description"}
    job_id = repo.save_job(
        db_path,
        SAMPLE_JOB["title"],
        SAMPLE_JOB["company"],
        SAMPLE_JOB["url"],
        SAMPLE_JOB["description"],
        stored_analysis,
    )
    result = score_match(profile, stored_analysis)
    repo.save_match(db_path, job_id, None, result["score"], result)
    resume_id = repo.create_resume_from_profile(
        db_path,
        profile,
        title="Aarav Sharma — Backend Intern Resume",
        template=template,
        job_id=job_id,
    )
    repo.set_setting(db_path, "demo_loaded", "1")
    return {
        "job_id": job_id,
        "resume_id": resume_id,
        "score": result["score"],
        "analysis": stored_analysis,
        "match": result,
        "profile": profile,
    }
