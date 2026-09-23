# Fonts

`Vazirmatn[wght].woff2` — the variable weight file, committed to the repo.

Source: <https://github.com/rastikerdar/vazirmatn/releases>
(in the release archive it lives at `fonts/webfonts/Vazirmatn[wght].woff2`)

It is committed rather than fetched at runtime on purpose. Google Fonts and
similar CDNs are not reliably reachable for Iranian users, and a Persian
interface falling back to a Latin-first font does not look like a styling bug
— it looks like a broken product.

One variable file covers every weight the app uses, so there is nothing to keep
in sync when a heading gets bolder.
