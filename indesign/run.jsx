// Runs the script named in scriptArgs "galley_target" and writes OK or the error (message + line) to the file
// named in "galley_result", so callers can report script errors instead of InDesign showing a dialog.
// If "galley_undo" is set, the whole script runs as ONE undo step with that name (Edit > Undo "Galley: ...").
#target indesign
(function () {
  var SA = app.scriptArgs;
  var out = File(SA.getValue('galley_result')); out.encoding = 'UTF-8';
  var target = File(SA.getValue('galley_target'));
  var undo = SA.isDefined('galley_undo') ? SA.getValue('galley_undo') : '';
  var msg = 'OK';
  // no dialogs while Galley works (missing fonts, missing links, alerts): a dialog would freeze InDesign
  // until someone clicks it, with Galley waiting behind it
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
  try {
    if (undo) app.doScript(function () { $.evalFile(target); }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, undo);
    else $.evalFile(target);
  } catch (e) {
    msg = 'ERROR: ' + e.message + ' | line ' + e.line + ' | ' + (e.source ? String(e.source).split('\n')[e.line - 1] : '');
  }
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  out.open('w'); out.write(msg); out.close();
})();
