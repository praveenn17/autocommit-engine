# AutoCommit Generator

> A fully automated, AI-powered GitHub activity system with smart scheduling, mood awareness, and self-protection.

[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white)](https://github.com/praveenn17/autocommit-engine/actions)
[![Python 3.12](https://img.shields.io/badge/Python%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![React 18](https://img.shields.io/badge/React%2018-20232A?style=flat-square&logo=react&logoColor=61DAFB)](https://react.dev)
[![Vercel](https://img.shields.io/badge/Vercel-000000?style=flat-square&logo=vercel&logoColor=white)](https://autocommit-engine.vercel.app/)

## 📖 Overview

AutoCommit Generator is a highly advanced, fully automated GitHub activity system built for sustained, human-like activity. It transcends basic automation by mimicking genuine developer behavior through sophisticated 60-day learning models, time-zone precise activity plotting, and real context-aware AI commit messaging. 

Rather than committing random strings or basic templates, it reads real git diffs and employs the Gemini API to generate contextually accurate commit messages. It actively monitors Indian calendar data for festivals or exam seasons to adjust its behavior, ensuring that the generated activity graph mirrors the ebbs and flows of a real human being. 

With enterprise-level features like Exponential Backoff for network failures, an automated Interview Shield to hide the engine during recruitment processes, and an intuitive NLP-driven React dashboard to control it all, AutoCommit Generator stands as a masterclass in CI/CD automation, AI integration, and state management.

## 🏗 Architecture

The system utilizes a secure **Two-Repo Design** to separate the automation logic from the commit history:

- **[`autocommit-engine`](https://github.com/praveenn17/autocommit-engine)** (Public) — This repository. Contains all the core engine logic (Python scripts), GitHub Actions workflows, and the React Dashboard frontend.
- **`commit-archive`** (Private) — A separate, private repository that securely stores all state JSON files (history, streak stats, preferences) and actually receives the automated commits. This ensures your primary profile remains clean while registering the activity.

## ✨ Features

1. **AI Commit Messages** — The Gemini API analyzes real git diffs on the fly to generate highly accurate, contextual commit messages.
2. **Smart Pattern Learning** — Learns from a baseline of 300+ real human commits to dictate human-like commit distributions and frequencies.
3. **Hybrid Mood Model** — Integrates the Indian calendar and the Calendarific API to adjust commit intensity during festivals, exams, and holidays.
4. **VPN-Aware Scheduling** — Robust error handling with exponential backoff and retry logic for seamless network miss recovery.
5. **Interview Shield** — Automatically destroys and restores engine files and configurations during scheduled interviews to safely cloak automation.
6. **Natural Language Scheduler** — Type in plain English (e.g., "Set intensity to high next week"), and the AI instantly interprets and updates the system configuration.
7. **Smart Mode** — Employs a 60-day seed pattern. After day 60, Gemini takes over to infinitely extend and vary the pattern while maintaining organic consistency.

## 💻 Tech Stack

- **GitHub Actions** (7 heavily optimized scheduled jobs)
- **Python 3.12** (8 core automation and engine scripts)
- **React 18 + Vite + Tailwind CSS** (Dark-themed, dynamic dashboard)
- **Gemini API** (Context-aware commit messages, NL scheduler, pattern extension)
- **Calendarific API** (Indian festival and holiday detection)
- **Telegram Bot API** (Live notifications, streak warnings, and reports)
- **ReportLab** (Weekly PDF report generation)
- **GitHub Contents API** (Headless, repository-based state management)

## 📊 Dashboard

**Live Dashboard:** [autocommit-engine.vercel.app](https://autocommit-engine.vercel.app)

![Dashboard Preview](https://via.placeholder.com/1200x600/1e1e24/61DAFB?text=AutoCommit+Dashboard)

**Dashboard Features:**
- Live System Stats & Current Streak
- System Controls & Preferences
- Interview Shield Configuration
- NLP AI Scheduler
- Live Contribution Graph
- Historical Analytics

## ⚙️ Workflow Jobs

| Job Name | Cron Schedule (IST) | Description |
| --- | --- | --- |
| **AutoCommit Engine** | `30 1-18 * * *` (Hourly) | Main engine. Evaluates mood, generates AI commits from diffs, and executes commits via git. |
| **Weekly Telegram Report** | `30 3 * * 2` (Tue 9:00 AM) | Generates a comprehensive PDF summary of the week's commits and sends it via Telegram. |
| **Streak Warning** | `30 14 * * *` (Daily 8:00 PM) | Checks if a commit is missing for the day and sends an alert to preserve the streak. |
| **Learn Pattern** | `30 0 * * 1` (Mon 6:00 AM) | Analyzes recent history and refines the commit time distribution models. |
| **Monthly Exam Prompt** | `30 3 1 * *` (1st of Month) | Monthly check-in via Telegram to schedule upcoming study/exam days. |
| **Network Miss Follow-up** | `0 */8 * * *` (Every 8h) | Retries and sends pending follow-up Telegram notifications for VPN/Network misses. |
| **Interview Shield Check** | `30 0 * * *` (Daily 6:00 AM) | Triggers self-destruction or restoration of automation components based on interview schedules. |

## 🚀 Setup

1. **Fork Both Repos** — Fork `autocommit-engine` (public) and create a private repository named `commit-archive`.
2. **Add Required Secrets** — Add all 8 secrets/variables (listed below) to your `autocommit-engine` repository settings.
3. **Run Setup Wizard** — Trigger the Setup Wizard workflow via `workflow_dispatch` and provide your initial intensity preference.
4. **Deploy Dashboard** — Deploy the dashboard to Vercel by selecting the `dashboard/` root directory in your project settings.
5. **Add API Key to Dashboard** — Open the deployed dashboard, go to Settings, and add your Gemini API key to `localStorage` to unlock the NLP Scheduler.

## 🔑 Secrets & Variables Required

| Secret / Variable | Type | Description |
| --- | --- | --- |
| `ARCHIVE_REPO_PAT` | Secret | Personal Access Token with repo scope for the `commit-archive` repository. |
| `COMMIT_EMAIL` | Secret | The email address associated with your GitHub account. |
| `COMMIT_NAME` | Secret | Your display name for git commits. |
| `GEMINI_API_KEY` | Secret | Google AI Studio API key for commit generation and AI tasks. |
| `CALENDARIFIC_API_KEY` | Secret | API key for fetching Indian holidays and festivals. |
| `TELEGRAM_BOT_TOKEN` | Secret | Bot token from BotFather for notifications. |
| `TELEGRAM_CHAT_ID` | Secret | Your Telegram chat ID to receive the messages. |
| `GH_USERNAME` | Variable | Your GitHub username (e.g., `praveenn17`). |

## 📈 Project Stats

- **Workflow Runs:** 100+ automated executions
- **GitHub Actions:** 7 independent, orchestrating jobs
- **Python Scripts:** 8 distinct modular engines
- **React Components:** 10+ polished dashboard UI elements
- **Integrations:** 3 powerful external APIs synchronized

## 👨‍💻 Developer

**Praveen Kumar** ([@praveenn17](https://github.com/praveenn17))  
*3rd year CSE, RTU Kota*

## 📄 License

This project is licensed under the [MIT License](LICENSE).
