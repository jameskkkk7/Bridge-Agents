# Troubleshooting sign-in and SSO

## Password sign-in

- **Forgotten password:** use **Forgot password** on the sign-in page. The reset
  link is valid for 60 minutes and single use.
- **Reset email never arrives:** check spam, confirm the address spelling and ask
  a workspace admin to verify the account exists. Do not create a second account
  with the same address; it will not join the original workspace.
- **Account locked after failed attempts:** wait 15 minutes, then try again. A
  workspace admin can unlock the member immediately from **Members**.
- **Session expires early:** sessions last up to 12 hours; sensitive actions may
  require re-authentication. Corporate browsers that clear storage on exit will
  require a fresh sign-in each time.

## Single sign-on loops

An SSO redirect loop usually means the identity provider and the workspace
disagree about the assertion.

1. Verify the identity provider metadata URL is reachable from the workspace.
2. Confirm the ACS/redirect URL shown in **Security → SSO** matches the identity
   provider configuration exactly (scheme, host and path).
3. Check the identity provider clock; SAML assertions with timestamps more than
   five minutes in the past or future are rejected.
4. If SSO was just enforced, sign in with the password-authenticated owner
   account, disable enforcement, reproduce the error, then re-enable it after
   fixing the provider configuration.

Common error codes:

- `invalid_signature` — the provider certificate rotated; upload the new
  certificate.
- `audience_mismatch` — the entity ID configured in the provider does not match
  the workspace.
- `user_not_provisioned` — just-in-time provisioning is disabled and the user
  does not exist; create the member or enable JIT provisioning.

## Multi-factor authentication

Members can enable MFA from **Profile → Security**. Admins can require MFA for
the workspace. If a member loses an authenticator device, an admin can reset MFA
after verifying the member's identity through the account recovery process.
Support cannot reset MFA without workspace admin approval.

## Email changes and duplicate accounts

Changing the sign-in email requires confirmation from both addresses. If a
customer signed up twice with different addresses, support can merge accounts
only when both addresses are verified and the workspace owner approves; the
older account's content is moved into the workspace and the duplicate is closed.

## Enterprise account recovery

If the only owner loses access and SSO is unavailable, support starts the
account recovery process: verify domain ownership, confirm billing identity and
designate a new owner. Recovery does not bypass MFA; it creates a new verified
owner account and records the action in the workspace audit history.
