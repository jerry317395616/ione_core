# App navigation availability

Applications can register `ione_navigation_filters` callables taking the native sidebar mapping and returning a narrowed mapping. The filter preserves native order, labels and section/child structure. It applies before existing business permission projection and also to Administrator's native boot and menu-refresh payloads. A feature filter is not an authorization grant and must not replace document permissions.

`sidebar_defaults.install(module, sections, version, label=...)` initializes a versioned default through Frappe's native site-level Custom Sidebar. Old entries remain hidden references rather than being deleted. The Patch Log marker makes later runs no-ops so administrators retain subsequent arrangements. The caller owns its configuration, deployment backup and transaction; the helper neither commits nor assigns roles or permissions.

Rehab supplies its own feature inventory and default grouping. Other applications and existing unrelated worktrees are unchanged.
