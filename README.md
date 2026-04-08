# DoorCodes Public Site Repo Template

Use this template in a separate public GitHub repository so the DoorCodes app code can stay private.

## Recommended repository

- Repository name: `doorcodes-site`
- GitHub Pages temporary URLs:
  - `https://ninjatomonline.github.io/doorcodes-site/`
  - `https://ninjatomonline.github.io/doorcodes-site/support.html`
  - `https://ninjatomonline.github.io/doorcodes-site/privacy.html`

## Contents this repo should contain

- `index.html`
- `support.html`
- `privacy.html`
- `site.css`
- `.nojekyll`
- `.github/workflows/publish-pages.yml`

## Setup

1. Create a new public GitHub repository named `doorcodes-site`.
2. Copy the exported DoorCodes site files into that repo root.
3. In the new repo, go to `Settings > Pages`.
4. Set `Source` to `GitHub Actions`.
5. Push to `main` and let the workflow deploy the site.

## Later custom-domain swap

Once `doorcodesapp.com` is ready:

1. Open the public site repo on GitHub.
2. Go to `Settings > Pages`.
3. Enter `doorcodesapp.com` as the custom domain.
4. Point the domain's DNS records at GitHub Pages.
5. Turn on `Enforce HTTPS` after DNS propagation finishes.
