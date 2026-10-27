# Internship Software Development Project — Project Submission Document

**Project Name**: Email Deliverability Checker  
**Author / Intern**: Software Engineering Intern  
**Evaluation Track**: Senior Full-Stack Development Internship  
**Submission Date**: October 2026  
**Repository URL**: `https://github.com/PEPSS2007/mailchecker` *(fill in upon GitHub push)*  
**Live Deployment URL**: `https://mailchecker-steel.vercel.app` *(fill in upon Render deployment)*  

---

## 1. Executive Summary

Email Deliverability Checker is a production-grade web application and REST API designed to evaluate the deliverability status of email addresses without sending actual emails. It features an RFC-compliant, 6-stage verification pipeline encompassing syntax analysis, DNS MX resolution, RFC 7505 Null MX detection, disposable and role-account heuristic profiling, safe async SMTP probing, and synthetic catch-all detection.

The application incorporates dynamic environment sensing (Degraded Mode) to honestly handle cloud hosting restrictions where outbound TCP port 25 is blocked, preventing false positives while preserving transparent verification.

---

## 2. Technology Stack & Architecture

- **Backend**: Python 3.12, FastAPI, Uvicorn (ASGI)
- **Email Syntax Validation**: `email-validator` (RFC 5322)
- **DNS Resolution**: `dnspython` (RFC 5321 MX & A/AAAA fallback, RFC 7505 Null MX)
- **SMTP Networking**: `aiosmtplib` with strict command restrictions and per-domain semaphores
- **Rate Limiting & Caching**: `slowapi` (IP-based limits), `cachetools` (TTL in-memory caching)
- **Frontend**: Accessible, responsive HTML5, modern CSS3 (custom SaaS tokens), Vanilla JavaScript
- **Testing & Quality**: `pytest`, `pytest-asyncio`, `ruff` (linter and formatter)
- **DevOps & Containerization**: Multi-stage `Dockerfile`, GitHub Actions CI workflow, Render deployment

---

## 3. Verification Stages & Verdict Standard

| Stage | Focus | Standard Applied |
| :--- | :--- | :--- |
| **Stage A** | Parse & Normalize | Multi-delimiter parsing (newlines, commas, semicolons, whitespace), deduplication, max 100 limit. |
| **Stage B** | DNS & Mail Server | Resolves MX sorted by priority; flags RFC 7505 Null MX (`0 .`); checks A/AAAA fallback; detects SSRF targets. |
| **Stage C** | Heuristic Profiling | Cross-references 250+ disposable domains and role accounts (`admin@`, `support@`, etc.). |
| **Stage D** | Safe SMTP Probe | Restricted conversation (`EHLO` &rarr; `MAIL FROM` &rarr; `RCPT TO` &rarr; `QUIT`). Never issues `DATA`. |
| **Stage E** | Catch-All Detection | Probes synthetic randomized recipient to identify catch-all servers and avert false deliverables. |
| **Stage F** | Classification | Produces standardized verdicts (`deliverable`, `bounce`, `unknown`) with clear reason codes. |

---

## 4. Ethical, Privacy, and Security Safeguards

1. **Zero Message Transmission Guarantee**: Verified by automated unit tests ensuring the `DATA` command is structurally and programmatically prevented.
2. **Privacy Protection**: Submitted email lists are processed in volatile memory and never saved to databases or persistent storage.
3. **Safe Log Masking**: Local parts of email addresses are masked across all operational logs (`j***e@domain.com`).
4. **SSRF Mitigation**: Mail server hostnames resolving to private, loopback, or cloud link-local addresses (`169.254.169.254`) are intercepted before establishing TCP connections.
5. **Degraded Mode Transparency**: When deployed on cloud platforms where outbound port 25 is firewalled, the system switches to DNS-Only verification with visible UI alerts rather than simulating fake verification.

---

## 5. Verification & Test Suite Execution Results

All 32 test cases passed with 100% success rate:

```text
tests/test_api.py::test_api_health_endpoint PASSED
tests/test_api.py::test_api_health_endpoint_degraded PASSED
tests/test_api.py::test_api_check_valid_request PASSED
tests/test_api.py::test_api_check_exceeds_max_limit PASSED
tests/test_api.py::test_api_serve_index PASSED
tests/test_classify.py::test_verdict_assignments PASSED
tests/test_classify.py::test_heuristic_flags PASSED
tests/test_classify.py::test_explanations_populated PASSED
tests/test_dns_checks.py::test_is_ip_prohibited PASSED
tests/test_dns_checks.py::test_rfc7505_null_mx PASSED
tests/test_dns_checks.py::test_standard_mx_resolution PASSED
tests/test_dns_checks.py::test_rfc5321_fallback_a_record PASSED
tests/test_dns_checks.py::test_nxdomain_handling PASSED
tests/test_dns_checks.py::test_dns_timeout_handling PASSED
tests/test_dns_checks.py::test_dns_cache_operation PASSED
tests/test_pipeline.py::test_pipeline_max_100_limit PASSED
tests/test_pipeline.py::test_pipeline_empty_input PASSED
tests/test_pipeline.py::test_pipeline_end_to_end_mocked PASSED
tests/test_smtp_probe.py::test_safety_constraint_strictly_forbids_data PASSED
tests/test_smtp_probe.py::test_smtp_mailbox_accepted PASSED
tests/test_smtp_probe.py::test_smtp_mailbox_rejected PASSED
tests/test_smtp_probe.py::test_smtp_catch_all_detection PASSED
tests/test_smtp_probe.py::test_probe_catch_all_function PASSED
tests/test_smtp_probe.py::test_smtp_temporary_failure_retry PASSED
tests/test_smtp_probe.py::test_smtp_unavailable_degraded_mode PASSED
tests/test_smtp_probe.py::test_proves_no_data_command_or_message_is_sent PASSED
tests/test_syntax.py::test_parse_multi_delimiter_input PASSED
tests/test_syntax.py::test_parse_input_deduplication PASSED
tests/test_syntax.py::test_valid_syntax_normalization PASSED
tests/test_syntax.py::test_invalid_syntax_missing_at PASSED
tests/test_syntax.py::test_invalid_syntax_consecutive_dots PASSED
tests/test_syntax.py::test_safe_log_masking PASSED

======================== 32 passed in 1.55s ========================
```

---

## 6. Live Deployment Checklist & Instructions

1. **GitHub Repository Setup**:
   ```bash
   git init
   git add .
   git commit -m "feat: complete email deliverability checker application"
   git branch -M main
   git remote add origin <YOUR_GITHUB_REPO_URL>
   git push -u origin main
   ```
2. **Render Web Service Deployment**:
   - Create a new **Web Service** on Render connected to the repository.
   - Select **Docker** environment.
   - Render automatically builds and starts the container with dynamic port routing.
3. **Post-Deployment Verification**:
   - Visit the deployment URL and confirm the dashboard loads cleanly.
   - Query `/api/health` to inspect the reported `smtp_available` capability.
   - Paste sample emails to verify end-to-end delivery check results.
