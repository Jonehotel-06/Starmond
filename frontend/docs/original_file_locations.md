# Original file locations and mapping

No upstream application repository or pre-existing source tree was mounted in this workspace. The implementation was authored as a self-contained frontend delivery; therefore an original-path-to-replacement diff cannot be asserted, and no original files were overwritten or deleted.

## Canonical delivered locations

| Area | Delivered path | Notes |
|---|---|---|
| Frontend root/pages | `changed_files/frontend/` | 58 generated HTML routes |
| Shared styling | `changed_files/frontend/assets/css/` | 8 CSS files |
| Browser modules | `changed_files/frontend/assets/js/` | 45 ES modules |
| HTML generation | `changed_files/frontend/tools/` | shell, storefront/admin templates, builders, prerenderer, server |
| Hosting examples | `changed_files/frontend/deploy/` | nginx, Netlify and Vercel examples |
| QA | `tests/`, `reports/` | scripts, mock fixture and result artifacts |
| Documentation | `changed_files/frontend/docs/` | reports and operational notes |

The workspace-level `patches/` and `rollback/` directories contain no source snapshots. If a specific upstream repository is provided later, these paths can be reconciled into a precise changed-file list and original-location map.