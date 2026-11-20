# Security, privacy and compliance

## Encryption and infrastructure

Traffic to Widget Cloud is encrypted with TLS 1.2 or newer; HTTP is redirected to
HTTPS. Data at rest is encrypted with AES-256. Backups are encrypted with the
same standard and retained for 35 days. Production access by Widget staff is
role-based, logged and requires multi-factor authentication.

Workspaces are hosted in the region selected at purchase (United States or
European Union). Data is not moved between regions except with the customer's
written approval. A current list of subprocessors is available from the support
desk and is updated before a new subprocessor starts processing customer data.

## Account and workspace security

- Members can enable multi-factor authentication; admins can require it for an
  Enterprise workspace.
- Enterprise workspaces can enforce SSO and restrict access by IP range.
- API tokens are scoped, shown once and revocable; leaked tokens should be
  revoked immediately.
- Audit history records sign-ins, member changes, permission changes, exports
  and integration configuration. Enterprise workspaces can export audit history
  for the retention period configured by the administrator.

## Data protection requests

Customers can request access, correction, export or deletion of personal data
through the privacy contact in the portal. Widget verifies the requester's
identity and authority over the workspace before acting.

- Export requests are fulfilled within 30 days.
- Deletion requests remove personal data from primary storage, with the same
  30-day workspace recovery window and seven-day erasure described in *Widget
  Cloud*. Backups expire on their normal 35-day schedule.
- Workspace admins can delete individual members and their content without
  contacting support; the action is recorded in audit history.

Enterprise customers with a data processing agreement follow the terms in that
agreement where it differs from this article.

## Backups and disaster recovery

Backups run daily. The recovery point objective is 24 hours and the recovery
time objective for a regional incident is four hours. Restores are tested
regularly; customers cannot request a restore of an individual workspace older
than the 30-day recovery window.

## Incident response

Confirmed security incidents affecting customer data are communicated to
affected workspace owners without undue delay and within 72 hours of
confirmation, with scope, remediation and follow-up details. The public status
page is used for service incidents; it never contains customer data. Security
researchers should report vulnerabilities privately through the channel listed
in the repository security policy, never through public issue trackers.

## Compliance documentation

Enterprise customers can request the current security questionnaire answers,
penetration-test summary and subprocessor list under NDA. Certifications and
reports available for the current release are listed on the trust page in the
portal; the support desk can confirm scope and expiry dates. Audit exports are
available only on the Enterprise plan.
