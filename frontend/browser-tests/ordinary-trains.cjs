// Compatibility entrypoint for ordinary-train controls on the unified page.
process.env.BROWSER_SCENARIOS='regular';
require('./journey-regressions.cjs');
