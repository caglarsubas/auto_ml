# Vendored SheetJS distribution

`xlsx-0.20.3.tgz` is the official SheetJS Community Edition distribution from
`https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz`, retrieved 7 October 2026.
The embedded `package/LICENSE` is Apache-2.0. Preserve the archive and license
when distributing the frontend dependency package.

SHA-256: `8dc73fc3b00203e72d176e85b50938627c7b086e607c682e8d3c22c02bb99fe8`.

The [official installation guidance](https://docs.sheetjs.com/docs/getting-started/installation/nodejs/)
recommends vendoring the tarball. The npm registry's older `xlsx` distribution
was replaced to address its known security advisories. `package-lock.json`
also records archive integrity. This makes installation independent of the
SheetJS CDN once this repository and the other dependency packages are staged.
