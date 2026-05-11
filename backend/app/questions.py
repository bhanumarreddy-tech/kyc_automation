"""Canonical KYC questionnaire used across the backend.

The structure mirrors `src/data/kycQuestions.ts` on the frontend. The serial
numbers are globally unique (1..64) and the section numbers (1..8) group the
questions for per-section LLM processing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KYCQuestion:
    serial_no: int
    section_no: int
    section_name: str
    question: str


KYC_QUESTIONS: list[KYCQuestion] = [
    # Section 1 - Legal Identity
    KYCQuestion(1, 1, "Legal Identity", "What is the company's registration number (e.g., Company Registration Number, CRN, or equivalent)?"),
    KYCQuestion(2, 1, "Legal Identity", "What is the date of incorporation or registration?"),
    KYCQuestion(3, 1, "Legal Identity", "What is the company's registered address?"),
    KYCQuestion(4, 1, "Legal Identity", "Does the company have any other operating or trading addresses?"),
    KYCQuestion(5, 1, "Legal Identity", "What is the company's tax identification number (TIN), VAT/GST number, or equivalent?"),
    KYCQuestion(6, 1, "Legal Identity", "Is the company a subsidiary, parent company, or part of a larger corporate group? If so, provide details of the group structure."),
    KYCQuestion(7, 1, "Legal Identity", "What is the company's legal entity type (e.g., LLC, corporation, partnership, trust)?"),
    KYCQuestion(8, 1, "Legal Identity", "Does the company operate under any trade names or aliases (Doing Business As, DBA)?"),
    KYCQuestion(9, 1, "Legal Identity", "Is the company publicly listed? If yes, on which stock exchange and what is the ticker symbol?"),

    # Section 2 - Ownership & Ultimate Beneficial Owner
    KYCQuestion(10, 2, "Ownership & Ultimate Beneficial Owner", "Who are the ultimate beneficial owners (UBOs) of the company (individuals owning 25% or more of the shares or voting rights, or those with significant control)? For each UBO, provide:"),
    KYCQuestion(11, 2, "Ownership & Ultimate Beneficial Owner", "Full name"),
    KYCQuestion(12, 2, "Ownership & Ultimate Beneficial Owner", "Date of birth"),
    KYCQuestion(13, 2, "Ownership & Ultimate Beneficial Owner", "Nationality"),
    KYCQuestion(14, 2, "Ownership & Ultimate Beneficial Owner", "Residential address"),
    KYCQuestion(15, 2, "Ownership & Ultimate Beneficial Owner", "Government-issued ID number (e.g., passport or national ID)"),
    KYCQuestion(16, 2, "Ownership & Ultimate Beneficial Owner", "Percentage of ownership or control"),
    KYCQuestion(17, 2, "Ownership & Ultimate Beneficial Owner", "Who are the key personnel or authorized signatories (e.g., directors, officers, or legal representatives)?"),
    KYCQuestion(18, 2, "Ownership & Ultimate Beneficial Owner", "Provide their full names, roles, dates of birth, nationalities, and ID details."),
    KYCQuestion(19, 2, "Ownership & Ultimate Beneficial Owner", "Is there a complex ownership structure involving trusts, nominees, or other entities? If so, provide detailed documentation."),
    KYCQuestion(20, 2, "Ownership & Ultimate Beneficial Owner", "Are there any shareholders or beneficial owners who are Politically Exposed Persons (PEPs) or their close associates?"),
    KYCQuestion(21, 2, "Ownership & Ultimate Beneficial Owner", "Has the ownership structure changed recently? If yes, provide details."),

    # Section 3 - Business Activities
    KYCQuestion(22, 3, "Business Activities", "What is the primary nature of the company's business (e.g., manufacturing, trading, services, fintech)?"),
    KYCQuestion(23, 3, "Business Activities", "What are the company's main products or services?"),
    KYCQuestion(24, 3, "Business Activities", "In which countries or jurisdictions does the company operate?"),
    KYCQuestion(25, 3, "Business Activities", "Who are the company's primary customers or clients (e.g., individuals, businesses, government entities)?"),
    KYCQuestion(26, 3, "Business Activities", "Who are the company's primary suppliers or business partners?"),
    KYCQuestion(27, 3, "Business Activities", "What is the expected annual revenue or turnover of the company?"),
    KYCQuestion(28, 3, "Business Activities", "What is the company's estimated net worth or asset value?"),
    KYCQuestion(29, 3, "Business Activities", "Does the company engage in high-risk activities (e.g., cash-intensive businesses, cryptocurrency, gambling, arms trading)?"),
    KYCQuestion(30, 3, "Business Activities", "Does the company operate in high-risk jurisdictions (e.g., countries with weak AML/CTF regulations or on sanctions lists)?"),
    KYCQuestion(31, 3, "Business Activities", "Are there any licenses or regulatory approvals required for the company's operations? If yes, provide details and copies."),

    # Section 4 - Financial & Banking
    KYCQuestion(32, 4, "Financial & Banking", "What types of transactions are expected (e.g., domestic/international wire transfers, payroll, trade finance)?"),
    KYCQuestion(33, 4, "Financial & Banking", "What is the anticipated volume and frequency of transactions?"),
    KYCQuestion(34, 4, "Financial & Banking", "What is the expected average transaction size?"),
    KYCQuestion(35, 4, "Financial & Banking", "What are the primary sources of funds for the company (e.g., sales revenue, investments, loans)?"),
    KYCQuestion(36, 4, "Financial & Banking", "Provide details of the company's existing banking relationships (e.g., other bank accounts, financial institutions used)."),
    KYCQuestion(37, 4, "Financial & Banking", "Are there any loans, credit facilities, or significant debts? If yes, provide details."),
    KYCQuestion(38, 4, "Financial & Banking", "Can the company provide recent financial statements (e.g., balance sheet, profit and loss statement, audited accounts)?"),
    KYCQuestion(39, 4, "Financial & Banking", "Are there any unusual or complex funding structures (e.g., offshore accounts, venture capital, private equity)?"),

    # Section 5 - Risk & Compliance
    KYCQuestion(40, 5, "Risk & Compliance", "Has the company or any of its UBOs, directors, or key personnel been involved in legal or regulatory actions (e.g., fines, sanctions, investigations)?"),
    KYCQuestion(41, 5, "Risk & Compliance", "Is the company, its UBOs, or key personnel listed on any sanctions lists (e.g., OFAC, UN, EU sanctions)?"),
    KYCQuestion(42, 5, "Risk & Compliance", "Has the company been subject to adverse media reports related to financial crimes, fraud, or unethical practices?"),
    KYCQuestion(43, 5, "Risk & Compliance", "Does the company have an AML/CTF compliance program in place? If yes, provide details."),
    KYCQuestion(44, 5, "Risk & Compliance", "Has the company conducted business with entities or individuals in sanctioned countries?"),
    KYCQuestion(45, 5, "Risk & Compliance", "Are there any connections to high-risk industries (e.g., money services businesses, precious metals, real estate)?"),
    KYCQuestion(46, 5, "Risk & Compliance", "Does the company deal with virtual assets or cryptocurrencies? If yes, provide details of compliance measures."),
    KYCQuestion(47, 5, "Risk & Compliance", "Has the company undergone a KYC/KYB process with other financial institutions? If yes, can supporting documentation be shared?"),

    # Section 6 - Source of Funds
    KYCQuestion(48, 6, "Source of Funds", "What is the source of funds for the account opening (e.g., operational revenue, capital injection, loans)?"),
    KYCQuestion(49, 6, "Source of Funds", "Can the company provide evidence of the source of funds (e.g., contracts, invoices, bank statements)?"),
    KYCQuestion(50, 6, "Source of Funds", "What is the source of wealth for the UBOs (e.g., inheritance, business profits, investments)?"),
    KYCQuestion(51, 6, "Source of Funds", "Are there any third-party funds involved in the account (e.g., investors, partners)? If yes, provide details."),
    KYCQuestion(52, 6, "Source of Funds", "Can the company provide documentation to verify the legitimacy of funds (e.g., tax returns, audited accounts)?"),

    # Section 7 - EDD
    KYCQuestion(53, 7, "EDD", "If the company is flagged as high-risk (e.g., due to jurisdiction, industry, or PEP status), provide additional details."),
    KYCQuestion(54, 7, "EDD", "Detailed explanation of business activities and relationships."),
    KYCQuestion(55, 7, "EDD", "Evidence of compliance with local and international regulations."),
    KYCQuestion(56, 7, "EDD", "Additional documentation for UBOs and key personnel (e.g., source of wealth, references)."),
    KYCQuestion(57, 7, "EDD", "Have site visits or interviews been conducted to verify the company's operations? If not, is the company open to such measures?"),
    KYCQuestion(58, 7, "EDD", "Are there any red flags identified during initial screening (e.g., inconsistencies in documents, lack of transparency)?"),
    KYCQuestion(59, 7, "EDD", "Can the company provide references from other financial institutions or business partners?"),

    # Section 8 - Declarations
    KYCQuestion(60, 8, "Declarations", "Does the company agree to provide updated information if there are changes in ownership, business activities, or key personnel?"),
    KYCQuestion(61, 8, "Declarations", "Is the company willing to consent to ongoing transaction monitoring?"),
    KYCQuestion(62, 8, "Declarations", "Can the company confirm that it will report any suspicious activities as required by law?"),
    KYCQuestion(63, 8, "Declarations", "Does the company agree to comply with all applicable AML/CTF regulations?"),
    KYCQuestion(64, 8, "Declarations", "Has the company or its representatives provided a signed declaration confirming the accuracy of the information provided?"),
]


def group_by_section() -> list[tuple[int, str, list[KYCQuestion]]]:
    """Return questions grouped as ``(section_no, section_name, questions)``."""
    groups: dict[int, list[KYCQuestion]] = {}
    names: dict[int, str] = {}
    for q in KYC_QUESTIONS:
        groups.setdefault(q.section_no, []).append(q)
        names[q.section_no] = q.section_name
    return [
        (section_no, names[section_no], groups[section_no])
        for section_no in sorted(groups.keys())
    ]
