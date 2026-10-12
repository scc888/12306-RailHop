// Compatibility entrypoint: unified page replaces former two tabs.
process.env.BROWSER_SCENARIOS='cancel,seats_sort_official';
require('./journey-regressions.cjs');
