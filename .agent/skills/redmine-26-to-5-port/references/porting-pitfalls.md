# Redmine 2.6 to 5 Porting Pitfalls

## Known Traps
- `parent_id` is already a core tree filter in Redmine 5. Do not replace it with a plain integer filter.
- `render :parent` is unsafe in many Redmine 5 plugin view overrides. Copy the full template and insert the plugin line directly.
- `project.principals.find(...)` and other legacy principal queries can fail in hooks. Use modern ActiveRecord queries.
- `available_filters` must contain `QueryFilter` objects, not raw hashes.
- `issues#index` can be slow on the first render due to warm-up. Benchmark twice before calling it a regression.
- Admin menu icons can duplicate in Redmine 5 if a legacy plugin adds its own `background-image` rule on `#admin-menu a.<plugin-name>`. Redmine 5 already renders a core icon for admin menu entries, so remove the plugin-specific admin-menu icon CSS instead of stacking another one.
- If an admin menu label shows overlapping icons or text shifted through the icon area, inspect the plugin stylesheet before the view code. In `redmine_custom_workflows`, the culprit was `#admin-menu a.custom-workflows { background-image: ... }`.
- Do not stop at removing the duplicate CSS. After removing the plugin-specific admin-menu `background-image`, confirm the menu entry still has a single icon. In Redmine 5, the correct fix is usually to add an explicit menu HTML class such as `:html => {:class => 'icon icon-workflows'}` or another core icon class during `menu :admin_menu` registration.
- If the icon disappears after you remove the legacy CSS, the plugin was relying on that CSS as its only icon source. Move the icon responsibility into the menu registration instead of reintroducing plugin-specific admin-menu background CSS.
- Zeitwerk in Redmine 5 will eagerly validate that file paths and constants match. If a file lives at `lib/view_customize/view_layouts_base_html_head_hook.rb`, Rails expects `ViewCustomize::ViewLayoutsBaseHtmlHeadHook`. A plugin namespace like `RedmineViewCustomize::ViewLayoutsBaseHtmlHeadHook` must live under a matching path such as `lib/redmine_view_customize/view_layouts_base_html_head_hook.rb`.
- If plugin boot fails with `uninitialized constant ...` during eager load even though the file was manually required, check the path-to-constant mapping before debugging the code inside the class. In `view_customize`, the real issue was the directory name, not the hook implementation.
- Old code-display helpers can silently degrade in Redmine 5 views. A plugin `show` page that used `highlight_by_language(code, :js/:css)` may render escaped literal `<span ...>` markup instead of syntax-highlighted code.
- Prefer Redmine 5 `syntax_highlight(filename, content)` over legacy plugin highlighters when rendering code snippets in plugin views, but do not output it bare. In `view_customize`, `syntax_highlight(...)` returned HTML fragments that ERB escaped into literal `&lt;span ...&gt;` text.
- Wrap Redmine 5 `syntax_highlight(...)` with an explicit code block and mark the fragment safe, for example `<pre><code class="syntaxhl"><%= raw syntax_highlight('view_customize.js', code) %></code></pre>`. This matched Redmine 5's Rouge output expectations and restored visible syntax highlighting.

## Macro Check
- For `issue_macro`, test with a real issue id from the target database, not a hard-coded legacy id.
- If Redmine shows the macro text literally, confirm the macro is registered and that the backing helper method exists.
- If Redmine shows `undefined method macro_...`, the macro registration exists but the helper method was not defined or loaded correctly.
- In Redmine 5, plugin-defined macro methods may exist on the helper instance even when `ActionView::Base.instance_method(...)` cannot see them. Prefer looking up the macro with `method(:macro_name)` or a similar instance-level check when diagnosing helper-loaded macros.

## High-Risk Patterns To Search For
- `before_filter`
- `alias_method_chain`
- `unloadable`
- `dispatcher`
- `find(:all)`
- `project.principals.find`
- `render :parent`
- `available_filters.merge!`
- raw hashes returned from query filter patches
- `#admin-menu a.<plugin-name> { background-image: ... }`
- admin menu entries without a Redmine 5 `:html => {:class => 'icon ...'}` icon class
- lib paths whose directory name does not match the namespace defined in the file
- bare `<%= syntax_highlight(...) %>` in plugin views without `raw` and an outer `<pre><code>`
