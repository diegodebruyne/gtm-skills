# Lemlist native fields

Rule: never invent a property that already exists natively, and write keys EXACTLY as below (case included). Read the live list with the Lemlist MCP tool `get_contact_fields_schema` (or the API) before deciding a field is custom; a field is native when it appears in that schema, never by assumption.

## Contact (lead)
email, firstName, lastName, jobTitle, phone, linkedinUrl, linkedinUrlSalesNav, picture, jobDescription, timezone, industry, languages, location, skills, summary, tagline, ownerId.
Read-only: status, createdAt.

## Company carried by the lead (prefix `company`)
companyName, companyDomain, companyLinkedinUrl, companyLinkedinUrlSalesNav, companyPicture, companyIndustry, companySubIndustry, companyLocation, companyHeadquarters, companySize, companyEmployeeCount, companyEmployeeGrowth, companyRevenue, companyType, companyDescription, companyTagline, companySpecialties, companyFoundedOn, companyTechnologies, companyOwnerId.

## Company object (company import, keys without prefix)
name, domain, linkedinUrl, linkedinUrlSalesNav, picture, industry, subIndustry, location, headquarters, size, employeeCount, employeeGrowth, revenue, type, description, tagline, specialties, foundedOn, technologies, ownerId.

## Keys to stop using (duplicates of native fields)
- `CompanyLinkedinUrl` (capital C): use `companyLinkedinUrl`.
- `leadLocation`: use `location`.

## Not native
- **`country` and `companyPhone` are NOT native Lemlist fields.** The only native phone is `phone`, the CONTACT's. The country is read from `companyLocation` and `companyHeadquarters`. `companyPhone` can be sent as a custom lead variable; `country` duplicates `companyLocation` and should not be sent.
- Typical custom variables: personaTier, emailType, gender, salutation, colleaguename1, colleaguename2, source, importBatch.
- A variable specific to one campaign (for example an event role) does not belong in a fixed list. The only control is that no native field covers it, and that this is justified in the report (check L11).

## Where to put what
- actor type (hotel, hotel group, consultant...) -> `companyType`. Never guess a value: without evidence the field stays empty and the row is flagged.
- description from the website or profile -> `companyDescription`
- company place and size -> `companyLocation`, `companySize` (and `companyEmployeeCount`)
- industry -> `companyIndustry`
- person's place -> `location`; languages -> `languages`; summary -> `summary`; headline -> `tagline`

## Lemlist normalizes some values on import
The read-back must compare normalized values, otherwise it reports false gaps: country subdomains of linkedin.com become `www`; a trailing language suffix (`/en`, `/fr`...) is removed from LinkedIn links; a sub-domain is cut back to the registered domain; a phone number starting with `+` gets a leading apostrophe in the CSV export (not through the API); emoji and the symbols (R) (TM) (C) are removed from text fields. `scripts/import_leads.py` (`_norm_value`) applies the same normalization to both sides.
