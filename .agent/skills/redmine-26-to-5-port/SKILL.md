---
name: redmine-26-to-5-port
description: Port legacy Redmine 2.6 plugins to Redmine 5. Use when migrating plugins, fixing Rails 6 compatibility issues, or diagnosing Redmine 2.6-to-5 breakages such as old hooks, query filters, macros, and view overrides.
---

# Redmine 2.6 to 5 Porting Guide

## Start Here
- Read `references/porting-pitfalls.md` first.
- Port one plugin at a time.
- Verify against the live Redmine 5 container after each change.

## Porting Flow
1. Inventory the plugin entry points: `init.rb`, controllers, hooks, helpers, query patches, views, and assets.
2. Replace deprecated Rails/Redmine patterns:
   - `before_filter` -> `before_action`
   - `alias_method_chain` -> `prepend`
   - `unloadable` -> remove
   - `dispatcher` / old autoloading -> `Rails.configuration.to_prepare` or explicit loading
3. Keep core Redmine names intact. Do not shadow built-in filters, routes, helpers, or view partials.
4. Re-test the exact page or API path the plugin touches.

## Prefer These Patterns
- Use `QueryFilter` objects for Redmine 5 query filters.
- Use modern ActiveRecord scopes instead of `find(:all)` and ad hoc SQL.
- Copy the full Redmine 5 template when a plugin needs to inject JS or markup into a view override.
- Load hooks once in `to_prepare` so Zeitwerk sees stable constants.

## Verify These Surfaces
- `issues#index` and `issues#new`
- wiki edit/render pages
- project show/index pages
- any plugin settings page
- admin menu entries and plugin icons
- any macro or hook endpoint the plugin exposes

## Stop And Check
- If a page returns literal macro text, confirm the macro name and the helper method that should back it.
- If a filter looks present but behaves oddly, confirm it is not replacing a core Redmine filter.
- If a page is slow only on first load, benchmark it twice before blaming the plugin.
