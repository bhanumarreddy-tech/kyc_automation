export interface KYCQuestion {
  serialNo: number;
  sectionNo: number;
  sectionName: string;
  question: string;
}

export interface SourceLink {
  title: string;
  url: string;
}

export interface ValidationSource {
  document: string;
  excerpt?: string;
  page?: number;
}

export type ValidationStatus = "Yes" | "No" | "";

export interface KYCRow {
  sectionNo: number;
  sectionName: string;
  serialNo: number;
  question: string;
  answer: string;
  sources: SourceLink[];
  validation: ValidationStatus;
  validationSources: ValidationSource[];
  analystComments: string;
}

export const kycQuestions: KYCQuestion[] = [
  // Section 1 - Legal Identity
  { serialNo: 1, sectionNo: 1, sectionName: "Legal Identity", question: "What is the company's registration number (e.g., Company Registration Number, CRN, or equivalent)?" },
  { serialNo: 2, sectionNo: 1, sectionName: "Legal Identity", question: "What is the date of incorporation or registration?" },
  { serialNo: 3, sectionNo: 1, sectionName: "Legal Identity", question: "What is the company's registered address?" },
  { serialNo: 4, sectionNo: 1, sectionName: "Legal Identity", question: "Does the company have any other operating or trading addresses?" },
  { serialNo: 5, sectionNo: 1, sectionName: "Legal Identity", question: "What is the company's tax identification number (TIN), VAT/GST number, or equivalent?" },
  { serialNo: 6, sectionNo: 1, sectionName: "Legal Identity", question: "Is the company a subsidiary, parent company, or part of a larger corporate group? If so, provide details of the group structure." },
  { serialNo: 7, sectionNo: 1, sectionName: "Legal Identity", question: "What is the company's legal entity type (e.g., LLC, corporation, partnership, trust)?" },
  { serialNo: 8, sectionNo: 1, sectionName: "Legal Identity", question: "Does the company operate under any trade names or aliases (Doing Business As, DBA)?" },
  { serialNo: 9, sectionNo: 1, sectionName: "Legal Identity", question: "Is the company publicly listed? If yes, on which stock exchange and what is the ticker symbol?" },

  // Section 2 - Ownership & Ultimate Beneficial Owner
  { serialNo: 10, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Who are the ultimate beneficial owners (UBOs) of the company (individuals owning 25% or more of the shares or voting rights, or those with significant control)? For each UBO, provide:" },
  { serialNo: 11, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Full name" },
  { serialNo: 12, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Date of birth" },
  { serialNo: 13, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Nationality" },
  { serialNo: 14, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Residential address" },
  { serialNo: 15, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Government-issued ID number (e.g., passport or national ID)" },
  { serialNo: 16, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Percentage of ownership or control" },
  { serialNo: 17, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Who are the key personnel or authorized signatories (e.g., directors, officers, or legal representatives)?" },
  { serialNo: 18, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Provide their full names, roles, dates of birth, nationalities, and ID details." },
  { serialNo: 19, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Is there a complex ownership structure involving trusts, nominees, or other entities? If so, provide detailed documentation." },
  { serialNo: 20, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Are there any shareholders or beneficial owners who are Politically Exposed Persons (PEPs) or their close associates?" },
  { serialNo: 21, sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner", question: "Has the ownership structure changed recently? If yes, provide details." },

  // Section 3 - Business Activities
  { serialNo: 22, sectionNo: 3, sectionName: "Business Activities", question: "What is the primary nature of the company's business (e.g., manufacturing, trading, services, fintech)?" },
  { serialNo: 23, sectionNo: 3, sectionName: "Business Activities", question: "What are the company's main products or services?" },
  { serialNo: 24, sectionNo: 3, sectionName: "Business Activities", question: "In which countries or jurisdictions does the company operate?" },
  { serialNo: 25, sectionNo: 3, sectionName: "Business Activities", question: "Who are the company's primary customers or clients (e.g., individuals, businesses, government entities)?" },
  { serialNo: 26, sectionNo: 3, sectionName: "Business Activities", question: "Who are the company's primary suppliers or business partners?" },
  { serialNo: 27, sectionNo: 3, sectionName: "Business Activities", question: "What is the expected annual revenue or turnover of the company?" },
  { serialNo: 28, sectionNo: 3, sectionName: "Business Activities", question: "What is the company's estimated net worth or asset value?" },
  { serialNo: 29, sectionNo: 3, sectionName: "Business Activities", question: "Does the company engage in high-risk activities (e.g., cash-intensive businesses, cryptocurrency, gambling, arms trading)?" },
  { serialNo: 30, sectionNo: 3, sectionName: "Business Activities", question: "Does the company operate in high-risk jurisdictions (e.g., countries with weak AML/CTF regulations or on sanctions lists)?" },
  { serialNo: 31, sectionNo: 3, sectionName: "Business Activities", question: "Are there any licenses or regulatory approvals required for the company's operations? If yes, provide details and copies." },

  // Section 4 - Financial & Banking
  { serialNo: 32, sectionNo: 4, sectionName: "Financial & Banking", question: "What types of transactions are expected (e.g., domestic/international wire transfers, payroll, trade finance)?" },
  { serialNo: 33, sectionNo: 4, sectionName: "Financial & Banking", question: "What is the anticipated volume and frequency of transactions?" },
  { serialNo: 34, sectionNo: 4, sectionName: "Financial & Banking", question: "What is the expected average transaction size?" },
  { serialNo: 35, sectionNo: 4, sectionName: "Financial & Banking", question: "What are the primary sources of funds for the company (e.g., sales revenue, investments, loans)?" },
  { serialNo: 36, sectionNo: 4, sectionName: "Financial & Banking", question: "Provide details of the company's existing banking relationships (e.g., other bank accounts, financial institutions used)." },
  { serialNo: 37, sectionNo: 4, sectionName: "Financial & Banking", question: "Are there any loans, credit facilities, or significant debts? If yes, provide details." },
  { serialNo: 38, sectionNo: 4, sectionName: "Financial & Banking", question: "Can the company provide recent financial statements (e.g., balance sheet, profit and loss statement, audited accounts)?" },
  { serialNo: 39, sectionNo: 4, sectionName: "Financial & Banking", question: "Are there any unusual or complex funding structures (e.g., offshore accounts, venture capital, private equity)?" },

  // Section 5 - Risk & Compliance
  { serialNo: 40, sectionNo: 5, sectionName: "Risk & Compliance", question: "Has the company or any of its UBOs, directors, or key personnel been involved in legal or regulatory actions (e.g., fines, sanctions, investigations)?" },
  { serialNo: 41, sectionNo: 5, sectionName: "Risk & Compliance", question: "Is the company, its UBOs, or key personnel listed on any sanctions lists (e.g., OFAC, UN, EU sanctions)?" },
  { serialNo: 42, sectionNo: 5, sectionName: "Risk & Compliance", question: "Has the company been subject to adverse media reports related to financial crimes, fraud, or unethical practices?" },
  { serialNo: 43, sectionNo: 5, sectionName: "Risk & Compliance", question: "Does the company have an AML/CTF compliance program in place? If yes, provide details." },
  { serialNo: 44, sectionNo: 5, sectionName: "Risk & Compliance", question: "Has the company conducted business with entities or individuals in sanctioned countries?" },
  { serialNo: 45, sectionNo: 5, sectionName: "Risk & Compliance", question: "Are there any connections to high-risk industries (e.g., money services businesses, precious metals, real estate)?" },
  { serialNo: 46, sectionNo: 5, sectionName: "Risk & Compliance", question: "Does the company deal with virtual assets or cryptocurrencies? If yes, provide details of compliance measures." },
  { serialNo: 47, sectionNo: 5, sectionName: "Risk & Compliance", question: "Has the company undergone a KYC/KYB process with other financial institutions? If yes, can supporting documentation be shared?" },

  // Section 6 - Source of Funds
  { serialNo: 48, sectionNo: 6, sectionName: "Source of Funds", question: "What is the source of funds for the account opening (e.g., operational revenue, capital injection, loans)?" },
  { serialNo: 49, sectionNo: 6, sectionName: "Source of Funds", question: "Can the company provide evidence of the source of funds (e.g., contracts, invoices, bank statements)?" },
  { serialNo: 50, sectionNo: 6, sectionName: "Source of Funds", question: "What is the source of wealth for the UBOs (e.g., inheritance, business profits, investments)?" },
  { serialNo: 51, sectionNo: 6, sectionName: "Source of Funds", question: "Are there any third-party funds involved in the account (e.g., investors, partners)? If yes, provide details." },
  { serialNo: 52, sectionNo: 6, sectionName: "Source of Funds", question: "Can the company provide documentation to verify the legitimacy of funds (e.g., tax returns, audited accounts)?" },

  // Section 7 - EDD (Enhanced Due Diligence)
  { serialNo: 53, sectionNo: 7, sectionName: "EDD", question: "If the company is flagged as high-risk (e.g., due to jurisdiction, industry, or PEP status), provide additional details." },
  { serialNo: 54, sectionNo: 7, sectionName: "EDD", question: "Detailed explanation of business activities and relationships." },
  { serialNo: 55, sectionNo: 7, sectionName: "EDD", question: "Evidence of compliance with local and international regulations." },
  { serialNo: 56, sectionNo: 7, sectionName: "EDD", question: "Additional documentation for UBOs and key personnel (e.g., source of wealth, references)." },
  { serialNo: 57, sectionNo: 7, sectionName: "EDD", question: "Have site visits or interviews been conducted to verify the company's operations? If not, is the company open to such measures?" },
  { serialNo: 58, sectionNo: 7, sectionName: "EDD", question: "Are there any red flags identified during initial screening (e.g., inconsistencies in documents, lack of transparency)?" },
  { serialNo: 59, sectionNo: 7, sectionName: "EDD", question: "Can the company provide references from other financial institutions or business partners?" },

  // Section 8 - Declarations
  { serialNo: 60, sectionNo: 8, sectionName: "Declarations", question: "Does the company agree to provide updated information if there are changes in ownership, business activities, or key personnel?" },
  { serialNo: 61, sectionNo: 8, sectionName: "Declarations", question: "Is the company willing to consent to ongoing transaction monitoring?" },
  { serialNo: 62, sectionNo: 8, sectionName: "Declarations", question: "Can the company confirm that it will report any suspicious activities as required by law?" },
  { serialNo: 63, sectionNo: 8, sectionName: "Declarations", question: "Does the company agree to comply with all applicable AML/CTF regulations?" },
  { serialNo: 64, sectionNo: 8, sectionName: "Declarations", question: "Has the company or its representatives provided a signed declaration confirming the accuracy of the information provided?" },
];

export const SECTIONS: { sectionNo: number; sectionName: string }[] = [
  { sectionNo: 1, sectionName: "Legal Identity" },
  { sectionNo: 2, sectionName: "Ownership & Ultimate Beneficial Owner" },
  { sectionNo: 3, sectionName: "Business Activities" },
  { sectionNo: 4, sectionName: "Financial & Banking" },
  { sectionNo: 5, sectionName: "Risk & Compliance" },
  { sectionNo: 6, sectionName: "Source of Funds" },
  { sectionNo: 7, sectionName: "EDD" },
  { sectionNo: 8, sectionName: "Declarations" },
];
