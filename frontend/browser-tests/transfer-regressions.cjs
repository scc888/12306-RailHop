// Compatibility entrypoint for the train list and inline transfer settings.
process.env.BROWSER_SCENARIOS='cancel,seats_settings,selected_transfer,adjust_selected';
require('./journey-regressions.cjs');
