# Arabic

بنيت ReleaseBeacon كأداة متصلة بالإنترنت لمتابعة إصدارات مشاريع GitHub في مكان واحد.

تجلب البيانات الحية من GitHub API، وتقارن وسم الإصدار بنسختك المسجلة، وتوضح هل تغير الإصدار منذ آخر فحص، وتولد لوحة HTML وروابط ملاحظات الإصدار.

جرّبتها فعليًا على مستودعين عامين، مع 19 اختبارًا لحالات النجاح وفشل الاتصال وحدود API. لا تحتاج مكتبات خارجية أو OpenAI API key. اختلاف الوسم يعني راجع الإصدار، ولا يعني تلقائيًا أن الترقية مناسبة لك.

https://github.com/dxrkf/releasebeacon

#Python #GitHub #DeveloperTools #OpenSource

# English

Introducing ReleaseBeacon: an online GitHub release watchlist with exact-tag review, last-observed release tracking and a generated HTML dashboard.

One HTTPS request per repository. Clear error rows instead of silently stale results. No package downloads or automatic upgrades.

Includes a successful two-repository live capture, 19 passing unit tests and zero third-party dependencies. Optional token support uses GITHUB_TOKEN without persisting it.

https://github.com/dxrkf/releasebeacon

Attach assets/cover.png and assets/demo-output.png. The image is a dated API capture, not a live-updating dashboard.
