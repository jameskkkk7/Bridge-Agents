# Widget Cloud

## Overview

Widget Cloud is the hosted plan for shared Widget boards. It includes cloud
storage, team roles, audit history and webhooks. Widget Pro is the optional
desktop companion app; Widget Cloud works in a browser without installing
anything.

## Plans

- Starter: one workspace, three members, 30-day history.
- Standard: unlimited workspaces, 20 members per workspace, one year history.
- Enterprise: single sign-on, audit exports and a dedicated support channel.

Changing plans takes effect immediately. Downgrades keep existing data readable
but disable features that are not part of the new plan.

## Refunds and billing

Subscriptions are billed monthly or annually. Monthly subscriptions can be
cancelled at any time and stay active until the end of the billing period.
Annual subscriptions can be refunded within 30 days of purchase when fewer than
five active members have used the workspace. After that window a refund is not
guaranteed and is handled case by case.

## Data retention

Deleting a workspace starts a 30-day recovery window. After that the data is
erased from primary storage within seven days. Audit exports remain available
for the retention period configured by the administrator.

## Support

Standard plans receive email support during business hours. Enterprise plans
receive a named contact and a four-hour response target for production issues.
Security reports should be sent through the private reporting channel listed in
the repository security policy, never through public issue trackers.

## Troubleshooting

- Single sign-on redirects loop: check that the identity provider metadata URL
  is reachable from the workspace.
- Webhooks are not delivered: verify the endpoint accepts POST requests and
  returns a 2xx status within ten seconds.
- A former member still receives notifications: remove the member from the
  workspace and rotate any personal integration tokens they created.
