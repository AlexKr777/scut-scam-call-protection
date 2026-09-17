package org.scut.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.text.DateFormat;
import java.util.Date;

public class AdvancedActivity extends Activity {
    @Override protected void attachBaseContext(Context base) { super.attachBaseContext(LocaleHelper.apply(base)); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = ScutUi.column(this);
        LinearLayout toolbar = new LinearLayout(this); toolbar.setGravity(Gravity.CENTER_VERTICAL); toolbar.setPadding(ScutUi.dp(this, 8), 0, ScutUi.dp(this, 20), 0);
        Button back = ScutUi.tertiary(this, "‹"); back.setTextSize(28); back.setGravity(Gravity.CENTER); back.setContentDescription(getString(R.string.a11y_back)); back.setOnClickListener(view -> finish()); toolbar.addView(back, new LinearLayout.LayoutParams(ScutUi.dp(this, 48), ScutUi.dp(this, 48)));
        toolbar.addView(ScutUi.text(this, getString(R.string.advanced_title), 18, ScutUi.INK, Typeface.BOLD)); page.addView(toolbar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 64)));
        LinearLayout content = ScutUi.column(this); content.setPadding(ScutUi.dp(this, 20), ScutUi.dp(this, 16), ScutUi.dp(this, 20), ScutUi.dp(this, 42));
        content.addView(ScutUi.text(this, getString(R.string.advanced_warning), 15, ScutUi.MUTED, Typeface.NORMAL));
        content.addView(diagnosticRow(R.string.advanced_connection, CloudControl.configured(this) ? getString(R.string.settings_on) : getString(R.string.settings_off)), ScutUi.matchWrap(this, 28));
        long lastSync = CloudControl.lastSyncMillis(this); content.addView(diagnosticRow(R.string.advanced_last_sync, lastSync == 0 ? "—" : DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(new Date(lastSync))));
        content.addView(diagnosticRow(R.string.advanced_fcm, CloudControl.fcmRegistered(this) ? getString(R.string.settings_on) : getString(R.string.settings_off)));
        String id = CloudControl.deviceId(this); String masked = id.length() >= 8 ? id.substring(0, 4) + "…" + id.substring(id.length() - 4) : "—";
        content.addView(diagnosticRow(R.string.advanced_masked_id, masked));
        content.addView(ScutUi.label(this, getString(R.string.advanced_local_pairing)), ScutUi.matchWrap(this, 34));
        EditText payload = new EditText(this); payload.setHint(R.string.advanced_pairing_hint); payload.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE); payload.setMinHeight(ScutUi.dp(this, 110)); payload.setGravity(Gravity.TOP); payload.setPadding(ScutUi.dp(this, 14), ScutUi.dp(this, 14), ScutUi.dp(this, 14), ScutUi.dp(this, 14)); payload.setBackground(ScutUi.background(ScutUi.RAISED, ScutUi.dp(this, 14), ScutUi.dp(this, 1), ScutUi.STONE)); content.addView(payload, ScutUi.matchWrap(this, 12));
        TextView result = ScutUi.label(this, ""); content.addView(result, ScutUi.matchWrap(this, 8));
        Button pair = ScutUi.secondary(this, getString(R.string.advanced_pair_action)); pair.setOnClickListener(view -> {
            try {
                JSONObject value = new JSONObject(payload.getText().toString()); String endpoint = value.getString("endpoint"); String token = value.getString("pairingToken");
                if (!endpoint.startsWith("ws://")) throw new IllegalArgumentException();
                if (!ScutService.pair(this, endpoint, token)) throw new IllegalStateException(); payload.setText(""); result.setText(R.string.advanced_pair_success);
            } catch (Exception ignored) { result.setText(R.string.advanced_pair_invalid); }
        }); content.addView(pair, ScutUi.matchWrap(this, 12));
        page.addView(ScutUi.scroll(this, content), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(page);
        ScutUi.applySystemBars(this, page);
    }

    private LinearLayout diagnosticRow(int title, String value) {
        LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setMinimumHeight(ScutUi.dp(this, 56));
        row.addView(ScutUi.text(this, getString(title), 15, ScutUi.INK, Typeface.NORMAL), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1)); row.addView(ScutUi.text(this, value, 14, ScutUi.MUTED, Typeface.NORMAL)); return row;
    }
}
