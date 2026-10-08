# Bundled typography and icons

These unmodified WOFF2 files preserve the application's existing Google Fonts
families and Material Icons. `fonts.css` uses local relative URLs so builds and
browsers do not contact Google for typography. `sources.json` records the exact
source URLs, retrieval date, sizes and SHA-256 hashes for every font and license.
Preserve the accompanying notices in distributed frontend assets.

- Instrument Sans: [SIL OFL](https://github.com/google/fonts/blob/main/ofl/instrumentsans/OFL.txt).
- Instrument Serif: [SIL OFL](https://github.com/google/fonts/blob/main/ofl/instrumentserif/OFL.txt).
- IBM Plex Mono: [SIL OFL](https://github.com/google/fonts/blob/main/ofl/ibmplexmono/OFL.txt).
- Material Icons: [Apache-2.0](https://github.com/google/material-design-icons/blob/master/LICENSE).

No network fetch runs as part of installation, build or application startup.
Updating font sources requires an intentional new asset/version review.
