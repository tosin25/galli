// Runs the script named in scriptArgs "galley_target" and writes OK or the error (message + line) to the file
// named in "galley_result", so PowerShell can report script errors instead of InDesign showing a dialog.
#target indesign
(function () {
  var out = File(app.scriptArgs.getValue('galley_result')); out.encoding = 'UTF-8';
  var msg = 'OK';
  try { $.evalFile(File(app.scriptArgs.getValue('galley_target'))); }
  catch (e) {
    msg = 'ERROR: ' + e.message + ' | line ' + e.line + ' | ' + (e.source ? String(e.source).split('\n')[e.line - 1] : '');
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  }
  out.open('w'); out.write(msg); out.close();
})();
