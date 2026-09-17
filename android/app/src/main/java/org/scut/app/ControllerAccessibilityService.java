package org.scut.app;

import android.accessibilityservice.AccessibilityService;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/** Explicitly enabled only; leaves ordinary volume behavior untouched while disabled. */
public class ControllerAccessibilityService extends AccessibilityService {
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override protected boolean onKeyEvent(KeyEvent event) {
        if (event.getAction()!=KeyEvent.ACTION_DOWN || !CloudControl.controllerButtonsEnabled(this)) return false;
        if (event.getKeyCode()==KeyEvent.KEYCODE_VOLUME_DOWN) { CloudControl.sendCommand(this, "FORCE"); return true; }
        if (event.getKeyCode()==KeyEvent.KEYCODE_VOLUME_UP) { CloudControl.sendCommand(this, "VETO"); return true; }
        return false;
    }
}
