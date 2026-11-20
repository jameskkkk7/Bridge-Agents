# Billing and invoices

## Payment methods

Widget Cloud accepts major credit and debit cards. Enterprise contracts may be
paid by bank transfer or purchase order when agreed in the order form. The card
on file is charged automatically at the start of each billing period.

Only workspace owners and admins can view or change payment details. Card
numbers are handled by the payment processor and are never stored on Widget
servers.

## Billing periods

Subscriptions are billed monthly or annually. The billing period starts on the
purchase date. Annual subscriptions renew on the same date each year unless
cancelled before the renewal date.

Upgrades take effect immediately and the price difference is prorated for the
remaining period. Downgrades take effect immediately as well: features outside
the new plan are disabled, existing data stays readable, and unused prepaid time
is not automatically refunded. See *Refunds and cancellations* for the annual
refund window.

## Invoices and tax

Invoices are available under **Billing → Invoices** as PDF downloads. Add a
company name, billing address and tax identifier before the next invoice is
issued; historical invoices are not reissued automatically, but support can
correct a recent invoice when the tax identifier was missing.

Enterprise customers can request consolidated invoices for multiple workspaces.
Purchase order numbers must be provided at contract signature; they appear on
every invoice for the contract.

## Failed payments

If a renewal charge fails, the payment processor retries on days 1, 3 and 5.
The workspace remains fully usable during a seven-day grace period. After the
grace period the workspace becomes read-only until payment succeeds; data is not
deleted. Update the payment method under **Billing → Payment method**, then use
**Retry payment**.

## Changing plans

Plan changes can be made by an owner at any time. A downgrade that would leave
more members than the target plan allows is blocked until the workspace reduces
its member count. Downgrading from Enterprise disables SSO enforcement and audit
exports at the end of the current billing period, not immediately, so members
keep access while the contract winds down.

## Billing questions and disputes

For invoice corrections, duplicate charges or unrecognised payments, contact
support with the workspace identifier and invoice number. Chargeback
investigations are handled through the payment processor; access may be
suspended while a dispute is open, and restored when it is resolved.

## Refunds

Refunds follow the plan-specific rules in *Refunds and cancellations*. Billing
support can confirm eligibility but cannot override the published policy;
exceptional cases are reviewed individually by the support lead.
