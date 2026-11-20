# Accounts and workspaces

## Creating an account

Sign up at the Widget Cloud portal with a work email address. A verification
email is sent immediately; the link stays valid for 24 hours. Until the address
is verified the account can sign in, but it cannot invite members or start a
paid subscription.

Personal email domains are accepted for the Starter plan. Enterprise purchases
require a company domain unless the contract states otherwise.

## Workspaces

A workspace is the container for boards, members, integrations and billing.
Starter includes one workspace, Standard includes unlimited workspaces and
Enterprise workspaces are provisioned per contract.

To create a workspace, open the workspace switcher and choose **Create
workspace**. The creator becomes the workspace owner. Workspace names are not
unique; the workspace URL identifier is.

## Members and roles

- **Owner** — exactly one per workspace; manages billing, ownership transfer and
  workspace deletion.
- **Admin** — manages members, integrations, security settings and content.
- **Editor** — creates and edits boards.
- **Viewer** — read-only access, including comments.

An invitation expires after seven days and can be resent from **Members**.
Members can be removed at any time; their content stays in the workspace and
remains attributed to their name.

To transfer ownership, the current owner selects **Transfer ownership** and the
target member confirms by email. Both parties must confirm; support cannot
transfer ownership on a customer's behalf unless the account recovery process
has been completed.

## Single sign-on

Enterprise workspaces can connect a SAML or OIDC identity provider. Enter the
provider metadata URL, choose whether to require SSO for all members, and save.
Members are provisioned just in time on their first SSO sign-in; automated user
provisioning protocols such as SCIM are not part of the current release. Keep at
least one password-authenticated owner account until SSO is verified, otherwise
a provider outage can lock the workspace out.

## Closing an account

Deleting a workspace requires owner confirmation and the workspace name. A
30-day recovery window follows; during that window support can restore the
workspace. After the window, data is erased from primary storage within seven
days, backups expire on their normal schedule, and the workspace URL is released.
Deleting an account does not automatically delete workspaces the account only
participates in. See *Widget Cloud* for the full retention policy.

## Email and profile changes

Members can change their display name and password in **Profile**. Changing the
sign-in email sends a confirmation to both the old and new address. Workspace
display names are independent of account names, so the support desk may address
a customer by either value depending on where the profile was updated.
