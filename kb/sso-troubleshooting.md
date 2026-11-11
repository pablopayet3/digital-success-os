# SSO connection test fails or users are locked out

If the SSO connection test fails with a certificate error, the signing certificate in the metadata file has expired or does not match. Download a fresh metadata file from your identity provider and upload it again under Admin settings, Security, Single sign-on.

If users are locked out after you enabled SSO, their email address in Relay probably differs from the one in the identity provider. Email addresses must match exactly. An admin who still has password sign-in can turn SSO off under Admin settings, Security, fix the addresses under Admin settings, Users, and turn SSO on again.

If nobody can sign in at all, contact support: an agent cannot change security settings for you.

---
Relay help centre. Fictional product documentation for a demo (synthetic data).
