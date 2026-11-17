# One-time setup (for you, the maintainer)

Do these once. Users never see any of this.

## 1. Create the database tables (2 minutes)

1. Open your Supabase project → **SQL Editor** → **New query**.
2. Open `supabase/schema.sql` from this repo, copy everything, paste it in, click **Run**.
   You should see "Success. No rows returned".

## 2. Allow Trail's sign-in to come back to the app

Supabase → **Authentication** → **URL Configuration**:

- **Site URL:** `https://ziggiphase.github.io/trail/`
- **Redirect URLs** → **Add URL:** `http://127.0.0.1:47261/callback` → Save

## 3. Turn on GitHub Pages (the website)

GitHub repo → **Settings** → **Pages** → *Build and deployment* → **Source: GitHub Actions**.
After your next push the site is live at https://ziggiphase.github.io/trail/

## 4. Google sign-in (recommended, about 10 minutes)

1. Go to https://console.cloud.google.com → create a project called **Trail**.
2. **Google Auth Platform** (APIs & Services → OAuth consent screen) → **Get started**:
   - App name **Trail**, your support email → **Audience: External** → finish.
   - **Branding:** home page `https://ziggiphase.github.io/trail/`,
     privacy policy `https://ziggiphase.github.io/trail/privacy.html`.
   - **Audience** → **Publish app** (otherwise only test users can sign in).
3. **Clients** → **Create client** → type **Web application** →
   **Authorized redirect URIs:** `https://eddyusnixdaaafqpleui.supabase.co/auth/v1/callback` → Create.
4. Copy the **Client ID** and **Client secret**.
5. Supabase → **Authentication** → **Sign In / Providers** → **Google** → enable, paste both → **Save**.

## 5. Email sign-in for everyone (needs a free email-sending account)

Supabase's built-in email only reaches members of your Supabase team (2 emails an hour).
To let anyone sign in with email, connect a free sending service. Brevo works without owning a domain:

1. Sign up at brevo.com → **Senders, domains & IPs** → add and verify your sender email.
2. Brevo → **SMTP & API** → **SMTP** tab: note the server, port, login and create an **SMTP key**.
3. Supabase → **Authentication** → **Emails** → **SMTP Settings** → enable custom SMTP:
   host `smtp-relay.brevo.com`, port `587`, username = your Brevo SMTP login,
   password = the SMTP key, sender email = the verified address, sender name `Trail` → Save.
4. Optional, lets people type a 6-digit code instead of clicking the link:
   **Emails → Templates** → in both **Magic link** and **Confirm signup**, add a line such as
   `<p>Or enter this code in Trail: <b>{{ .Token }}</b></p>` → Save.

Until this is done, use Google sign-in (or your own team email) for testing.

## 6. Publish a release

1. Commit and push your changes (VS Code → Source Control → Commit → Sync Changes).
2. GitHub repo → **Releases** → **Draft a new release** → **Choose a tag** → type `v1.1.0` →
   *Create new tag* → title `Trail 1.1.0` → write what changed → **Publish release**.
3. Wait about 6 minutes (watch the **Actions** tab). `Trail-Setup.exe` gets attached to the release.

From then on:
- The website's **Download** button gives that version.
- Installed copies of Trail (1.1.0 and newer) see an **Update** button and update themselves.
- For the next version, just publish a release with a higher tag (`v1.1.1`, `v1.2.0`, …).
  You don't need to edit any version numbers in the code.

Version 1.0.0 (the one already on your PC) has no updater, so install 1.1.0 by hand once:
download it from the website and run it. It replaces 1.0.0 and keeps your settings.
